from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "dev-only-key-change-me"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "war",
]

MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        # Scrierile paralele din SQLite se blochează între ele; așteptăm în loc să eșuăm.
        # IMMEDIATE: tranzacția ia blocarea de scriere de la început și așteaptă la coadă,
        # în loc să eșueze la trecerea de la citire la scriere ("database is locked").
        "OPTIONS": {"timeout": 60, "transaction_mode": "IMMEDIATE"},
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "static/"
USE_TZ = True

# Sursa datelor (folosită de `manage.py load_data`)
API_BASE_URL = "https://coderun2026-csbwf4haa4d0gubu.westus3-01.azurewebsites.net"

# --- Celery -------------------------------------------------------------------------------
# Broker: memory:// merge doar într-un singur proces (teste, CELERY_EAGER=1).
# Pentru un worker separat folosește Redis, de ex.: set CELERY_BROKER_URL=redis://localhost:6379/0
import os  # noqa: E402

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "memory://")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "cache+memory://")
CELERY_TASK_ALWAYS_EAGER = os.environ.get("CELERY_EAGER") == "1"
CELERY_TASK_EAGER_PROPAGATES = False  # în modul eager, un retry reușit nu trebuie să arunce Retry
CELERY_TASK_ACKS_LATE = True          # un task pierdut la o cădere a workerului se reia
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# --- Drafting în loturi -------------------------------------------------------------------
DRAFT_FETCH_TIMEOUT = int(os.environ.get("DRAFT_FETCH_TIMEOUT", "60"))  # secunde; serverul e lent, peste ele cererea se reia
# Adresa unui lot; {batch} e numărul lotului (0, 1, 2 ... cum îl dă `next_batch`).
# TODO: pune adresa reală (cea de unde ai primit lotul cu "next_batch").
DRAFT_BATCH_URL = os.environ.get("DRAFT_BATCH_URL", API_BASE_URL + "/draft?batch={batch}")

# Erorile taskurilor (inclusiv în modul eager) se afișează în consolă.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}
