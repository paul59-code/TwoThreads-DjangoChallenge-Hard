"""Încarcă oamenii și luptele în baza de date.

Din API:      python manage.py load_data --fights-path /fights
Din fișiere:  python manage.py load_data --people-file people.json --fights-file fights.json

Formatul luptelor nu era cunoscut la scrierea acestui cod, așa că numele câmpurilor sunt acceptate în
mai multe variante (vezi *_KEYS). Dacă niciuna nu se potrivește, comanda afișează cheile găsite.
"""
import json
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from war.models import Fight, FightEvent, Person

PAIR_KEYS = [
    ("soldier_a", "soldier_b"), ("soldier1", "soldier2"), ("soldier_1", "soldier_2"),
    ("soldier1_id", "soldier2_id"), ("soldier_1_id", "soldier_2_id"), ("fighter1", "fighter2"),
    ("fighter_1", "fighter_2"), ("a", "b"), ("first", "second"), ("p1", "p2"),
]
LIST_KEYS = ["soldiers", "soldier_ids", "soldierIds", "fighters", "participants", "people", "ids"]
EVENTS_KEYS = ["events", "fight_events", "fightEvents", "history", "log", "attacks"]
ATTACKER_KEYS = ["attacker", "attacker_id", "attackerId", "from", "source", "attacks"]
DEFENDER_KEYS = ["defender", "defender_id", "defenderId", "to", "target", "defends"]
DAMAGE_KEYS = ["damage", "points", "damage_points", "damagePoints", "amount", "hp", "value"]
ID_KEYS = ["id", "fight_id", "fightId"]


def fetch_json(url):
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def read_json_file(path):
    """Citește un fișier JSON în UTF-8 (cu/fără BOM) sau UTF-16 (cum îl salvează PowerShell cu `>`)."""
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig")
    return json.loads(text)


def unwrap(payload):
    """Acceptă o listă simplă sau învelișul {"data": [...], "status": ...}."""
    while isinstance(payload, dict) and "data" in payload:
        payload = payload["data"]
    if isinstance(payload, dict):
        for key in ("fights", "people", "items", "results"):
            if isinstance(payload.get(key), list):
                return payload[key]
    if not isinstance(payload, list):
        raise CommandError(f"Format neașteptat (nu e listă): {str(payload)[:300]}")
    return payload


def pick(obj, keys, what):
    for key in keys:
        if key in obj:
            return obj[key]
    raise CommandError(f"Nu găsesc {what} în {json.dumps(obj)[:300]} (chei: {sorted(obj)}). "
                       f"Adaugă numele câmpului în lista din load_data.py.")


def as_id(value):
    return int(value["id"] if isinstance(value, dict) else value)


def parse_fight(raw, index):
    fight_id = next((raw[k] for k in ID_KEYS if k in raw), index)
    pair = next(((raw[a], raw[b]) for a, b in PAIR_KEYS if a in raw and b in raw), None)
    if pair is None:
        listed = next((raw[k] for k in LIST_KEYS if isinstance(raw.get(k), list) and len(raw[k]) == 2), None)
        if listed is None:
            raise CommandError(f"Nu găsesc cei doi soldați în {json.dumps(raw)[:300]} (chei: {sorted(raw)}).")
        pair = tuple(listed)
    events = []
    for order, event in enumerate(pick(raw, EVENTS_KEYS, "lista de evenimente")):
        events.append((
            order,
            as_id(pick(event, ATTACKER_KEYS, "atacatorul")),
            as_id(pick(event, DEFENDER_KEYS, "apărătorul")),
            int(pick(event, DAMAGE_KEYS, "daunele")),
        ))
    return int(fight_id), as_id(pair[0]), as_id(pair[1]), events


class Command(BaseCommand):
    help = "Încarcă oamenii (și soldații) și luptele cu evenimentele lor."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", default=settings.API_BASE_URL)
        parser.add_argument("--people-path", default="/people")
        parser.add_argument("--fights-path", default="/fights")
        parser.add_argument("--people-file")
        parser.add_argument("--fights-file")
        parser.add_argument("--skip-fights", action="store_true")

    def handle(self, *args, **opts):
        base = opts["base_url"].rstrip("/")

        def load(file_opt, path_opt):
            if opts[file_opt]:
                return unwrap(read_json_file(opts[file_opt]))
            return unwrap(fetch_json(base + opts[path_opt]))

        people = load("people_file", "people_path")
        with transaction.atomic():
            for p in people:
                Person.objects.update_or_create(
                    id=p["id"], defaults={"name": p["name"], "age": p["age"]}
                )
        self.stdout.write(f"{len(people)} persoane salvate.")

        if opts["skip_fights"]:
            return
        raw_fights = load("fights_file", "fights_path")
        parsed = [parse_fight(raw, i) for i, raw in enumerate(raw_fights)]
        known = set(Person.objects.values_list("id", flat=True))
        for fight_id, a, b, events in parsed:
            missing = {a, b} | {x for _, att, dfd, _ in events for x in (att, dfd)}
            missing -= known
            if missing:
                raise CommandError(f"Lupta {fight_id} referă soldați necunoscuți: {sorted(missing)}")

        with transaction.atomic():
            for fight_id, a, b, events in parsed:
                Fight.objects.update_or_create(
                    id=fight_id,
                    defaults={"soldier_a_id": a, "soldier_b_id": b, "status": Fight.PENDING},
                )
                FightEvent.objects.filter(fight_id=fight_id).delete()
                FightEvent.objects.bulk_create(
                    FightEvent(fight_id=fight_id, order=o, attacker_id=att, defender_id=dfd, damage=dmg)
                    for o, att, dfd, dmg in events
                )
        Person.objects.update(health=100)
        self.stdout.write(f"{len(parsed)} lupte salvate, cu {sum(len(p[3]) for p in parsed)} evenimente.")
