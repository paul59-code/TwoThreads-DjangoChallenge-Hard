"""Strict production fight parser; drafting adapter awaits the real dataset."""
import json
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from django.conf import settings
from django.db import transaction
from .models import Person, Fight, FightEvent

class TransientDownload(Exception):
    pass

def load_json(source):
    if not str(source).startswith(('http://', 'https://')):
        raw = Path(source).read_bytes()
        return json.loads(raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'))
    try:
        response = requests.get(source, timeout=(5, 30))
    except (requests.Timeout, requests.ConnectionError) as exc:
        raise TransientDownload(str(exc)) from exc
    if response.status_code in (408, 429) or response.status_code >= 500:
        raise TransientDownload(f'HTTP {response.status_code}: {source}')
    response.raise_for_status()
    return response.json()

def api_url(path):
    return urljoin(settings.API_BASE_URL, str(path))

def rows(payload):
    result = payload.get('data') if isinstance(payload, dict) else payload
    if not isinstance(result, list):
        raise ValueError('Expected a data array; instructions are not a dataset.')
    return result

def integer(value, label):
    if type(value) is not int:
        raise ValueError(f'{label} must be an integer')
    return value

def import_people(payload):
    records = rows(payload)
    with transaction.atomic():
        for r in records:
            defaults = {'name': r['name'], 'age': integer(r['age'], 'age')}
            if 'key' in r:
                defaults['key'] = r['key']
            Person.objects.update_or_create(external_id=integer(r['id'], 'id'), defaults=defaults)
    return len(records)

def import_fights(payload):
    records = rows(payload)
    for r in records:
        # Each fight is all-or-nothing; previously imported batches survive errors.
        with transaction.atomic():
            blue = Person.objects.get(external_id=integer(r['blue_soldier_id'], 'blue_soldier_id'))
            red = Person.objects.get(external_id=integer(r['red_soldier_id'], 'red_soldier_id'))
            if blue == red or not isinstance(r['steps'], list) or not r['steps']:
                raise ValueError('A fight needs two participants and a nonempty steps list')
            external_id = str(integer(r['fight_id'], 'fight_id'))
            fight, created = Fight.objects.get_or_create(external_id=external_id, defaults={'blue_soldier': blue, 'red_soldier': red, 'source_data': r})
            if not created:
                if fight.source_data != r:
                    raise ValueError(f'Fight {external_id} changed; refusing to rewrite historical events')
                continue
            events = []
            people = {blue.external_id: blue, red.external_id: red}
            for index, step in enumerate(r['steps']):
                attacker = people[integer(step['attacker'], 'attacker')]
                defender = people[integer(step['defender'], 'defender')]
                damage = integer(step['damage'], 'damage')
                if attacker == defender or damage < 0:
                    raise ValueError('Invalid attacker/defender or negative damage')
                events.append(FightEvent(fight=fight, attacker=attacker, defender=defender, damage=damage, event_index=index, source_data=step))
            FightEvent.objects.bulk_create(events)
    return len(records)

def next_fight_source(payload, source):
    # The live API uses numeric next_batch, not the instruction's prose 'next'.
    if 'next_batch' not in payload:
        raise ValueError('Missing next_batch: cannot confirm the final fight batch')
    next_batch = payload['next_batch']
    if next_batch is None or next_batch is False:
        return None
    if type(next_batch) is int:
        if next_batch < 0:
            raise ValueError('Unexpected negative next_batch; inspect response')
        return api_url(f'fight/{next_batch}')
    if isinstance(next_batch, str) and next_batch:
        if next_batch.isdigit():
            return api_url(f'fight/{next_batch}')
        return urljoin(source, next_batch)
    raise ValueError(f'Unrecognized next_batch: {next_batch!r}')

def import_all_fights(source, cache_dir=None, local_only=False):
    seen = set()
    total = 0
    while source:
        if source in seen:
            raise ValueError('Cyclic fight pagination')
        seen.add(source)
        payload = load_json(source)
        if cache_dir:
            path = Path(cache_dir)
            path.mkdir(parents=True, exist_ok=True)
            (path / f'fight_{len(seen)-1}.json').write_text(json.dumps(payload), encoding='utf-8')
        total += import_fights(payload)
        following = next_fight_source(payload, source)
        if local_only and following:
            candidate = Path(source).resolve().parent / f'fight_{payload["next_batch"]}.json'
            if not candidate.is_file():
                raise ValueError(f'Batch imported but more data required: {following}; download it to {candidate}')
            following = str(candidate)
        source = following
    return total
