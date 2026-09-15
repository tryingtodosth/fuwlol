"""fuw.lol — settings. Everything deployment-specific comes from the environment
(see deploy/OVH.md); the defaults are for local development only."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('FUWLOL_SECRET_KEY', 'dev-only-insecure-key-change-me')
DEBUG = os.environ.get('FUWLOL_DEBUG', '1') == '1'
ALLOWED_HOSTS = [h for h in os.environ.get('FUWLOL_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'accounts',
    'archive',
    'board',
    'escalation',
]

FUWLOL_TRUST_PROXY = os.environ.get('FUWLOL_TRUST_PROXY', '0') == '1'

MIDDLEWARE = [
    'config.middleware.RealIpMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # serves STATIC_ROOT (the admin) from gunicorn
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]
WSGI_APPLICATION = 'config.wsgi.application'

# SQLite by default (a clone, ./setup.sh); Postgres in production via DATABASE_URL, e.g.
# postgres://fuwlol:secret@db:5432/fuwlol (see docker-compose.yml).
if os.environ.get('DATABASE_URL'):
    from urllib.parse import urlparse
    _u = urlparse(os.environ['DATABASE_URL'])
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': _u.path.lstrip('/'), 'USER': _u.username, 'PASSWORD': _u.password,
        'HOST': _u.hostname, 'PORT': _u.port or 5432, 'CONN_MAX_AGE': 60,
    }}
else:
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.environ.get('FUWLOL_DB_PATH', BASE_DIR / 'db.sqlite3'),
        'OPTIONS': {'timeout': 20},
    }}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
]

LANGUAGE_CODE = 'pl'
TIME_ZONE = 'Europe/Warsaw'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = os.environ.get('FUWLOL_STATIC_ROOT', BASE_DIR / 'staticfiles')
MEDIA_URL = '/media/'
MEDIA_ROOT = os.environ.get('FUWLOL_MEDIA_ROOT', BASE_DIR / 'media')
# Escalation evidence (escalation/evidence.py) — outside MEDIA_ROOT on purpose: nothing here
# is ever served by path, only streamed through a view that re-checks is_head_admin per
# request (escalation/views.py). Never point this inside a directory Nginx/whitenoise serves.
EVIDENCE_ROOT = os.environ.get('FUWLOL_EVIDENCE_ROOT', BASE_DIR / 'evidence')
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Uploads: 25 MB per file, 6 files per post. Checked in archive/validators.py.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_FILES_PER_POST = 6
DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.AllowAny'],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '300/min',
        'user': '600/min',
        'register': '10/hour',
        'login': '20/min',
        'post_create': '30/hour',
        'report': '20/hour',
        'board_anon': '20/hour',
        'board_user': '60/hour',
        'board_report': '20/hour',
        'escalate': '10/day',
        'verify': '5/hour',  # institutional-address confirmation mails, per user
    },
}

# A shared file cache so throttle counters survive restarts and are shared between
# Passenger workers on OVH (a per-process memory cache would multiply every rate).
CACHES = {'default': {
    'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
    'LOCATION': os.environ.get('FUWLOL_CACHE_DIR', BASE_DIR / 'cachedata'),
}}

# Mail — the institutional-address confirmation link (accounts/views.py). Local dev prints
# it to the console; production talks SMTP. OVH hosting mail is SMTP on ssl0.ovh.net:587
# (STARTTLS) with a mailbox created in the OVH panel — see deploy/OVH.md; the credentials
# come from FUWLOL_EMAIL_USER / FUWLOL_EMAIL_PASSWORD in the environment, never this file.
EMAIL_BACKEND = os.environ.get('FUWLOL_EMAIL_BACKEND') or (
    'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.environ.get('FUWLOL_EMAIL_HOST', 'ssl0.ovh.net')
EMAIL_PORT = int(os.environ.get('FUWLOL_EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('FUWLOL_EMAIL_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('FUWLOL_EMAIL_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('FUWLOL_EMAIL_USE_TLS', '1') == '1'
DEFAULT_FROM_EMAIL = os.environ.get('FUWLOL_FROM_EMAIL', 'fuw.lol <archiwum@fuw.lol>')
# Where the confirmation link points (the SvelteKit site, which has the /potwierdz page).
FUWLOL_SITE_URL = os.environ.get('FUWLOL_SITE_URL', 'http://localhost:5173').rstrip('/')

CORS_ALLOWED_ORIGINS = [o for o in os.environ.get(
    'FUWLOL_CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',') if o]
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get('FUWLOL_CSRF_ORIGINS', '').split(',') if o]

STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    USE_X_FORWARDED_HOST = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# The escalation app's audit trail (escalation/services.py): every escalate/approve/decline
# writes an Escalation row AND a line here, so a database-only compromise cannot erase the
# trail on its own. Deliberately not routed through the 'django' logger's own config.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {'security': {'handlers': ['console'], 'level': 'INFO', 'propagate': False}},
}
