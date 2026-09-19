"""fuw.lol — settings. Everything deployment-specific comes from the environment
(see deploy/OVH.md); the defaults are for local development only."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

_DEV_KEY = 'dev-only-insecure-key-change-me'
SECRET_KEY = os.environ.get('FUWLOL_SECRET_KEY', _DEV_KEY)
# On by default for a clone (./run.sh, manage.py runserver); the container image sets
# FUWLOL_DEBUG=0 (backend/Dockerfile) so a `docker run` is never accidentally a debug server.
DEBUG = os.environ.get('FUWLOL_DEBUG', '1') == '1'
if not DEBUG and SECRET_KEY == _DEV_KEY:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured('FUWLOL_SECRET_KEY must be set when FUWLOL_DEBUG=0.')
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
    'consent',
    'escalation',
    'portraits',
    'share',
]

# See config/middleware.py for what each of these means and when it is safe.
FUWLOL_TRUST_PROXY = os.environ.get('FUWLOL_TRUST_PROXY', '0') == '1'
FUWLOL_PROXY_HOPS = int(os.environ.get('FUWLOL_PROXY_HOPS', '1'))
FUWLOL_CLOUDFLARE = os.environ.get('FUWLOL_CLOUDFLARE', '0') == '1'
# Salt for the stored hash of a visitor's address (board/models.py). Separate from
# SECRET_KEY so that rotating the key does not break "same place?" correlation, and so
# that whoever holds the key does not automatically hold the salt.
FUWLOL_IP_SALT = os.environ.get('FUWLOL_IP_SALT') or SECRET_KEY

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
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
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
        'login_user': '10/min',  # per submitted username, on top of the per-IP rate
        'comment_create': '60/hour',
        'post_create': '30/hour',
        'report': '20/hour',
        'board_anon': '20/hour',
        'board_user': '60/hour',
        'board_report': '20/hour',
        'escalate': '10/day',
        'presign': '60/hour',  # one per file; a six-file post costs six
        'suggest': '20/hour',  # edit suggestions: a real correction is rare, a flood is not
        'verify': '5/hour',  # institutional-address confirmation mails, per user
        # „Jesteś tą osobą?” (consent/views.py). Both send mail to somebody ELSE's
        # mailbox, so the rate limits what one visitor can do TO a third party
        # rather than what they can do to us. Three an hour is a person retrying a
        # form twice; it is not a way to post a lecturer's inbox.
        'claim_request': '3/hour',
        'claim_manage': '3/hour',
        # Portraits (portraits/views.py). An upload is 25 MB of decoded pixels plus a
        # moderator's attention; a vote is one row, but a gallery voted by a script is
        # not a vote. Both per IP, like every other scope here.
        'portrait_upload': '10/hour',
        'portrait_vote': '60/hour',
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
DEFAULT_FROM_EMAIL = os.environ.get('FUWLOL_FROM_EMAIL', 'FUW <no-reply@fuw.lol>')
# Deliberately NOT the same address. What we send FROM is a Brevo-verified relay sender
# that nobody reads; where a person (or Dyżurnet.pl, or somebody exercising a RODO right)
# should WRITE is a mailbox a human opens. Conflating them puts "no-reply@" on the DSA
# art. 12 contact point, which is the one address that must actually answer.
FUWLOL_CONTACT_EMAIL = os.environ.get('FUWLOL_CONTACT_EMAIL', 'admin@fuw.lol')
# Where the confirmation link points (the SvelteKit site, which has the /potwierdz page).
FUWLOL_SITE_URL = os.environ.get('FUWLOL_SITE_URL', 'http://localhost:5173').rstrip('/')
# Link previews (share/). FUWLOL_SPA_INDEX points at the built SvelteKit shell when Django can
# read it (mode a: the tags are spliced into the real page for everybody); unset, share/ serves
# its own minimal page to crawlers (mode b — what runs today, see deploy/OVH.md).
FUWLOL_SPA_INDEX = os.environ.get('FUWLOL_SPA_INDEX', '')
FUWLOL_SHARE_REDIRECT_HUMANS = os.environ.get('FUWLOL_SHARE_REDIRECT_HUMANS', '1')

CORS_ALLOWED_ORIGINS = [o for o in os.environ.get(
    'FUWLOL_CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',') if o]
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get('FUWLOL_CSRF_ORIGINS', '').split(',') if o]

STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}

# --- Cloudflare R2 (config/r2.py) ------------------------------------------------------
# Attachment bytes go browser -> R2 directly, through a presigned PUT, so a 25 MB upload
# never occupies a gunicorn worker or the VPS's 500 Mbps uplink, and never meets
# Cloudflare's 100 MB proxy ceiling (one file per request, six requests per post).
#
# UNSET IS A SUPPORTED CONFIGURATION and is what a bare clone and the whole test suite run
# with: uploads then keep going through Django to MEDIA_ROOT exactly as before, and the
# presign endpoint answers 503 rather than pretending. What is NOT supported is a
# deployment that stores attachments in R2 without FUWLOL_R2_* — see config/r2.py.
R2_BUCKET = os.environ.get('FUWLOL_R2_BUCKET', '')
R2_ENDPOINT_URL = os.environ.get('FUWLOL_R2_ENDPOINT_URL', '')
R2_ACCESS_KEY_ID = os.environ.get('FUWLOL_R2_ACCESS_KEY_ID', '')
R2_SECRET_ACCESS_KEY = os.environ.get('FUWLOL_R2_SECRET_ACCESS_KEY', '')
# The hostname Cloudflare serves the public prefix from (a custom domain on the bucket).
R2_PUBLIC_BASE_URL = os.environ.get('FUWLOL_R2_PUBLIC_BASE_URL', '').rstrip('/')
# A SEPARATE, PRIVATE bucket for quarantined objects — no custom domain, no public access.
# An R2 custom domain serves the whole bucket, so a quarantined object left in the public
# one stays fetchable by anyone who knows its key. See config/r2.py.
R2_QUARANTINE_BUCKET = os.environ.get('FUWLOL_R2_QUARANTINE_BUCKET', '')

# Cache purge for a quarantined object (escalation/cdn.py). Without these an escalation
# still hides the content everywhere this origin controls, and logs that the edge copy was
# not purged — it does not pretend the purge happened.
CLOUDFLARE_ZONE_ID = os.environ.get('FUWLOL_CLOUDFLARE_ZONE_ID', '')
CLOUDFLARE_PURGE_TOKEN = os.environ.get('FUWLOL_CLOUDFLARE_PURGE_TOKEN', '')

# How long the uploader's address and user-agent are kept on a Post (archive/models.py).
# They exist for exactly one purpose — being the identifying half of a Dyzurnet.pl report
# under art. 18 DSA — and a raw address kept past its usefulness is a liability, not an
# asset. `manage.py forget_submitter_ips` enforces this; run it from cron.
SUBMITTER_IP_RETENTION_DAYS = int(os.environ.get('FUWLOL_SUBMITTER_IP_RETENTION_DAYS', '90'))

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    USE_X_FORWARDED_HOST = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
    # HSTS is set here for the /api and /admin responses gunicorn serves; the SPA's own
    # headers come from frontend/nginx.conf. Preload is left off on purpose (irreversible).
    SECURE_HSTS_SECONDS = int(os.environ.get('FUWLOL_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# The escalation app's audit trail (escalation/services.py): every escalate/approve/decline
# writes an Escalation row AND a line here, so a database-only compromise cannot erase the
# trail on its own. Deliberately not routed through the 'django' logger's own config.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {'security': {'handlers': ['console'], 'level': 'INFO', 'propagate': False}},
}
