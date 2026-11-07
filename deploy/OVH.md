# fuw.lol on OVHcloud VPS-1 (Warsaw) — the runbook

`settings.py` has pointed at this file since before it existed. Here it is.

```
            visitor
               │  https
        ┌──────▼───────────────┐
        │ Cloudflare (free)    │  proxy, edge cache, Bot Fight Mode, DDoS
        │ WAW edge             │  DNS for fuw.lol lives here
        └──────┬───────────────┘
               │  only these ranges may reach the origin (deploy/firewall.sh)
      ┌────────▼─────────────────────────────────────────────┐
      │ OVHcloud VPS-1 2027 · 146.59.103.167 · Warsaw WAW    │
      │ 2 vCores · 4 GB · 40 GB NVMe · Ubuntu 26.04          │
      │                                                      │
      │  caddy  ── TLS (Cloudflare origin cert) ──►  web     │
      │                                    (nginx + SPA)     │
      │                                             │        │
      │                                          api (gunicorn)
      │                                             │        │
      │                                            db (postgres 16)
      └──────────────────────────────────────────────────────┘
                                              │
                                              ▼
                                       Brevo SMTP :587
                                       verification mail
                                       (OVH blocks :25)
```

There is no object storage. Attachments live on the `fuwlol_media` volume and nginx serves
them under `/media/`; the nightly restic backup goes to `/srv/fuwlol/restic-repo` on the
same disk. Until 02.11.2026 the backup lived in Cloudflare R2, and uploads were wired to
R2 as well, though no attachment was ever stored there — see "Backups" for what dropping it
costs.

Human mail (`archiwum@`, `kontakt@`, `abuse@`) stays on **OVH mail**, whose MX records were
already live on this domain before any of this — one fewer service to run. Brevo only ever
sends: the address-verification message that decides who joins the trusted tier is the one
message that must not land in spam, and a shared-host SMTP reputation is not where to
gamble that.

## What runs where

| | |
|---|---|
| Compose file | `/srv/fuwlol/docker-compose.prod.yml` (shipped by CI, never edited on the box) |
| Secrets | `/srv/fuwlol/.env` (**never** in git, never touched by a deploy) |
| Origin cert | `/srv/fuwlol/secrets/origin.{crt,key}` |
| Images | `ghcr.io/tryingtodosth/fuwlol-{api,web}` — built and tested by Actions, only pulled here |
| Data | docker volumes `fuwlol_{pgdata,media,cachedata,evidence}` |

## One-time: what a person has to do in a browser

