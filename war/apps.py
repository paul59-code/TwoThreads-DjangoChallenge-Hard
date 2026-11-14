from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _tune_sqlite(sender, connection, **kwargs):
    # WAL: cititorii nu blochează scriitorul; busy_timeout: așteaptă în loc de "database is locked".
    if connection.vendor == "sqlite":
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=60000;")
        cursor.execute("PRAGMA synchronous=NORMAL;")


class WarConfig(AppConfig):
    name = "war"

    def ready(self):
        connection_created.connect(_tune_sqlite)
