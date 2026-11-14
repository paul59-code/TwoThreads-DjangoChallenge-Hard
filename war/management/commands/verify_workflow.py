import json
from pathlib import Path
from collections import Counter
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum
from war.data import load_json, rows
from django.conf import settings
from war.models import Person, DraftBatch, Fight, FightEvent

class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--people', default='people.json')
        parser.add_argument('--cache-drafts', action='store_true', help='Export real persisted draft responses into datasets/')
    def handle(self, *args, **options):
        errors = []
        for r in rows(load_json(options['people'])):
            p = Person.objects.filter(external_id=r['id']).first()
            if not p or (p.name, p.age) != (r['name'], r['age']):
                errors.append(f'Missing/incorrect person {r["id"]}')
        batches = list(DraftBatch.objects.all())
        initial_health = {}
        expected_people = set()
        for batch in batches:
            if batch.status != 'COMPLETED':
                errors.append(f'Unfinished draft batch {batch.pk}: {batch.status}')
            elif batch.payload:
                for r in rows(batch.payload):
                    expected_people.add(r['id'])
                    if 'health' in r:
                        initial_health[r['id']] = r['health']
                    if Person.objects.get(external_id=r['id']).rank != r['rank']:
                        errors.append(f'Rank mismatch {r["id"]}')
                if options['cache_drafts']:
                    directory = Path(settings.BASE_DIR) / 'datasets'
                    directory.mkdir(exist_ok=True)
                    index = batch.source.rstrip('/').split('/')[-1]
                    (directory / f'draft_{index}.json').write_text(json.dumps(batch.payload), encoding='utf-8')
        if batches and expected_people != set(Person.objects.values_list('external_id', flat=True)):
            errors.append('Draft input does not cover every registered person')
        # Check persisted pagination, including an explicit terminal response.
        for batch in batches:
            if batch.payload and 'next_batch' in batch.payload and batch.payload['next_batch'] is not None:
                from war.data import api_url
                if not DraftBatch.objects.filter(source=api_url(f'draft/{batch.payload["next_batch"]}'), status='COMPLETED').exists():
                    errors.append(f'Missing next draft batch after {batch.source}')
        received = dict(FightEvent.objects.filter(processed=True).values('defender__external_id').annotate(total=Sum('damage')).values_list('defender__external_id', 'total'))
        if settings.WAR_MIN_HEALTH is None:
            for person in Person.objects.all():
                expected = initial_health.get(person.external_id, settings.WAR_INITIAL_HEALTH) - received.get(person.external_id, 0)
                if person.health != expected:
                    errors.append(f'Health mismatch #{person.external_id}: {person.health} != {expected}')
        for path in (Path(settings.BASE_DIR) / 'datasets').glob('fight_*.json'):
            payload = load_json(path)
            for r in rows(payload):
                fight = Fight.objects.filter(external_id=str(r['fight_id'])).first()
                if not fight or fight.source_data != r or fight.events.count() != len(r['steps']):
                    errors.append(f'Missing/incorrect fight {r["fight_id"]}')
        undrafted = Person.objects.filter(rank__isnull=True).count()
        if undrafted:
            errors.append(f'{undrafted} people have no rank; real drafting data required')
        self.stdout.write(f'People={Person.objects.count()}, draft batches={len(batches)}, fights={Fight.objects.count()}, events={FightEvent.objects.count()}, processed={FightEvent.objects.filter(processed=True).count()}')
        hellstorm = Person.objects.filter(name='Hellstorm Fireburn').values('external_id', 'key', 'rank').first()
        self.stdout.write(f'Hellstorm: {hellstorm}')
        self.stdout.write(f'Fight statuses: {dict(Counter(Fight.objects.values_list("status", flat=True)))}')
        if errors:
            raise CommandError('; '.join(errors))
        self.stdout.write('People and stored drafting data verified')
