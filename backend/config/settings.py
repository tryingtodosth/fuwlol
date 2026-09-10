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
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
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
    },
}

# A shared file cache so throttle counters survive restarts and are shared between
# Passenger workers on OVH (a per-process memory cache would multiply every rate).
CACHES = {'default': {
    'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
    'LOCATION': os.environ.get('FUWLOL_CACHE_DIR', BASE_DIR / 'cachedata'),
}}

CORS_ALLOWED_ORIGINS = [o for o in os.environ.get(
    'FUWLOL_CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',') if o]
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get('FUWLOL_CSRF_ORIGINS', '').split(',') if o]

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
