"""Fixtures for drafting are synthetic. Fight regression uses downloaded API data."""
import json
import tempfile
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, Mock
from django.conf import settings
from django.test import TestCase, TransactionTestCase, Client
from django.db import close_old_connections, connection
from django.db.migrations.executor import MigrationExecutor
from celery.exceptions import Retry
from .models import Person, Fight, FightEvent, DraftBatch
from .data import import_people, import_fights, load_json, next_fight_source, TransientDownload
from .services import replay_fight, dispatch_fights
from .tasks import draft_batch, download_draft_batch, download_drafting

def synthetic_people():
    import_people({'data': [{'id': i, 'age': 24, 'name': 'Same name', 'key': 'draft-info' if i == 0 else None} for i in range(4)]})
    Person.objects.update(rank='TEST ONLY')

def synthetic_fight(identifier=0, blue=0, red=1, damage=30):
    return {'fight_id': identifier, 'blue_soldier_id': blue, 'red_soldier_id': red, 'steps': [{'attacker': blue, 'defender': red, 'damage': damage}, {'attacker': red, 'defender': blue, 'damage': 5}]}

class ImportTests(TestCase):
    def test_people_ids_update_and_preserve_military_fields(self):
        synthetic_people()
        Person.objects.filter(external_id=0).update(health=49, rank='General')
        import_people({'data': [{'id': 0, 'name': 'Hellstorm Fireburn', 'age': 25, 'key': 'fight-info'}]})
        p = Person.objects.get(external_id=0)
        self.assertEqual((p.health, p.rank, p.key, p.age), (49, 'General', 'fight-info', 25))
        self.assertEqual(Person.objects.count(), 4)

    def test_actual_people(self):
        payload = load_json(settings.BASE_DIR / 'people.json')
        import_people(payload)
        import_people(payload)
        self.assertEqual(Person.objects.count(), len(payload['data']))
        self.assertEqual(Person.objects.get(external_id=99).key, 'draft-info')
        self.assertTrue(Person.objects.filter(external_id=0).exists())

    def test_events_order_and_idempotent_import(self):
        synthetic_people()
        payload = {'data': [synthetic_fight()]}
        import_fights(payload)
        import_fights(payload)
        self.assertEqual(Fight.objects.count(), 1)
        self.assertEqual(list(FightEvent.objects.values_list('event_index', 'damage')), [(0, 30), (1, 5)])
        self.assertEqual(Person.objects.get(external_id=1).health, 100)
        changed = synthetic_fight(damage=90)
        with self.assertRaises(ValueError):
            import_fights({'data': [changed]})

    def test_invalid_participant_rolls_back(self):
        synthetic_people()
        r = synthetic_fight()
        r['steps'][0]['defender'] = 3
        with self.assertRaises(KeyError):
            import_fights({'data': [r]})
        self.assertEqual(Fight.objects.count(), 0)

    def test_pagination(self):
        self.assertTrue(next_fight_source({'next_batch': 1}, 'x').endswith('/fight/1'))
        self.assertIsNone(next_fight_source({'next_batch': None}, 'x'))
        with self.assertRaises(ValueError):
            next_fight_source({}, 'x')

