"""Global health, exactly-once event application, short SQLite write transactions."""
import random
import time
from django.conf import settings
from django.db import transaction, OperationalError
from django.db.models import F
from django.db.models.functions import Greatest
from .models import Person, Fight, FightEvent

def db_retry(fn):
    for attempt in range(7):
        try:
            return fn()
        except OperationalError as exc:
            if not any(word in str(exc).lower() for word in ('locked', 'busy')) or attempt == 6:
                raise
            time.sleep(min(0.025 * 2 ** attempt, 1) + random.uniform(0, 0.025))

def apply_next_event(fight_id):
    # BEGIN IMMEDIATE serializes only this short write transaction on SQLite.
    # Never use SQLite's ineffective select_for_update() as a lock.
    with transaction.atomic():
        fight = Fight.objects.get(pk=fight_id)
        if fight.status == 'COMPLETED':
            return False
        if not fight.initial_health:
            fight.initial_health = {str(p.external_id): p.health for p in Person.objects.filter(pk__in=[fight.blue_soldier_id, fight.red_soldier_id])}
        fight.status = 'RUNNING'
        fight.error = ''
        event = fight.events.filter(processed=False).order_by('event_index').first()
        if event:
            event.clean()
            event.health_before = Person.objects.values_list('health', flat=True).get(pk=event.defender_id)
            expression = F('health') - event.damage
            if settings.WAR_MIN_HEALTH is not None:
                expression = Greatest(expression, settings.WAR_MIN_HEALTH)
            Person.objects.filter(pk=event.defender_id).update(health=expression)
            event.health_after = Person.objects.values_list('health', flat=True).get(pk=event.defender_id)
            event.processed = True
            event.save(update_fields=['health_before', 'health_after', 'processed'])
        else:
            fight.final_health = {str(p.external_id): p.health for p in Person.objects.filter(pk__in=[fight.blue_soldier_id, fight.red_soldier_id])}
            fight.status = 'COMPLETED'
            fight.queued = False
            # No unsupported win/death rules: report exact damage in this fight.
            totals = {}
            for external_id, damage in fight.events.values_list('defender__external_id', 'damage'):
                key = str(external_id)
                totals[key] = totals.get(key, 0) + damage
            fight.result = 'Damage received: ' + ', '.join(f'#{k}: {v}' for k, v in totals.items())
        fight.save(update_fields=['initial_health', 'final_health', 'status', 'queued', 'result', 'error'])
        return event is not None

def replay_fight(fight_id):
    def validate():
        fight = Fight.objects.get(pk=fight_id)
        if not fight.events.exists():
            raise ValueError('Fight has no imported events')
        if Person.objects.filter(pk__in=[fight.blue_soldier_id, fight.red_soldier_id], rank__isnull=True).exists():
            raise ValueError('Participants have not been drafted; real rank data is required')
    db_retry(validate)
    while db_retry(lambda: apply_next_event(fight_id)):
        pass
    return fight_id

def dispatch_fights(recover=False):
    from .tasks import simulate_fight
    # Persist intent before publishing. --recover republishes crash/interrupted
    # deliveries safely, since event application is database-idempotent.
    ids = list(Fight.objects.exclude(status='COMPLETED').values_list('pk', flat=True))
    if Person.objects.filter(rank__isnull=True).filter(pk__in=Fight.objects.filter(pk__in=ids).values('blue_soldier_id')).exists() or Person.objects.filter(rank__isnull=True).filter(pk__in=Fight.objects.filter(pk__in=ids).values('red_soldier_id')).exists():
        raise ValueError('Draft all fight participants before starting simulation')
    count = 0
    for pk in ids:
        def claim():
            with transaction.atomic():
                query = Fight.objects.filter(pk=pk).exclude(status='COMPLETED')
                if not recover:
                    query = query.filter(queued=False)
                return query.update(queued=True)
        if db_retry(claim):
            try:
                result = simulate_fight.delay(pk)
                db_retry(lambda: Fight.objects.filter(pk=pk).update(task_id=result.id))
                count += 1
            except Exception:
                db_retry(lambda: Fight.objects.filter(pk=pk).update(queued=False))
                raise
    return count