1. **Cloudflare.** Add `fuw.lol`, change the nameservers at the OVH registrar to the pair
   Cloudflare gives. When the import finishes, check the `mx1/mx2/mx3.mail.ovh.net` records
   came across and are **DNS-only (grey cloud)** — proxying MX breaks mail. Then:

   | Type | Name | Value | Proxy |
   |---|---|---|---|
   | A | `fuw.lol` | `146.59.103.167` | proxied |
   | AAAA | `fuw.lol` | `2001:41d0:601:1100::9fa9` | proxied |
   | CNAME | `www` | `fuw.lol` | proxied |
   | MX | `fuw.lol` | the three existing OVH values | DNS only |
   | TXT | `fuw.lol` | SPF including **both** OVH and Brevo | DNS only |
   | TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:admin@fuw.lol` | DNS only |

   SSL/TLS mode: **Full (strict)**. Cache rule: bypass `/api/*`.

   **Start DMARC at `p=none`.** Going straight to `p=reject` before DKIM is confirmed
   working kills your own verification mail, silently, and the failure looks like "the
   trusted tier is broken" rather than like a DNS mistake. Tighten after a clean week of
   `rua` reports.

2. **Origin certificate.** Cloudflare → SSL/TLS → Origin Server → Create Certificate, for
   `fuw.lol` and `*.fuw.lol`. Save the two PEM blocks as `origin.crt` and `origin.key`.
   This is not Let's Encrypt on purpose: the firewall lets only Cloudflare reach 80/443, so
   an ACME HTTP-01 challenge — which arrives from Let's Encrypt directly — could never be
   answered. An origin certificate is trusted by exactly the set of clients that can
   connect, which is the set that matters.

3. **Brevo.** Verify `fuw.lol`, add their SPF and DKIM records, create an SMTP key.

4. **GitHub → Settings → Secrets and variables → Actions:** `DEPLOY_SSH_KEY`,
   `DEPLOY_HOST` = `146.59.103.167`, `DEPLOY_USER` = `deploy`.

## One-time: the box

```bash
# as root, once
adduser --disabled-password --gecos '' deploy
install -d -m700 -o deploy -g deploy /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/ && chown deploy:deploy /home/deploy/.ssh/authorized_keys
usermod -aG docker deploy
install -d -o deploy -g deploy /srv/fuwlol /srv/fuwlol/deploy /srv/fuwlol/secrets
install -d -m700 -o deploy -g deploy /srv/fuwlol/restic-repo
chmod 700 /srv/fuwlol/secrets

# docker (official repo; Ubuntu 26.04 "resolute" is supported)
apt-get update && apt-get install -y ca-certificates curl restic
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# ssh: keys only
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/;s/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
systemctl reload ssh

# unattended security updates
apt-get install -y unattended-upgrades && dpkg-reconfigure -plow unattended-upgrades
```

### `/srv/fuwlol/.env`

```ini
POSTGRES_PASSWORD=          # openssl rand -base64 33
FUWLOL_SECRET_KEY=          # python -c 'import secrets;print(secrets.token_urlsafe(50))'
FUWLOL_IP_SALT=             # openssl rand -hex 32 — rotate this and chat ip_hashes stop correlating
FUWLOL_CLOUDFLARE_ZONE_ID=
FUWLOL_CLOUDFLARE_PURGE_TOKEN=
FUWLOL_EMAIL_HOST=smtp-relay.brevo.com
FUWLOL_EMAIL_USER=
FUWLOL_EMAIL_PASSWORD=
FUWLOL_FROM_EMAIL="FUW <no-reply@fuw.lol>"   # quoted: deploy/backup.sh SOURCES this file, and < is a redirect
FUWLOL_CONTACT_EMAIL=admin@fuw.lol           # the one OVH mailbox — what a human reads
SKOKI_TAG=latest             # WUM (fuw.lol/fum) — a commit of the MEDAPP repository, not this one
LSD_TAG=lsd-latest           # LSD (fuw.lol/lsd) — the second MedApp copy; the medapp repository's lsd-<sha> tags
RESTIC_REPOSITORY=/srv/fuwlol/restic-repo
RESTIC_PASSWORD_FILE=/srv/fuwlol/secrets/restic.pass
```

No `FUWLOL_R2_*`: with them unset `config/r2.is_configured()` is false, every upload goes
through Django onto the media volume, and quarantine moves files on that volume. Setting
them again would switch R2 back on — don't, unless the buckets are recreated first.

`chmod 600 /srv/fuwlol/.env`. **Keep `RESTIC_PASSWORD_FILE`'s contents somewhere that is
not this server** — a backup you cannot decrypt is not a backup, and the server is the one
machine guaranteed to be missing when you need it.

`FUWLOL_SITE_URL` (`https://fuw.lol`, set in `docker-compose.prod.yml`; default
`http://localhost:5173`) is the host every server-built link points at — the verification
mail, the consent claims, and `og:url`/`canonical` in the link previews. Running dev on the
alternate ports means setting it to `http://localhost:5273`, or every link says 5173.

### Firewall, and the boot/refresh units

```bash
/srv/fuwlol/deploy/firewall.sh            # apply now

cat > /etc/systemd/system/fuwlol-firewall.service <<'EOF'
[Unit]
Description=Cloudflare-only ingress for fuw.lol
After=docker.service
Requires=docker.service
[Service]
Type=oneshot
ExecStart=/srv/fuwlol/deploy/firewall.sh
[Install]
WantedBy=multi-user.target
EOF
cat > /etc/systemd/system/fuwlol-firewall.timer <<'EOF'
[Unit]
Description=Refresh Cloudflare ranges weekly
[Timer]
OnCalendar=weekly
Persistent=true
[Install]
WantedBy=timers.target
EOF
systemctl enable --now fuwlol-firewall.service fuwlol-firewall.timer
```

The rules live in `DOCKER-USER` and do not survive a reboot on their own, which is why the
service exists. The timer is not cosmetic: Cloudflare adds ranges, and a stale list means
visitors from a new one get dropped.

### Cron

```cron
0 3 * * *  /srv/fuwlol/deploy/backup.sh >> /srv/fuwlol/backup.log 2>&1
0 4 * * *  cd /srv/fuwlol && docker compose -f docker-compose.prod.yml exec -T api python manage.py forget_submitter_ips
0 4 * * *  cd /srv/fuwlol && docker compose -f docker-compose.prod.yml exec -T api python manage.py forget_claim_ips
15 4 * * * cd /srv/fuwlol && docker compose -f docker-compose.prod.yml exec -T api python manage.py kolo_forget_unconfirmed
```

The second and third are not housekeeping: `Post.submitter_ip` is personal data kept for
one purpose (art. 18 DSA), and keeping it past that purpose is the RODO problem, not the
solution. `forget_claim_ips` does the same for the consent claims — except on approved
rows, which ARE the evidence that somebody agreed. (`sweep_uploads`, which deleted
unclaimed R2 uploads, ran at 5:00 until R2 went; it is a no-op without R2 and was removed
from the crontab.)

### Backups

`deploy/backup.sh`, nightly: `pg_dump`, the `evidence` volume and the `media` volume, into
the restic repository at `/srv/fuwlol/restic-repo` (deploy-owned, 700, encrypted with
`secrets/restic.pass`). Keeps 7 daily, 4 weekly, 12 monthly, and reads a random 5% of the
data back every night.

**It is not off-site.** Until 02.11.2026 the repository was in R2; it was copied here byte
for byte (182 objects, the 45 snapshot ids identical, `restic check --read-data` clean, the
latest snapshot restored and `pg_restore --list` read) and R2 was switched off to save the
bill. A local repository covers a dropped table or a wiped volume, not a lost VPS or a
suspended OVH account — for those the only copy is OVH's own snapshot. The repository is
self-contained, so making it off-site again is one line somewhere else, e.g. from a machine
that can reach the box:
`rsync -a --delete ubuntu@146.59.103.167:/srv/fuwlol/restic-repo/ ./fuwlol-restic/`
(read it with the same password file).

Restore drill:
`sudo -u deploy RESTIC_PASSWORD_FILE=/srv/fuwlol/secrets/restic.pass restic -r /srv/fuwlol/restic-repo restore latest --target /tmp/r`

### First start

```bash
cd /srv/fuwlol
IMAGE_TAG=latest docker compose -f docker-compose.prod.yml --env-file .env up -d
docker compose -f docker-compose.prod.yml exec api python manage.py createsuperuser
```

**Before the first start, fix the volume ownership.** The container runs as uid 1000, but
a freshly created named volume can end up owned by root — and the failure is not at boot,
it is later, when somebody uploads a file and gets a 500 with
`PermissionError: '/app/media/attachments'`. Every attachment is stored on this volume,
so this is not a corner case:

```bash
for v in media cachedata evidence; do docker run --rm -v "fuwlol_${v}:/v" alpine chown -R 1000:1000 /v; done
```

`entrypoint.sh` migrates and collects static on every start, so there is no separate
migrate step. **Do not set `FUWLOL_SEED_DEMO=1` here** — it creates dziekan/doktorant/
student, and this is not a demo.

## Deploying

Push to `main`. Actions runs the Django suite and `svelte-check`, builds both images, and
only then pulls them here. A deploy never writes `.env` and never builds on the box.

**Rollback** is the same command with an older tag — no rebuild, because the image for
every commit is still in GHCR:

```bash
cd /srv/fuwlol && IMAGE_TAG=<older-sha> docker compose -f docker-compose.prod.yml --env-file .env up -d
```

## WUM — the side app at `fuw.lol/fum`

MedApp, a patient-facing prototype from **a different repository**
(`github.com/tryingtodosth/medapp`), is served from this origin under `/fum` and calls itself
**WUM** there. It is here because the people whose opinion it needs are the people who already
have this site's address. It sends two things to this server: a note about a screen, and — since
2026-10 — its own accounts and the anonymised records people choose to publish (`backend/wum/`,
`LEGAL.md` §9). Health data stays in the browser; the container itself still stores nothing.

**It was `/fwumu`, called FwUMU, until 27.09.2026.** The address is now `/fum` and the app calls
itself **WUM**; `/wum` and `/fwumu` — with their sub-paths and query strings — answer 308 to the
same path under `/fum` (`frontend/nginx.conf`). Links already sent to people keep working, and
nothing inside the app ever builds an old-name URL, so a redirect is only ever the first request.

**It is moving to a hostname of its own, `https://wum.fuw.lol` — in preparation since
2026-11-03, nothing live moved yet.** The procedure is `docs/work/WUM-HOST-RUNBOOK.md` in the medapp
repository; what this repository already carries for it is inert until a proxied `wum` record
exists in Cloudflare: the `server_name wum.fuw.lol` block at the end of `frontend/nginx.conf`
(the two API prefixes to `api`, everything else to the `wum` service), `wum.fuw.lol { import
common }` in `deploy/Caddyfile` (the origin certificate covers `*.fuw.lol`), `wum.fuw.lol` in
`FUWLOL_ALLOWED_HOSTS`, the `wum` service on `WUM_TAG` (`:wum-latest`, built at `/` by the medapp
workflow beside the mounted `:latest`), and the deploy's best-effort start of it after `skoki`.
**A changed Caddyfile is not reloaded by the deploy** — Caddy's admin API is off — so
`docker compose -f docker-compose.prod.yml --env-file .env restart caddy` by hand, once. The move
itself (the `/fum` redirects, the self-unregistering service worker at `/fum/service-worker.js`,
`skoki` retired) is the runbook's phase 2 and is not in this repository yet. Two things the move
costs that no config shows: the record a tester kept under `fuw.lol` stays there (storage is per
origin), and the worker the old copy registered must be unregistered by the old origin.

**Moving or renaming it again is the medapp repository's job, not a hand edit here.** That
repository carries `scripts/deployment.mjs` (`npm run deployment -- --name … --base … --aliases …`),
which prints the exact nginx block, the build arguments and the by-hand checks, and a
`deployment-mount` skill that lists every file on both sides. Paste what it prints into
`frontend/nginx.conf` and rebuild the `web` image — the mount is baked into the app's image at
BUILD time, so `docker-compose.prod.yml` cannot move it. Nothing in the archive's own frontend
names the path any more, so that config is the only place here that has to change.

Three pieces, and they are deliberately independent of the archive's own deploy:

| Piece | Where | Note |
|---|---|---|
| `skoki` service | `docker-compose.prod.yml` | its own `SKOKI_TAG`, because `IMAGE_TAG` is a commit of THIS repository |
| `location /fum/` | `frontend/nginx.conf` | proxies to `skoki:3000` **through a variable**, so a missing side app cannot stop nginx from starting |
| `/wum`, `/fwumu` → `/fum` | `frontend/nginx.conf` | 308, sub-paths and query preserved; the old names are kept alive, not supported |
| `POST /api/feedback/` | `backend/feedback/` | a note about a screen; anonymous, 120/hour per IP, read in the Django admin |
| `/api/wum/…` | `backend/wum/` | accounts, example templates, anonymised publications; token-only auth; `/admin/wum/` is where templates are written and publications taken down. The restic dump of Postgres now holds these rows too |

**The archive's deploy no longer depends on it.** `.github/workflows/deploy.yml` pulls and starts
the four archive services **by name**, then tries `skoki` separately and warns instead of failing
if it cannot. Learned twice on 26.09.2026: a plain `docker compose pull` died on the missing
side-app image, and so did `up --scale skoki=0` — **scaling a service to zero does not stop Compose
resolving its image while it plans the run**, so only naming the services keeps it out of the
archive's path.

**The image is a private package by default**, because the medapp repository is private, and this
box pulls from GHCR anonymously — so a pull of it fails with `denied` even once it exists. Two ways
out, and the first is the one in use: make the package public (GitHub → the medapp repository →
Packages → `fuwlol-skoki` → Package settings → Change visibility), since the image holds a public
web app and no secrets; or `docker login ghcr.io` on the box with a `read:packages` token, which
then has to be kept alive.

**Deploying it** is a push to `main` in the medapp repository: its own workflow type-checks it,
builds it mounted, pushes `ghcr.io/tryingtodosth/fuwlol-skoki:<sha>` **and `:latest`**, and prints
the tag. Nothing on this box pulls by itself: the archive's own deploy re-pulls whatever
`SKOKI_TAG` says (`latest` unless pinned), and otherwise it is the two lines below. The box was
found 40 commits behind on 2026-10-06 for exactly that reason. The api side (`wum/0001` … `wum/0003`,
the last the practitioners' marks on the figure of 2026-10-15) migrates on container start (`backend/entrypoint.sh`), so the archive's deploy carries it. Then here:

```bash
cd /srv/fuwlol
sed -i 's/^SKOKI_TAG=.*/SKOKI_TAG=<sha>/' .env     # or leave it at latest and just pull
docker compose -f docker-compose.prod.yml --env-file .env pull skoki
docker compose -f docker-compose.prod.yml --env-file .env up -d skoki
```

Rolling it back is the same two lines with an older sha, and it touches nothing else on the box.
**Taking it down entirely** — `docker compose stop skoki` — leaves the archive untouched and makes
`/fum/` answer 502; removing the location from `nginx.conf` is the tidy version and needs a
`web` image, so it is not the emergency move.

After the first deploy of it, in a browser:

1. `https://fuw.lol/fum` redirects to `/fum/` and the app opens — **styled**, and **in
   staropolszczyzna** („Dzień obecny", „Cielesna powłoka"). Unstyled means the base path and the
   build disagree, and everything else will be wrong too; English at the bare path means the image
   was built without `MEDAPP_DEFAULT_LOCALE=lol` (it is compiled in — the medapp repository's
   `Dockerfile`, and no variable on this box can change it).
