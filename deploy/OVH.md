# Deploying fuw.lol on OVH shared hosting (cluster129, FTP user `fuwlolf`)

The site is two things: a **static SvelteKit build** (plain files) and a **Django API** that must
run as a Python process. OVH web hosting runs Python only on plans with the "Python (Passenger)"
option — Pro/Performance — via a `.ovhconfig` file; the Perso/Starter plans run PHP only.
Check the plan first: OVH panel → Hosting → *Multisite* / *General information* → "Passenger".

## Layout on the server (`/home/fuwlolf`)

```
www/                 ← the static build (frontend/build/*): index.html, 200.html, _app/…
www/.htaccess        ← SPA fallback + proxy of /api and /media (below)
api/                 ← the Django project: backend/* plus passenger_wsgi.py and .ovhconfig
api/media/           ← uploads (writeable)
api/db.sqlite3
```

## Steps

1. Build the frontend locally with the production API URL:
   `cd frontend && echo 'PUBLIC_API_BASE_URL=/api' > .env && npm run build` → upload `frontend/build/*` to `www/`.
2. Upload `backend/*` to `api/` (skip `media/`, `db.sqlite3`, `cachedata/`, `__pycache__`).
3. In `api/` create `passenger_wsgi.py`:
   ```python
   import os, sys
   sys.path.insert(0, os.path.dirname(__file__))
   os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
   os.environ.setdefault('FUWLOL_DEBUG', '0')
   os.environ.setdefault('FUWLOL_ALLOWED_HOSTS', 'fuw.lol,www.fuw.lol')
   os.environ.setdefault('FUWLOL_SECRET_KEY', 'PUT-A-LONG-RANDOM-STRING-HERE')
   os.environ.setdefault('FUWLOL_CSRF_ORIGINS', 'https://fuw.lol,https://www.fuw.lol')
   from config.wsgi import application
   ```
   and `.ovhconfig` (Python via Passenger):
   ```
   app.engine=passenger
   app.engine.version=python3
   http.firewall=none
   environment=production
   ```
   Then install the requirements into the user site with the SSH/CLI OVH gives you:
   `pip3 install --user -r requirements.txt`, run `python3 manage.py migrate`,
   `python3 manage.py collectstatic --noinput`, `python3 manage.py createsuperuser`.
4. Point the domain's "root folder" for `fuw.lol` at `www` and add a second multisite entry
   (or subdomain `api.fuw.lol`) pointing at `api` — Passenger serves the WSGI app from there.
   Then in `www/.htaccess`:
   ```apache
   RewriteEngine On
   # API + admin + media live on the Python multisite; proxy them under the same host if
   # mod_proxy is allowed on your plan, otherwise use https://api.fuw.lol and set
   # PUBLIC_API_BASE_URL=https://api.fuw.lol/api + FUWLOL_CORS_ORIGINS=https://fuw.lol.
   RewriteCond %{REQUEST_FILENAME} !-f
   RewriteCond %{REQUEST_FILENAME} !-d
   RewriteRule ^ 200.html [L]
   ```
5. Media in production: Django does not serve `/media/` when `FUWLOL_DEBUG=0`. Map
   `api/media/` as a static folder (multisite `media.fuw.lol` or an alias) and set
   `MEDIA_URL` accordingly — or keep DEBUG-style serving behind Passenger by adding
   `static(settings.MEDIA_URL, ...)` unconditionally in `config/urls.py` if the plan has no
   other way (slower, but works).

## Mail (verification links)

The trusted-user tier sends one e-mail per verification request. OVH hosting mail is plain
SMTP: set `FUWLOL_EMAIL_HOST=ssl0.ovh.net`, `FUWLOL_EMAIL_PORT=587`, `FUWLOL_EMAIL_USER` /
`FUWLOL_EMAIL_PASSWORD` (a mailbox created in the OVH panel, e.g. archiwum@fuw.lol),
`FUWLOL_FROM_EMAIL="fuw.lol <archiwum@fuw.lol>"` and `FUWLOL_SITE_URL=https://fuw.lol`
in `passenger_wsgi.py`'s environment. With `FUWLOL_DEBUG=0` and no host set, sending fails
loudly (503 on the request) rather than silently.

## If the plan has no Python

Cheapest workable alternative: keep the static build on OVH and run the API on any small VPS
or a free-tier PaaS; set `PUBLIC_API_BASE_URL` to that host and `FUWLOL_CORS_ORIGINS=https://fuw.lol`.
The code needs no change for that split — every request is a cross-origin `fetch` already.

## Not automated

No FTP upload script is included on purpose: the FTP password is not in the repo and the owner
uploads on their own schedule. `frontend/build/` and `backend/` are the two things to upload.
