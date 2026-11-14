from django.conf import settings
from django.core.management.base import BaseCommand

from war.models import Person
from war.tasks import start_draft


class Command(BaseCommand):
    help = "Pornește drafting-ul: lanț de taskuri Celery de descărcare pe loturi, cu un task de drafting per lot."

    def add_arguments(self, parser):
        parser.add_argument("--first-batch", type=int, default=0)

    def handle(self, *args, **opts):
        self.stdout.write(f"Adresa loturilor: {settings.DRAFT_BATCH_URL}")
        result = start_draft(opts["first_batch"])
        if settings.CELERY_TASK_ALWAYS_EAGER:
            # modul eager: totul a rulat deja; arătăm ce s-a întâmplat, ca o eroare să nu treacă neobservată
            if result.failed():
                self.stdout.write(self.style.ERROR(f"Lotul {opts['first_batch']} a eșuat: {result.result!r}"))
            else:
                self.stdout.write(f"Primul lot: {result.result}")
        else:
            self.stdout.write("Taskurile au fost trimise; workerul Celery le execută în fundal.")
        total = Person.objects.count()
        ranked = Person.objects.filter(rank__isnull=False).count()
        self.stdout.write(f"Persoane în baza de date: {total}, cu grad: {ranked}")
        for p in Person.objects.exclude(key__isnull=True).exclude(key=""):
            self.stdout.write(self.style.SUCCESS(f"Cheie pentru pasul următor: {p.name} -> {p.key}"))