class DraftTests(TestCase):
    def setUp(self):
        synthetic_people()
    def test_draft_idempotency_and_key(self):
        b = DraftBatch.objects.create(source='TEST ONLY', payload={'data': [{'id': 0, 'rank': 'Private', 'key': 'fight-info', 'health': 123}]})
        draft_batch.apply(args=[b.pk], throw=True)
        Person.objects.filter(external_id=0).update(health=90)
        draft_batch.apply(args=[b.pk], throw=True)
        p = Person.objects.get(external_id=0)
        self.assertEqual((p.rank, p.key, p.health), ('Private', 'fight-info', 90))

    @patch('war.tasks.download_draft_batch.delay')
    def test_each_manifest_batch_has_separate_task(self, delay):
        delay.return_value.id = 'test-download-id'
        with patch('war.tasks.load_json', return_value={'batches': ['one.json', 'two.json']}):
            download_drafting.run(str(settings.BASE_DIR / 'TEST-ONLY-manifest.json'))
        self.assertEqual(delay.call_count, 2)
        self.assertNotEqual(delay.call_args_list[0].args, delay.call_args_list[1].args)

    @patch('war.tasks.draft_batch.delay')
    @patch('war.tasks.load_json')
    def test_download_immediately_dispatches_only_its_batch(self, load, delay):
        delay.return_value.id = 'test-draft-id'
        load.return_value = {'data': [{'id': 0, 'rank': 'TEST'}]}
        one = DraftBatch.objects.create(source='https://example.invalid/one')
        two = DraftBatch.objects.create(source='https://example.invalid/two')
        download_draft_batch.apply(args=[one.pk], throw=True)
        delay.assert_called_once_with(one.pk)
        two.refresh_from_db()
        self.assertIsNone(two.payload)

    @patch('war.tasks.load_json', side_effect=TransientDownload('timeout'))
    def test_timeout_uses_bounded_celery_retry(self, load):
        b = DraftBatch.objects.create(source='https://example.invalid/timeout')
        with patch.object(download_draft_batch, 'retry', side_effect=Retry('retry')) as retry:
            with self.assertRaises(Retry):
                download_draft_batch.run(b.pk)
        retry.assert_called_once()
        self.assertEqual(download_draft_batch.max_retries, 5)

    @patch('war.tasks.load_json', side_effect=ValueError('malformed dataset'))
    def test_permanent_error_is_not_retried(self, load):
        b = DraftBatch.objects.create(source='invalid')
        with patch.object(download_draft_batch, 'retry') as retry:
            with self.assertRaises(ValueError):
                download_draft_batch.run(b.pk)
        retry.assert_not_called()

    @patch('war.tasks.download_draft_batch.delay')
    @patch('war.tasks.draft_batch.delay')
    def test_actual_pagination_dispatches_draft_before_next_download(self, draft_delay, download_delay):
        calls = []
        draft_delay.side_effect = lambda pk: (calls.append(('draft', pk)) or Mock(id='draft-task'))
        download_delay.side_effect = lambda pk: (calls.append(('download', pk)) or Mock(id='download-task'))
        from .tasks import accept_draft_download
        from .data import api_url
        b = DraftBatch.objects.create(source=api_url('draft/0'))
        accept_draft_download(b, {'data': [{'id': 0, 'rank': 'Lieutenant', 'health': 100}], 'next_batch': 1}, 'coordinator-task')
        self.assertEqual([kind for kind, pk in calls], ['draft', 'download'])
        self.assertTrue(DraftBatch.objects.filter(source=api_url('draft/1')).exists())

    def test_all_cached_actual_drafting_records(self):
        import_people(load_json(settings.BASE_DIR / 'people.json'))
        paths = list((settings.BASE_DIR / 'datasets').glob('draft_*.json'))
        if not paths:
            self.skipTest('Real draft responses are still downloading')
        expected = {}
        for path in paths:
            payload = load_json(path)
            b = DraftBatch.objects.create(source=str(path), payload=payload)
            draft_batch.apply(args=[b.pk], throw=True)
            expected.update({r['id']: r for r in payload['data']})
        for identifier, r in expected.items():
            p = Person.objects.get(external_id=identifier)
            self.assertEqual((p.rank, p.health), (r['rank'], r['health']))
            if 'key' in r:
                self.assertEqual(p.key, r['key'])

