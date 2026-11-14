import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'local-coderun-development-key')
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'
ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'testserver']
INSTALLED_APPS = ['django.contrib.contenttypes', 'django.contrib.auth', 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'war']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'django.contrib.messages.middleware.MessageMiddleware']
ROOT_URLCONF = 'coderun2026_starter.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'coderun2026_starter.wsgi.application'
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3', 'TEST': {'NAME': BASE_DIR / 'test-war.sqlite3'}, 'OPTIONS': {'timeout': 20, 'transaction_mode': 'IMMEDIATE'}}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
USE_TZ = True
STATIC_URL = 'static/'
CELERY_BROKER_URL = 'sqla+sqlite:///' + (BASE_DIR / 'celery-broker.sqlite3').as_posix()
CELERY_RESULT_BACKEND = 'db+sqlite:///' + (BASE_DIR / 'celery-results.sqlite3').as_posix()
CELERY_TASK_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_RESULT_SERIALIZER = 'json'
CELERY_WORKER_POOL = 'threads'
CELERY_WORKER_CONCURRENCY = 16
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_TRANSPORT_OPTIONS = {'connect_args': {'timeout': 20}}
API_BASE_URL = 'https://coderun2026-csbwf4haa4d0gubu.westus3-01.azurewebsites.net/'
# Hard instructions do not specify these rules; configurable assumptions.
WAR_INITIAL_HEALTH = int(os.environ.get('WAR_INITIAL_HEALTH', '100'))
WAR_MIN_HEALTH = int(os.environ['WAR_MIN_HEALTH']) if 'WAR_MIN_HEALTH' in os.environ else None
