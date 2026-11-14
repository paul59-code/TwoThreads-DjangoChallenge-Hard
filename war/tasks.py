"""Drafting în loturi cu Celery.

Serverul dă datele în loturi: fiecare răspuns conține lista de oameni (cu `rank`) și `next_batch`.
Fluxul:
  start_draft()  ->  download_batch(0)  ->  salvează lotul, apoi lansează
                                              * draft_batch(lot)  (task separat, pornește imediat)
                                              * download_batch(next_batch)  (dacă mai există)
Pentru că adresa lotului următor e cunoscută abia după ce îl descarci pe cel curent, descărcarea e un lanț;
în schimb drafting-ul fiecărui lot rulează în paralel cu descărcarea celorlalte.

Retry: erorile de rețea / timeout reiau taskul cu întârziere exponențială (2s, 4s, 8s ... max 60s, cu jitter),
de cel mult MAX_RETRIES ori. `acks_late` face ca un task pierdut la căderea workerului să fie reluat.
Taskurile sunt idempotente (upsert pe id / UPDATE pe rank), deci o reluare nu strică nimic.
"""
import json
import socket
import urllib.error
import urllib.request

from celery import shared_task
from django.conf import settings
from django.db import transaction

from .models import Person

MAX_RETRIES = 6
RETRYABLE = (TimeoutError, socket.timeout, ConnectionError, urllib.error.URLError)
RETRY_POLICY = dict(
    autoretry_for=RETRYABLE,
    retry_backoff=2,          # 2s, 4s, 8s, ...
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=MAX_RETRIES,
    acks_late=True,
)


def _fetch_batch(batch):
    url = settings.DRAFT_BATCH_URL.format(batch=batch)
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=settings.DRAFT_FETCH_TIMEOUT) as response:
        payload = json.load(response)
    return payload["data"], payload.get("next_batch")


@shared_task(bind=True, **RETRY_POLICY)
def download_batch(self, batch):
    items, next_batch = _fetch_batch(batch)
    with transaction.atomic():
        for item in items:
            defaults = {"name": item["name"], "age": item["age"]}
            if item.get("key"):
                defaults["key"] = item["key"]
            Person.objects.update_or_create(
                id=item["id"],
                defaults=defaults,
                create_defaults={**defaults, "health": item.get("health", 100)},
            )
    # Lotul e descărcat: drafting-ul lui pornește imediat, ca task separat...
    draft_batch.delay(batch, [{"id": i["id"], "rank": i.get("rank")} for i in items])
    # ...iar descărcarea continuă cu lotul următor.
    if next_batch is not None:
        download_batch.delay(next_batch)
    return {"batch": batch, "people": len(items), "next_batch": next_batch}


@shared_task(bind=True, **RETRY_POLICY)
def draft_batch(self, batch, items):
    """Atribuie gradul (rank) persoanelor din lot."""
    with transaction.atomic():
        for item in items:
            if item.get("rank") is not None:
                Person.objects.filter(pk=item["id"]).update(rank=item["rank"])
    return {"batch": batch, "drafted": len(items)}


def start_draft(first_batch=0):
    """Pornește lanțul de descărcare de la primul lot."""
    return download_batch.delay(first_batch)
