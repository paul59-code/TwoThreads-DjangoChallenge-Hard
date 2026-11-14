from django.core.management.base import BaseCommand

from war.tasks import start_draft


class Command(BaseCommand):
    help = "Pornește drafting-ul: lanț de taskuri Celery de descărcare pe loturi, cu un task de drafting per lot."

    def add_arguments(self, parser):
        parser.add_argument("--first-batch", type=int, default=0)

    def handle(self, *args, **opts):
        start_draft(opts["first_batch"])
        self.stdout.write("Descărcarea a pornit în fundal (workerul Celery trebuie să ruleze).")
