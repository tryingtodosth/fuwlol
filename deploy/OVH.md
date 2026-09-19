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
   see DESIGN.md "The two takedowns"). Add a custom domain `pliki.fuw.lol` for the public
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
RESTIC_REPOSITORY=s3:https://<account-id>.r2.cloudflarestorage.com/fuwlol-backup
RESTIC_PASSWORD_FILE=/srv/fuwlol/secrets/restic.pass
AWS_ACCESS_KEY_ID=          # the same R2 token, or one scoped to the backup bucket
AWS_SECRET_ACCESS_KEY=
```

`chmod 600 /srv/fuwlol/.env`. **Keep `RESTIC_PASSWORD_FILE`'s contents somewhere that is
not this server** — a backup you cannot decrypt is not a backup, and the server is the one
machine guaranteed to be missing when you need it.

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
0 5 * * *  cd /srv/fuwlol && docker compose -f docker-compose.prod.yml exec -T api python manage.py sweep_uploads
```

The second one is not housekeeping: `Post.submitter_ip` is personal data kept for one
purpose (art. 18 DSA), and keeping it past that purpose is the RODO problem, not the
solution. The third deletes objects that were uploaded to R2 and never claimed by a post.

### First start

```bash
cd /srv/fuwlol
IMAGE_TAG=latest docker compose -f docker-compose.prod.yml --env-file .env up -d
docker compose -f docker-compose.prod.yml exec api python manage.py createsuperuser
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

## Verify after a deploy

Green tests are not evidence that the site works; several real bugs in this project were
found by looking at it. So, in a browser:

1. `https://fuw.lol` loads, and `curl -I https://fuw.lol` shows `cf-cache-status`.
2. `curl -I https://146.59.103.167` from anywhere **fails** — otherwise `FUWLOL_CLOUDFLARE=1`
   is a forgeable header and every per-IP throttle is a fiction.
3. Register with a real `@fuw.edu.pl` address; the verification mail arrives in the inbox,
   not spam. This is the trusted tier working, and it is the thing most likely to be broken.
4. Submit a post with a 20 MB video: the browser PUTs it to `pliki.fuw.lol` directly (watch
   the network tab — it must not go to `fuw.lol/api/`), and it plays back afterwards.
5. Escalate something as a trusted user, confirm it vanishes for everyone but head-admin,
   and that the picture's URL on `pliki.fuw.lol` now 404s.

## Not verified here

Written on a machine with no Docker: the compose file parses and the Python side is
covered by 186 tests, but the first `docker compose pull` and the first Caddy start happen
on the server. If `caddy` will not start, `docker compose logs caddy` names the reason —
usually the origin certificate paths.
