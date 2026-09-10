#!/bin/sh
# Migrate, collect the admin's static files, seed the categories once, then serve.
set -e
until python manage.py migrate --noinput; do echo "waiting for the database…"; sleep 2; done
python manage.py collectstatic --noinput >/dev/null
if [ "${FUWLOL_SEED_DEMO:-0}" = "1" ]; then python manage.py seed_demo; fi
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-3}" --timeout 120 --access-logfile - --error-logfile -