2. Click through two or three screens and change the language: every URL keeps `/fum` on it. A
   link that drops to `https://fuw.lol/today` is the base path leaking (`src/hooks.ts` there).
   **`/fum/` itself is staropolszczyzna** — 17th-century Polish, the joke for this audience. That
   deployment is built with `MEDAPP_DEFAULT_LOCALE=lol`, so the three real languages live at
   `/fum/pl/`, `/fum/en/` and `/fum/uk/`, and all four are in its switcher. It is an overlay on
   modern Polish, so a screen nobody has rendered into staropolszczyzna yet reads as ordinary
   Polish and **never** as English. The language is compiled into that image; nothing here can
   change it, and no other deployment of that app offers it. (Until 27.09.2026 the image was built
   with `=pl`, Polish was the bare path and `/fum/pl/` a 404; it is not any more.)
3. `https://fuw.lol/` is still the archive, and `https://fuw.lol/wpis/<slug>` still opens a post:
   the new location must not have swallowed anything.
4. The old names still land: `curl -sI https://fuw.lol/fwumu/en/today` and `.../wum/care?q=1` must
   each answer `308` with a `Location:` of the same path under `/fum` — **relative**, not
   `http://…`, or somebody typing the old address takes an unencrypted hop.
5. **The archive does not link to it, and must not start.** `https://fuw.lol/` has no path to the
   app: the „Skoki" list in the time machine carried a **WUM** stop until 27.09.2026 and no longer
   does. Somebody with the address still opens it; a visitor to the archive does not find it. This
   is deliberate — the comment where the stop stood says so, so nobody restores it as a bug fix.
