from django.core.management.base import BaseCommand, CommandError
from war.services import dispatch_fights

class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--recover', action='store_true')
    def handle(self, *args, **options):
        try:
            count = dispatch_fights(options['recover'])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f'Queued {count} separate fight tasks')
