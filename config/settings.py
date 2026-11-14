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