6. Send a note from the app's own button, then look for it in
   `https://fuw.lol/admin/feedback/feedback/`. The `location` column must name the screen you were
   on — that is the whole point of the endpoint.
7. `docker compose exec web nginx -t`, as after any change to `frontend/nginx.conf`.
8. The accounts round trip, same-origin: open `/fum/pl/account`, create an account — it appears in
   `https://fuw.lol/admin/wum/wumprofile/` with `User.email` blank. On `/fum/pl/publish` the
   preview shows no name; publish, and `curl -s https://fuw.lol/api/wum/publications/` lists one
   row with an `id`, a `payload`, a `published_month` and **no username anywhere**; withdraw, and
   the list is empty again while the row stays in `/admin/wum/publication/` as `withdrawn`. Paste
   an exported example into `/admin/wum/template/`, set it `published`, and `/fum/pl/templates`
   offers it. A 403 on any of these is the CSRF trap (`backend/wum/views.py`); a 409 is a text or
   payload version the two repositories disagree on (`wum/CLAUDE.md` "Mirrored constants").

**If `/fum/` answers 502, read the error log before anything else** — the container being
healthy proves nothing, and two plausible-sounding theories (a stale DNS cache; the wrong image)
were both wrong on 26.09.2026:

```bash
docker compose -f docker-compose.prod.yml --env-file .env logs --tail=20 web
```

