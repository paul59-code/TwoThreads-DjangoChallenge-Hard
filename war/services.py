"""Simularea luptelor: o sarcină în fundal (thread) per luptă, toate rulând în paralel.

Concurență:
* un soldat poate apărea în mai multe lupte, deci mai multe thread-uri scad sănătatea aceluiași rând;
  scăderea se face într-un singur UPDATE atomic (`health = MAX(health - damage, 0)`), fără citire-modificare-scriere;
* fiecare eveniment este "revendicat" cu un UPDATE condiționat (applied=False -> True) în aceeași tranzacție
  cu scăderea, deci un eveniment nu se aplică niciodată de două ori (nici dacă rulează două simulări deodată);
* tranzacțiile sunt scurte (un eveniment), ca scrierile din SQLite să nu se blocheze reciproc mult timp;
* operațiile care primesc "database is locked" se reiau.
"""
import time
from concurrent.futures import ThreadPoolExecutor

from django.db import OperationalError, connections, transaction
from django.db.models import F, Value
from django.db.models.functions import Greatest

from .models import Fight, FightEvent, Person

MAX_WORKERS = 32


def _retry(fn, attempts=8):
    for i in range(attempts):
        try:
            return fn()
        except OperationalError as exc:  # "database is locked"
            if "locked" not in str(exc).lower() or i == attempts - 1:
                raise
            time.sleep(0.05 * (i + 1))


def _apply_event(event_id):
    event = FightEvent.objects.get(pk=event_id)  # citire în afara tranzacției de scriere
    with transaction.atomic():
        claimed = FightEvent.objects.filter(pk=event_id, applied=False).update(applied=True)
        if not claimed:  # deja aplicat de altcineva
            return
        Person.objects.filter(pk=event.defender_id).update(
            health=Greatest(F("health") - event.damage, Value(0))
        )
        health = Person.objects.values_list("health", flat=True).get(pk=event.defender_id)
        FightEvent.objects.filter(pk=event_id).update(defender_health_after=health)


def run_fight(fight_id):
    """Rejoacă o luptă. Rulează într-un thread propriu, cu conexiunea lui la baza de date."""
    try:
        claimed = _retry(
            lambda: Fight.objects.filter(pk=fight_id, status=Fight.PENDING).update(status=Fight.RUNNING)
        )
        if not claimed:
            return fight_id
        event_ids = list(
            FightEvent.objects.filter(fight_id=fight_id, applied=False)
            .order_by("order")
            .values_list("pk", flat=True)
        )
        for event_id in event_ids:
            _retry(lambda: _apply_event(event_id))
        _retry(lambda: Fight.objects.filter(pk=fight_id).update(status=Fight.DONE))
        return fight_id
    finally:
        connections.close_all()  # thread-ul își închide conexiunea


def simulate_pending():
    """Pornește câte un proces de fundal pentru fiecare luptă nerejucată și așteaptă finalul lor."""
    fight_ids = list(Fight.objects.filter(status=Fight.PENDING).values_list("pk", flat=True))
    if not fight_ids:
        return 0
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(fight_ids))) as pool:
        for future in [pool.submit(run_fight, fid) for fid in fight_ids]:
            future.result()  # propagă excepțiile
    return len(fight_ids)


def reset_all():
    """Readuce totul la starea inițială (sănătate 100, lupte nerejucate)."""
    with transaction.atomic():
        Person.objects.update(health=100)
        FightEvent.objects.update(applied=False, defender_health_after=None)
        Fight.objects.update(status=Fight.PENDING)
