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
               │                              │
               ▼                              ▼
      Cloudflare R2                    Brevo SMTP :587
      attachment bytes                 verification mail
      + restic backups                 (OVH blocks :25)
```

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
   | CNAME | `pliki` | (R2 custom domain, set from the R2 bucket page) | proxied |
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

3. **R2.** Bucket (`fuwlol-media`), EU location hint. **Versioning OFF, and no lifecycle
   rule that retains deleted objects** — `escalation/shred.py` deletes an object to make a
   purge real, and a retained version would make the audit row a lie (art. 202 § 4b k.k.;
   see LEGAL.md "The two takedowns"). Add a custom domain `pliki.fuw.lol` for the public
   prefix. Create an API token: Object Read & Write, scoped to this bucket.

   **And a second bucket, `fuwlol-quarantine`, with NO custom domain.** A custom domain
   publishes the whole bucket, so an escalated attachment moved to a `held/` prefix in
   the public bucket is still served — measured, not assumed: the held URL answered
   HTTP 200. The token needs access to both buckets.

4. **Brevo.** Verify `fuw.lol`, add their SPF and DKIM records, create an SMTP key.

5. **GitHub → Settings → Secrets and variables → Actions:** `DEPLOY_SSH_KEY`,
   `DEPLOY_HOST` = `146.59.103.167`, `DEPLOY_USER` = `deploy`.

## One-time: the box

```bash
# as root, once
adduser --disabled-password --gecos '' deploy
install -d -m700 -o deploy -g deploy /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/ && chown deploy:deploy /home/deploy/.ssh/authorized_keys
usermod -aG docker deploy
install -d -o deploy -g deploy /srv/fuwlol /srv/fuwlol/deploy /srv/fuwlol/secrets
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
FUWLOL_R2_BUCKET=fuwlol-media
FUWLOL_R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
FUWLOL_R2_ACCESS_KEY_ID=
FUWLOL_R2_SECRET_ACCESS_KEY=
FUWLOL_R2_PUBLIC_BASE_URL=https://pliki.fuw.lol
FUWLOL_CLOUDFLARE_ZONE_ID=
FUWLOL_CLOUDFLARE_PURGE_TOKEN=
FUWLOL_EMAIL_HOST=smtp-relay.brevo.com
FUWLOL_EMAIL_USER=
FUWLOL_EMAIL_PASSWORD=
FUWLOL_FROM_EMAIL="FUW <no-reply@fuw.lol>"   # quoted: deploy/backup.sh SOURCES this file, and < is a redirect
FUWLOL_CONTACT_EMAIL=admin@fuw.lol           # the one OVH mailbox — what a human reads
SKOKI_TAG=latest             # FwUMU (fuw.lol/fwumu) — a commit of the MEDAPP repository, not this one
RESTIC_REPOSITORY=s3:https://<account-id>.r2.cloudflarestorage.com/fuwlol-backup
RESTIC_PASSWORD_FILE=/srv/fuwlol/secrets/restic.pass
AWS_ACCESS_KEY_ID=          # the same R2 token, or one scoped to the backup bucket
AWS_SECRET_ACCESS_KEY=
```

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
0 3 * * *  /srv/fuwlol/deploy/backup.sh >> /var/log/fuwlol-backup.log 2>&1
0 4 * * *  cd /srv/fuwlol && docker compose -f docker-compose.prod.yml exec -T api python manage.py forget_submitter_ips
0 4 * * *  cd /srv/fuwlol && docker compose -f docker-compose.prod.yml exec -T api python manage.py forget_claim_ips
0 5 * * *  cd /srv/fuwlol && docker compose -f docker-compose.prod.yml exec -T api python manage.py sweep_uploads
```

The second and third are not housekeeping: `Post.submitter_ip` is personal data kept for
one purpose (art. 18 DSA), and keeping it past that purpose is the RODO problem, not the
solution. `forget_claim_ips` does the same for the consent claims — except on approved
rows, which ARE the evidence that somebody agreed. The last one deletes objects that were
uploaded to R2 and never claimed by a post.

### First start

```bash
cd /srv/fuwlol
IMAGE_TAG=latest docker compose -f docker-compose.prod.yml --env-file .env up -d
docker compose -f docker-compose.prod.yml exec api python manage.py createsuperuser
```

**Before the first start, fix the volume ownership.** The container runs as uid 1000, but
a freshly created named volume can end up owned by root — and the failure is not at boot,
it is later, when somebody uploads a file and gets a 500 with
`PermissionError: '/app/media/attachments'`. Comment attachments still use local storage
even when R2 is on, so this is not a corner case:

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

## FwUMU — the side app at `fuw.lol/fwumu`