- `upstream sent too big header` — **the one that actually happened.** SvelteKit's `Link:`
  modulepreload header is up to 6.9 kB on this app and nginx's default buffer is 4 kB, so every
  page 502s while the app is perfectly healthy. `frontend/nginx.conf` raises the buffers to 32 kB
  and carries the measurements. A `wget` from inside the web container SUCCEEDS in this state,
  which is why it misleads: wget does not care how big a header is.
- `could not be resolved` — DNS. An nginx that was running before the side app's container existed
  caches the failure, and `valid=` does not cover failed answers; `nginx -s reload` clears it, and
  any deploy that ships a new `web` image does it by itself.
- `connect() failed` — the app is down or on another network; check `docker compose ps skoki`.

## LSD — the second side app at `fuw.lol/lsd`

A second copy of MedApp from the same repository, mounted at `/lsd` and called **LSD** there, for
an anonymous retrospective questionnaire about psychedelic use run as preparation for a student
experiment — a project not affiliated with any university; the controller is Piotr Putyło,
`admin@fuw.lol`. It is the WUM arrangement a second time: the `lsd` service in
`docker-compose.prod.yml`, `location /lsd/` and `location = /lsd` in `frontend/nginx.conf`
through the same resolver variable and raised buffers, the deploy's best-effort pull after `skoki`
and `wum`. Two differences: the image is built with `/lsd` baked in and pushed under the **`lsd-`
tag prefix** (`:lsd-<sha>`, `:lsd-latest`), so its own variable is **`LSD_TAG`** (`lsd-latest`
unless pinned in `/srv/fuwlol/.env`); and it has no old names, so there are no alias redirects.

