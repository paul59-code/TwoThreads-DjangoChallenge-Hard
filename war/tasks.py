from pathlib import Path
from urllib.parse import urljoin
from celery import shared_task
from django.db import transaction, OperationalError
from .data import load_json, rows, TransientDownload, integer, api_url
from .models import DraftBatch, Person, Fight
from .services import db_retry, replay_fight

@shared_task(bind=True, max_retries=5, retry_backoff=True, retry_jitter=True)
def simulate_fight(self, fight_id):
    try:
        return replay_fight(fight_id)
    except OperationalError as exc:
        if any(s in str(exc).lower() for s in ('locked', 'busy')) and self.request.retries < self.max_retries:
            import random
            raise self.retry(exc=exc, countdown=random.uniform(0, min(2 ** self.request.retries, 30)))
        db_retry(lambda: Fight.objects.filter(pk=fight_id).exclude(status='COMPLETED').update(status='FAILED', queued=False, error=str(exc)))
        raise
    except Exception as exc:
        db_retry(lambda: Fight.objects.filter(pk=fight_id).exclude(status='COMPLETED').update(status='FAILED', queued=False, error=str(exc)))
        raise

def draft_records(payload):
    """Actual /draft/N schema uses person id, string rank and integer health."""
    records = rows(payload)
    ids = set()
    for record in records:
        identifier = integer(record['id'], 'draft id')
        if identifier in ids or 'rank' not in record or record['rank'] is None:
            raise ValueError('Each draft record needs a unique id and nonnull rank')
        if not isinstance(record['rank'], str) or not record['rank'] or len(record['rank']) > 100:
            raise ValueError('Draft rank must be a nonempty string of at most 100 characters')
        ids.add(identifier)
    return records

@shared_task(bind=True, max_retries=5, retry_backoff=True, retry_jitter=True)
def draft_batch(self, batch_id):
    try:
        def apply():
            with transaction.atomic():
                batch = DraftBatch.objects.get(pk=batch_id)
                if batch.status == 'COMPLETED':
                    return 0
                records = draft_records(batch.payload)
                people = {p.external_id: p for p in Person.objects.filter(external_id__in=[r['id'] for r in records])}
                for r in records:
                    p = people[r['id']]
                    p.rank = r['rank']
                    if 'key' in r:
                        p.key = r['key']
                    if 'health' in r:
                        if p.attacks.filter(processed=True).exists() or p.defences.filter(processed=True).exists():
                            raise ValueError('Cannot overwrite health after simulation')
                        p.health = integer(r['health'], 'health')
                    p.attributes.update({k: v for k, v in r.items() if k not in ('id', 'rank', 'key', 'health')})
                Person.objects.bulk_update(people.values(), ['rank', 'key', 'health', 'attributes'])
                batch.status = 'COMPLETED'
                batch.draft_task_id = self.request.id or ''
                batch.error = ''
                batch.save()
                return len(records)
        return db_retry(apply)
    except Exception as exc:
        db_retry(lambda: DraftBatch.objects.filter(pk=batch_id).update(status='FAILED', error=str(exc)))
        raise

def queue_draft(batch):
    result = draft_batch.delay(batch.pk)
    db_retry(lambda: DraftBatch.objects.filter(pk=batch.pk).update(draft_task_id=result.id))

def accept_draft_download(batch, payload, task_id):
    if batch.source.startswith(api_url('draft/')) and 'next_batch' not in payload:
        raise ValueError('Missing next_batch in actual drafting response; cannot confirm completion')
    draft_records(payload)
    db_retry(lambda: DraftBatch.objects.filter(pk=batch.pk).update(payload=payload, status='DOWNLOADED', error='', download_task_id=task_id or ''))
    queue_draft(batch)  # Before discovering/downloading any later batch.
    schedule_next_draft(batch, payload)

def schedule_next_draft(batch, payload):
    if 'next_batch' in payload:
        following = payload['next_batch']
        if following is not None and following is not False:
            integer(following, 'next_batch')
            if following < 0:
                raise ValueError('Invalid draft next_batch')
            source = api_url(f'draft/{following}')
            current_index = batch.source.rstrip('/').split('/')[-1]
            if source == batch.source or (current_index.isdigit() and following <= int(current_index)):
                raise ValueError('Cyclic drafting pagination')
            next_batch, _ = db_retry(lambda: DraftBatch.objects.get_or_create(source=source))
            if next_batch.status != 'COMPLETED':
                task = download_draft_batch.delay(next_batch.pk)
                db_retry(lambda: DraftBatch.objects.filter(pk=next_batch.pk).update(download_task_id=task.id))

@shared_task(bind=True, max_retries=5, autoretry_for=(TransientDownload,), retry_backoff=True, retry_backoff_max=60, retry_jitter=True)
def download_draft_batch(self, batch_id):
    batch = DraftBatch.objects.get(pk=batch_id)
    if batch.status == 'COMPLETED':
        schedule_next_draft(batch, batch.payload)
        return
    try:
        payload = batch.payload if batch.payload is not None else load_json(batch.source)
        accept_draft_download(batch, payload, self.request.id)
    except TransientDownload as exc:
        db_retry(lambda: DraftBatch.objects.filter(pk=batch_id).update(status='FAILED' if self.request.retries >= self.max_retries else 'RETRYING', error=str(exc)))
        raise
    except Exception as exc:
        db_retry(lambda: DraftBatch.objects.filter(pk=batch_id).update(status='FAILED', error=str(exc)))
        raise

@shared_task(bind=True, max_retries=5, autoretry_for=(TransientDownload,), retry_backoff=True, retry_backoff_max=60, retry_jitter=True)
def download_drafting(self, source):
    """Download actual first batch and follow next_batch, or explicit manifest."""
    manifest = load_json(source)
    if isinstance(manifest, dict) and isinstance(manifest.get('data'), list):
        if 'next_batch' not in manifest:
            raise ValueError('Actual paginated drafting response requires next_batch')
        batch, _ = db_retry(lambda: DraftBatch.objects.get_or_create(source=source))
        if batch.status != 'COMPLETED':
            accept_draft_download(batch, manifest, self.request.id)
        else:
            schedule_next_draft(batch, manifest)
        return [batch.pk]
    if not isinstance(manifest, dict) or not isinstance(manifest.get('batches'), list) or not manifest['batches']:
        raise ValueError('Expected /draft/N data with next_batch, or an explicit batches manifest')
    ids = []
    for location in manifest['batches']:
        if not isinstance(location, str):
            raise ValueError('batches must contain actual URLs or file paths')
        if source.startswith(('http://', 'https://')):
            location = urljoin(source, location)
        else:
            location = location if location.startswith(('http://', 'https://')) else str((Path(source).resolve().parent / location).resolve())
        batch, _ = db_retry(lambda: DraftBatch.objects.get_or_create(source=location))
        if batch.status != 'COMPLETED':
            task = download_draft_batch.delay(batch.pk)
            db_retry(lambda: DraftBatch.objects.filter(pk=batch.pk).update(download_task_id=task.id))
        ids.append(batch.pk)
    return ids
