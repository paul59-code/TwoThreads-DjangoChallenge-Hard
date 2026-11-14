"""Real Celery thread pool integration; synthetic ranks stay in the test DB."""
import time
import uuid
from unittest.mock import patch
from celery.contrib.testing.worker import start_worker
from django.test import TransactionTestCase
from django.conf import settings
from coderun2026_starter.celery import app
from .data import import_people, import_fights, load_json
from .models import Person, Fight
from .services import dispatch_fights
from .tasks import simulate_fight

class CeleryWorkerTests(TransactionTestCase):
    def test_real_thread_worker_sqlite_broker_and_shared_soldier(self):
        import_people(load_json(settings.BASE_DIR / 'people.json'))
        Person.objects.update(rank='TEST ONLY — not competition drafting data')
        payload = load_json(settings.BASE_DIR / 'fight_0.json')
        import_fights({'data': [f for f in payload['data'] if f['fight_id'] in (1, 10)]})
        # Real SQLAlchemy/SQLite transport, real JSON messages, real threads.
        queue = 'war-tests-' + uuid.uuid4().hex
        with start_worker(app, pool='threads', concurrency=4, queues=[queue], perform_ping_check=False, shutdown_timeout=30):
            with patch.object(simulate_fight, 'delay', side_effect=lambda *args: simulate_fight.apply_async(args=args, queue=queue)):
                self.assertEqual(dispatch_fights(), 2)
                self.assertEqual(dispatch_fights(), 0)
                deadline = time.monotonic() + 30
                while Fight.objects.exclude(status='COMPLETED').exists():
                    if time.monotonic() > deadline:
                        self.fail(str(list(Fight.objects.values('status', 'error'))))
                    time.sleep(0.1)
        self.assertEqual(Person.objects.get(external_id=58).health, 49)
        self.assertEqual(len(set(Fight.objects.values_list('task_id', flat=True))), 2)