MedApp, a patient-facing prototype from **a different repository**
(`github.com/tryingtodosth/medapp`), is served from this origin under `/fwumu` and calls itself
**FwUMU** there. It is here because the people whose opinion it needs are the people who already
have this site's address, and the one thing it sends anywhere is a note about a screen.

Three pieces, and they are deliberately independent of the archive's own deploy:

| Piece | Where | Note |
|---|---|---|
| `skoki` service | `docker-compose.prod.yml` | its own `SKOKI_TAG`, because `IMAGE_TAG` is a commit of THIS repository |
| `location /fwumu/` | `frontend/nginx.conf` | proxies to `skoki:3000` **through a variable**, so a missing side app cannot stop nginx from starting |
| `POST /api/feedback/` | `backend/feedback/` | the only call it makes; anonymous, 120/hour per IP, read in the Django admin |

**The one coupling this creates:** the archive's own deploy runs `docker compose pull`, which now
includes `skoki` — an image **another repository** publishes. If that image does not exist yet (the
first deploy of the pair, in the wrong order) or has been deleted, the pull fails and the archive's
deploy goes red without the archive itself being touched: the site stays on the previous version.
Fix it by publishing the image and re-running the job, or deploy the archive alone with

```bash
docker compose -f docker-compose.prod.yml --env-file .env up -d --remove-orphans --scale skoki=0
```

Deploy the two in the order **medapp first, archive second** and the question does not arise.

**Deploying it** is a push to `main` in the medapp repository: its own workflow type-checks it,
builds it mounted, pushes `ghcr.io/tryingtodosth/fuwlol-skoki:<sha>`, and prints the tag. Then here:

```bash
cd /srv/fuwlol
sed -i 's/^SKOKI_TAG=.*/SKOKI_TAG=<sha>/' .env     # or leave it at latest and just pull
docker compose -f docker-compose.prod.yml --env-file .env pull skoki
docker compose -f docker-compose.prod.yml --env-file .env up -d skoki
```

Rolling it back is the same two lines with an older sha, and it touches nothing else on the box.
**Taking it down entirely** — `docker compose stop skoki` — leaves the archive untouched and makes
`/fwumu/` answer 502; removing the location from `nginx.conf` is the tidy version and needs a
`web` image, so it is not the emergency move.

After the first deploy of it, in a browser:

1. `https://fuw.lol/fwumu` redirects to `/fwumu/` and the app opens — **styled**. Unstyled means
   the base path and the build disagree, and everything else will be wrong too.
2. Click through two or three screens and change the language: every URL keeps `/fwumu` on it. A
   link that drops to `https://fuw.lol/today` is the base path leaking (`src/hooks.ts` there).
3. `https://fuw.lol/` is still the archive, and `https://fuw.lol/wpis/<slug>` still opens a post:
   the new location must not have swallowed anything.
4. Send a note from the app's own button, then look for it in
   `https://fuw.lol/admin/feedback/feedback/`. The `location` column must name the screen you were
   on — that is the whole point of the endpoint.
5. `docker compose exec web nginx -t`, as after any change to `frontend/nginx.conf`.

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
4. Submit a post with a 20 MB video: the browser PUTs it to `pliki.fuw.lol` directly (watch
   the network tab — it must not go to `fuw.lol/api/`), and it plays back afterwards.
5. Escalate something as a trusted user, confirm it vanishes for everyone but head-admin,
   and that the picture's URL on `pliki.fuw.lol` now 404s.
6. `curl -s -A "facebookexternalhit/1.1" https://fuw.lol/wpis/<slug> | grep og:` prints the
   post's title, summary and picture; the same URL in a browser is still the app. Then
   paste the link into Messenger and **look at it** — and check that a hidden post's URL
   gives the plain site card, not its title.

## Not verified here

Written on a machine with no Docker: the compose file parses and the Python side is
covered by 186 tests, but the first `docker compose pull` and the first Caddy start happen
on the server. The same is true of **everything about `skoki`**: its Dockerfile, the
`location /fwumu/` block and the variable-resolver trick have never been run — the app itself was
driven in a browser behind a Node stand-in for nginx (`scripts/mounted-preview.mjs` in the medapp
repository), which is not the same thing. `docker compose exec web nginx -t` and the five checks in
the FwUMU section above are what stands in for that. If `caddy` will not start, `docker compose logs caddy` names the reason —
usually the origin certificate paths.

The link-preview rewrite is in the same position: the Django half has its own tests, but
the three `map` blocks and the `/share/` location have never been through `nginx -t` —
there is no nginx on the machine they were written on. `docker compose exec web nginx -t`
is the first thing to run after the deploy that carries them, and `curl -A
facebookexternalhit` the second.
