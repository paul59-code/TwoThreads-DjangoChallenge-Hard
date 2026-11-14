from django.core.management.base import BaseCommand, CommandError
from war.data import import_all_fights, api_url

class Command(BaseCommand):
    help = 'Import every fight batch, following the actual next_batch metadata'
    def add_arguments(self, parser):
        parser.add_argument('--source', default=api_url('fight/0'))
        parser.add_argument('--cache-dir', default='datasets')
        parser.add_argument('--local-only', action='store_true', help='Follow cached fight_N.json files without network access; report missing batches')
    def handle(self, *args, **options):
        try:
            count = import_all_fights(options['source'], options['cache_dir'], options['local_only'])
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f'Imported/verified {count} fights; reached explicit end of pagination')