Its new server calls are `POST /api/survey/` and `POST /api/survey/withdraw/` (`backend/survey/`,
`LEGAL.md` §9b): a finished sheet becomes one row with **no address, no account, no user agent
and a DATE instead of a timestamp**; the person's optional e-mail and optional key are stored as
hashes only, and the key blanks the sheet again. Sheets are read in the Django admin and exported
by `manage.py export_survey <slug> [--format jsonl|csv] [--since YYYY-MM-DD]`; a withdrawal asked
for by mail is `manage.py survey_withdraw --email <the sender's address>`. It also files notes to
`POST /api/feedback/` like the first copy. The container stores nothing.

Deploying and rolling it back are the WUM lines with `lsd` for `skoki` and `LSD_TAG` for
`SKOKI_TAG`; `survey/0001` migrates on the api container's start like every other migration.

After the first deploy of it, in a browser:

1. `https://fuw.lol/lsd` answers 308 to `/lsd/` (relative `Location:`, as for `/fum`) and the app
   opens **styled** and **in Polish** at the bare path — this copy is not the staropolszczyzna
   build; an unstyled page or English at the bare path means the build and the mount disagree.
2. `https://fuw.lol/lsd/en/` exists and is English; every link clicked keeps `/lsd` on it.
3. `https://fuw.lol/lsd/survey` opens the questionnaire: the heading names the goal (preparation
   of a student experiment), the three acknowledgements and the 18+ gate come before the first
   question, and the optional e-mail / key step comes last.
4. Send one, asking for a key, and look at `https://fuw.lol/admin/survey/surveyresponse/`: the
   row has the survey slug, version, consent version, locale, duration and a **date only** — no
   IP, no account, no time of day, no hash anywhere on the page, „ma klucz” ticked. Then
   `curl -s -X POST https://fuw.lol/api/survey/withdraw/ -H 'content-type: application/json'
   -d '{"key":"<the key>"}'` answers `{"ok": true, "status": "withdrawn"}` and the row shows
   „Wycofana” with empty answers. A 403 on sending is the CSRF trap (`backend/survey/views.py`);
   a 400 keyed `version` or `consent_version` means the app and `survey/rules.py` disagree.
5. `https://fuw.lol/`, `/fum/` and a post are unchanged, and `docker compose exec web nginx -t`.

