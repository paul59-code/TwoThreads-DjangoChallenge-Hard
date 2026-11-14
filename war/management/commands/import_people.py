from django.core.management.base import BaseCommand, CommandError
from war.data import import_people, load_json, api_url

class Command(BaseCommand):
    help = 'Idempotently import people from a file or the live API'
    def add_arguments(self, parser):
        parser.add_argument('--source', default=api_url('people'))
    def handle(self, *args, **options):
        try:
            count = import_people(load_json(options['source']))
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f'Imported/verified {count} people')
