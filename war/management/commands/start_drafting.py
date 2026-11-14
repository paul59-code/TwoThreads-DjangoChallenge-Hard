from pathlib import Path
from django.core.management.base import BaseCommand
from war.tasks import download_drafting, download_draft_batch, queue_draft
from war.models import DraftBatch
from war.data import api_url

class Command(BaseCommand):
    help = 'Start background downloading from an explicit real batch manifest, or recover missing batches'
    def add_arguments(self, parser):
        parser.add_argument('--source', default=api_url('draft/0'))
        parser.add_argument('--recover', action='store_true')
    def handle(self, *args, **options):
        if options['recover']:
            for batch in DraftBatch.objects.all():
                if batch.status == 'COMPLETED':
                    from war.tasks import schedule_next_draft
                    schedule_next_draft(batch, batch.payload)
                elif batch.payload is not None:
                    queue_draft(batch)
                    from war.tasks import schedule_next_draft
                    schedule_next_draft(batch, batch.payload)
                else:
                    download_draft_batch.delay(batch.pk)
            self.stdout.write('Republished unfinished batches')
        elif options['source']:
            source = options['source']
            if not source.startswith(('http://', 'https://')):
                source = str(Path(source).resolve())
            self.stdout.write(download_drafting.delay(source).id)
        else:
            from django.core.management.base import CommandError
            raise CommandError('Missing actual draft endpoint. Provide --source manifest.json or --recover.')