class SimulationTests(TransactionTestCase):
    def setUp(self):
        synthetic_people()

    def test_retry_and_repeated_requests_do_not_repeat_damage(self):
        import_fights({'data': [synthetic_fight()]})
        pk = Fight.objects.get().pk
        from .services import apply_next_event
        apply_next_event(pk)  # Simulated worker crash after committed event.
        replay_fight(pk)
        replay_fight(pk)
        self.assertEqual(Person.objects.get(external_id=1).health, 70)
        self.assertEqual(FightEvent.objects.filter(processed=True).count(), 2)
        with patch('war.tasks.simulate_fight.delay') as delay:
            self.assertEqual(dispatch_fights(), 0)
        delay.assert_not_called()

    def test_damage_and_marker_roll_back_together(self):
        import_fights({'data': [synthetic_fight()]})
        from .services import apply_next_event
        with patch.object(FightEvent, 'save', side_effect=RuntimeError('crash before marker commit')):
            with self.assertRaises(RuntimeError):
                apply_next_event(Fight.objects.get().pk)
        self.assertEqual(Person.objects.get(external_id=1).health, 100)
        self.assertFalse(FightEvent.objects.filter(processed=True).exists())

    def test_duplicate_dispatch_and_html_csrf(self):
        import_fights({'data': [synthetic_fight()]})
        with patch('war.tasks.simulate_fight.delay') as delay:
            delay.return_value.id = 'test-task'
            self.assertEqual(dispatch_fights(), 1)
            self.assertEqual(dispatch_fights(), 0)
            delay.assert_called_once()
        self.assertContains(self.client.get('/simulate'), 'Fight 0')
        self.assertContains(self.client.get('/simulate'), 'csrfmiddlewaretoken')
        self.assertEqual(Client(enforce_csrf_checks=True).post('/simulate').status_code, 403)

    def test_requires_real_drafting_before_dispatch(self):
        import_fights({'data': [synthetic_fight()]})
        Person.objects.update(rank=None)
        with self.assertRaises(ValueError):
            dispatch_fights()

    def run_parallel(self, pks):
        barrier = threading.Barrier(len(pks))
        def run(pk):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return replay_fight(pk)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(pks)) as pool:
            list(pool.map(run, pks))

    def test_independent_fights_and_duplicate_delivery_parallel(self):
        import_fights({'data': [synthetic_fight(), synthetic_fight(1, 2, 3, 20)]})
        pks = list(Fight.objects.values_list('pk', flat=True))
        self.run_parallel(pks + [pks[0]])
        self.assertEqual(Person.objects.get(external_id=1).health, 70)
        self.assertEqual(Person.objects.get(external_id=3).health, 80)
        self.assertEqual(Fight.objects.filter(status='COMPLETED').count(), 2)

    def test_real_fights_1_and_10_soldier_58_finishes_at_49(self):
        import_people(load_json(settings.BASE_DIR / 'people.json'))
        Person.objects.update(rank='TEST RANK — actual drafting data unavailable')
        payload = load_json(settings.BASE_DIR / 'fight_0.json')
        self.assertEqual(len(payload['data']), 30)
        self.assertEqual(sum(len(f['steps']) for f in payload['data']), 163)
        chosen = [f for f in payload['data'] if f['fight_id'] in (1, 10)]
        self.assertEqual(len(chosen), 2)
        self.assertEqual([sum(e['damage'] for e in f['steps'] if e['defender'] == 58) for f in chosen], [27, 24])
        import_fights({'data': chosen})
        self.run_parallel(list(Fight.objects.values_list('pk', flat=True)))
        self.assertEqual(Person.objects.get(external_id=58).health, 49)

    def test_all_available_real_fights_exact_damage(self):
        import_people(load_json(settings.BASE_DIR / 'people.json'))
        Person.objects.update(rank='TEST ONLY')
        paths = list((settings.BASE_DIR / 'datasets').glob('fight_*.json')) or [settings.BASE_DIR / 'fight_0.json']
        expected = {}
        for path in paths:
            payload = load_json(path)
            import_fights(payload)
            for fight in payload['data']:
                for event in fight['steps']:
                    identifier = event['defender']
                    expected[identifier] = expected.get(identifier, 0) + event['damage']
        pks = list(Fight.objects.values_list('pk', flat=True))
        def run(pk):
            close_old_connections()
            try:
                replay_fight(pk)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(run, pks))
        for identifier, damage in expected.items():
            self.assertEqual(Person.objects.get(external_id=identifier).health, 100 - damage)
        self.assertFalse(FightEvent.objects.filter(processed=False).exists())

class RankMigrationTests(TransactionTestCase):
    def test_adding_rank_preserves_existing_people_including_zero(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('war', '0001_initial')])
        try:
            old = executor.loader.project_state([('war', '0001_initial')]).apps.get_model('war', 'Person')
            old.objects.create(external_id=0, name='Preserved person', age=24, health=88)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate([('war', '0003_alter_person_rank')])
        p = Person.objects.get(external_id=0)
        self.assertEqual((p.name, p.health, p.rank), ('Preserved person', 88, None))
