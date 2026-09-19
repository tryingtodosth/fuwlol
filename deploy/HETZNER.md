# fuw.lol on Hetzner Cloud (CX23, Coolify) behind Cloudflare

> **Superseded on 19.09.2026.** The site runs on an OVHcloud VPS-1 in Warsaw with plain
> Docker Compose and Caddy — see `deploy/OVH.md`. This file stays because it is still an
> accurate description of the Coolify setup, and `docker-compose.yml` (the build-it-here
> one it refers to) is still valid for local use; `docker-compose.prod.yml` is what the
> live site runs.

One box runs three containers from `docker-compose.yml`: `db` (Postgres 16), `api` (Django
+ gunicorn), `web` (nginx: the SvelteKit build, `/api` `/admin` `/static` `/share` and
`/sitemap.xml` proxied to the api, `/media` served straight from the shared uploads volume).
Everything is on ONE domain, so no CORS and `PUBLIC_API_BASE_URL=/api` is baked into the
build. Link previews need nothing from Traefik/Coolify either — they are a User-Agent match
inside `frontend/nginx.conf`, which this setup uses unchanged; see `deploy/OVH.md`.

## First deploy (Coolify)

1. Push the repo to GitHub; in Coolify add a **Docker Compose** resource pointing at it
   (compose file: `docker-compose.yml`). Coolify routes the domain to the `web` service on
   port 80; the `ports:` block of `web` is only for a plain-docker setup.
2. Environment (Coolify → Environment Variables), from `.env.example`:
   `POSTGRES_PASSWORD`, `FUWLOL_SECRET_KEY` (50+ random chars), `FUWLOL_DOMAIN=fuw.lol`,
   the `FUWLOL_EMAIL_*` values of your mail provider, and `FUWLOL_SEED_DEMO=1` for the very
   first start only (creates dziekan/doktorant/student + demo posts; set back to 0 after).
3. Domain: `https://fuw.lol` on the `web` service. Coolify's Traefik gets the Let's Encrypt
   certificate; with Cloudflare in front set Cloudflare SSL to **Full (strict)**.
4. Deploy. `api` waits for Postgres, migrates, collects the admin's static files, seeds if
   asked, then serves. Create your real admin: Coolify → `api` → Terminal →
   `python manage.py createsuperuser`.
5. Webhook: Coolify → the resource → Webhooks, paste into GitHub → every push to `main` redeploys.

Plain server without Coolify: `cp .env.example .env`, fill it, `docker compose up -d --build`;
put Caddy or Traefik in front of `localhost:8080` for TLS.

## Cloudflare

- DNS: A + AAAA for `fuw.lol` and `www` → the Hetzner IPs, proxied (orange cloud).
- SSL/TLS: Full (strict). Cache rule: bypass `/api/*`. Everything else may be cached.
- `FUWLOL_TRUST_PROXY=1` (set in the compose file) makes Django read `CF-Connecting-IP` /
  `X-Forwarded-For`, so per-IP throttles (registration, login, guest chat, reports) see the
  visitor and not the proxy. Only ever set it behind a proxy you control.
- Free-plan request limit is 100 MB; a post can carry 6 × 25 MB. Either accept the limit or
  lower `MAX_FILES_PER_POST` in `config/settings.py`.

## Mail

Hetzner blocks outbound port 25; use a provider's SMTP on 587 (Brevo, Resend, SES). Add the
provider's SPF and DKIM records for fuw.lol at the DNS, or verification mails land in spam
and the trusted tier never activates.

## Backups

Hetzner snapshots (+20%) cover the whole disk. Also dump the database nightly:
`docker compose exec db pg_dump -U fuwlol fuwlol | gzip > /backup/fuwlol-$(date +%F).sql.gz`
(cron on the host), and copy the `media` volume — or move uploads to Hetzner Object Storage /
Cloudflare R2 via django-storages when they outgrow the disk.

## Firewall

Hetzner Cloud Firewall: inbound 22 (your IP only), 80, 443. SSH keys only. Coolify's own
dashboard on its own subdomain with 2FA.

## Not verified here

The images were written on a machine without Docker: the Python side (Postgres settings,
gunicorn, WhiteNoise, the real-IP middleware) is tested, the compose file parses, but the
first `docker compose build` runs on the server. If `web` fails to start, `nginx -t` inside
the container shows why.