If `/lsd/` answers 502, the WUM list above applies unchanged (`logs --tail=20 web`;
`docker compose ps lsd`).

## Koło AI — `ai.fuw.lol` (`backend/kolo_ai/`)

The same containers serve it: nginx 308s `fuw.lol/ai` (any letter case) to the subdomain, and
the SPA reroutes that host's paths under `/ai` (`frontend/src/hooks.ts`). One-time steps, in
order:

1. **Cloudflare DNS:** `CNAME ai → fuw.lol`, **proxied**, like `www`. It inherits both the A and
   the AAAA record. **Never DNS-only:** the firewall admits only Cloudflare's ranges, and the
   origin certificate is trusted by Cloudflare alone, so a grey-cloud record is a timeout or a
   certificate error for every visitor. The origin certificate covers `*.fuw.lol` (step 2 of the one-time setup above).
   Until the deploy below, ai.fuw.lol answers with an error from Caddy, which harms nothing.
2. **Deploy** (push to `main`). The workflow ships `deploy/Caddyfile` with the `ai.fuw.lol` block,
   but does not reload Caddy (its admin API is off), so once:
   `cd /srv/fuwlol && docker compose -f docker-compose.prod.yml --env-file .env restart caddy`.
3. **The first manager:** `docker compose -f docker-compose.prod.yml exec api python manage.py kolo_invite ADRES@student.uw.edu.pl --name "Imię Nazwisko" --manager`
4. **The publish key** for the status script: `… exec api python manage.py kolo_publish_key create claude`.
   The key is printed once; keep it in `~/.config/kolo-ai/token` (mode 600) on the machine that runs
   `publikuj_status.py`.
5. **The cron line** `kolo_forget_unconfirmed` (above).
6. **After the Koło is in the BOK register:** set `FUWLOL_KOLO_AUTO_ADMIT: "1"` in
   `docker-compose.prod.yml`, so that a confirmed `student.uw.edu.pl` declaration admits itself.

Check after a deploy:
- `curl -sI https://fuw.lol/AI/x?y=1` → `308`, `location: https://ai.fuw.lol/x?y=1`;
- `curl -s https://ai.fuw.lol/api/kolo/info/` → JSON;
- https://ai.fuw.lol shows Koło AI, not the archive;
- `/`, `/fum/` and a post on fuw.lol are unchanged.

## Link previews (`backend/share/`)

Every URL here is served the same `200.html` and titled by JavaScript, and **no scraper
runs JavaScript** — which is why a post pasted into Messenger used to show „fuw.lol" and
nothing else. The fix is server-rendered tags for the scrapers, and nothing at all for
everybody else.

**The mode: crawler routing, at the nginx hop.** `frontend/nginx.conf` matches the
User-Agent and rewrites the request to Django, which answers `/share/<the same path>` with
a small page carrying `og:*`, `twitter:*`, `<title>`, the description and a canonical link:

```nginx
map $http_user_agent $fuwlol_crawler { default 0; ~*facebookexternalhit|…|Signal 1; }
map $uri             $fuwlol_route   { default 1; ~\. 0; }   # a dot means a file, not a route
map $fuwlol_crawler$fuwlol_route $fuwlol_preview { default 0; 11 1; }

location / {
    if ($fuwlol_preview) { rewrite ^ /share$uri last; }
    try_files $uri /200.html;
}
location /share/     { proxy_pass http://api:8000; … }
location = /sitemap.xml { proxy_pass http://api:8000/share/sitemap.xml; … }
```

The other design — Django serving the real `200.html` with the tags spliced into its
`<head>`, for everybody, with no User-Agent anywhere — is better and is implemented
(`FUWLOL_SPA_INDEX` + `FUWLOL_SHARE_REDIRECT_HUMANS=0`, tested). It is not what runs,
because the built SPA lives in the `web` image and Django in the `api` one: it would need
a shared volume or one image holding both. Switch when the packaging does; the Django side
needs no change. Until then the human path is byte-for-byte what it was, which is the
point — Caddy is untouched and so is the CSP.

**Cloudflare: do not put a „Cache Everything" rule on HTML.** One URL now answers
differently by User-Agent, and Cloudflare honours `Vary` on `Accept-Encoding` only — a
cache-everything rule would serve one visitor's answer to the other kind of visitor.
HTML is not in Cloudflare's default cache set (it caches by extension), so as configured
this is safe; the bypass rule on `/api/*` stays as it is.

**After a deploy, re-scrape anything already shared.** Facebook keeps what it scraped —
for a URL somebody sent last week, Messenger will go on showing the old, empty card until
Facebook fetches it again, and it will not fetch it again just because the page changed.
Paste the URL into <https://developers.facebook.com/tools/debug/> and press *Scrape Again*
(that is also where a malformed tag shows up as an error rather than as silence). Telegram
caches the same way: send the link to [@WebpageBot](https://t.me/WebpageBot) and it
refreshes. WhatsApp, Slack and Discord expire on their own within a day or so, and a URL
nobody has shared yet is fetched fresh, so this is only about the links already out there.

**The four fallback pictures** (`frontend/static/og-default.png`, `og-osoba-m.png`,
`og-osoba-f.png`, `og-osoba.png`) are drawn by `manage.py make_share_images` and committed — 1200×630,
because Facebook drops any image below 200×200 and the faculty's own silhouettes are
130×130. Re-run the command if the wording on them should change.

`https://fuw.lol/sitemap.xml` is generated by the same app (published posts, listed people,
subjects, categories, the standing pages) and named from `robots.txt`.

## Verify after a deploy

Green tests are not evidence that the site works; several real bugs in this project were
found by looking at it. So, in a browser:

1. `https://fuw.lol` loads, and `curl -I https://fuw.lol` shows `cf-cache-status`.
2. `curl -I https://146.59.103.167` from anywhere **fails** — otherwise `FUWLOL_CLOUDFLARE=1`
   is a forgeable header and every per-IP throttle is a fiction.
3. Register with a real `@fuw.edu.pl` address; the verification mail arrives in the inbox,
   not spam. This is the trusted tier working, and it is the thing most likely to be broken.
   **Give it an hour before calling it broken**: `fuw.edu.pl` is the Faculty's own
   `mail.fuw.edu.pl`, which greylists Brevo's shared relay, while `uw.edu.pl` and
   `student.uw.edu.pl` are on Google and arrive at once. A 202 from `verify/request/` only
   means Brevo accepted the message — `send_mail` returns there and a later bounce goes to
   Brevo, never to us — so **Brevo → Transactional → Logs**, filtered to the address, is the
   only witness: `Delivered` puts it in the recipient's quarantine, `Soft bounce` is the
   greylist, `Blocked`/`Hard bounce` carries the remote server's refusal, and nothing listed
   at all is the one answer that points back at this box. Test it with an address you own —
   a clicked link binds that address to whatever account asked for it, and `accounts/views.py`
   `_taken_by_someone_else` then locks its real owner out until the row is deleted.
4. Submit a post with a 20 MB video: it is a multipart POST to `fuw.lol/api/posts/`, lands
   on the media volume, and plays back afterwards from `/media/attachments/…`.
5. Escalate something as a trusted user, confirm it vanishes for everyone but head-admin,
   and that the picture's `/media/attachments/…` URL now 404s.
6. `curl -s -A "facebookexternalhit/1.1" https://fuw.lol/wpis/<slug> | grep og:` prints the
   post's title, summary and picture; the same URL in a browser is still the app. Then
   paste the link into Messenger and **look at it** — and check that a hidden post's URL
   gives the plain site card, not its title.

## Not verified here

Written on a machine with no Docker: the compose file parses and the Python side is
covered by 186 tests, but the first `docker compose pull` and the first Caddy start happen
on the server. The same is true of **everything about `skoki`**: its Dockerfile, the
`location /fum/` block and the variable-resolver trick have never been run — the app itself was
driven in a browser behind a Node stand-in for nginx (`scripts/mounted-preview.mjs` in the medapp
repository), which is not the same thing. `docker compose exec web nginx -t` and the five checks in
the WUM section above are what stands in for that. If `caddy` will not start, `docker compose logs caddy` names the reason —
usually the origin certificate paths.

The link-preview rewrite is in the same position: the Django half has its own tests, but
the three `map` blocks and the `/share/` location have never been through `nginx -t` —
there is no nginx on the machine they were written on. `docker compose exec web nginx -t`
is the first thing to run after the deploy that carries them, and `curl -A
facebookexternalhit` the second.
