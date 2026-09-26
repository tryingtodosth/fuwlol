# backend/ — Django 5.2 + DRF, 8 apps + `config/`, SQLite locally / Postgres in production

Scoped context for backend work. The cross-cutting rules are in the root `CLAUDE.md`; the reasoning
is in `DESIGN.md`; each app's own `CLAUDE.md` has its rules; `MODERATION-API.md` documents the
trusted-tier, moderation, escalation, R2 and chat endpoints one by one.

## Run / test

- `cd backend && FUWLOL_CACHE_DIR=<scratch> ../.venv/bin/python manage.py test` — 374 tests,
  about 4 minutes, SQLite, no daemon. `manage.py check`, `manage.py makemigrations --check
  --dry-run` (CI enforces the latter; a model change without its migration fails the deploy).
- Dev server: `./run.sh` from the repo root, or by hand
  `FUWLOL_CORS_ORIGINS=http://localhost:<front>,http://127.0.0.1:<front> ../.venv/bin/python
  manage.py runserver 127.0.0.1:<api>` — and then `FUWLOL_SITE_URL` too, or every mailed and
  previewed link points at 5173.
- `requirements.txt` here is the only one. `boto3` is in it although R2 is optional at runtime:
  a deployment that stores attachments in R2 must not discover the import on the box.
- `FUWLOL_DEBUG` defaults to `1`. The API image sets it to `0`, and settings then refuse the default
  `SECRET_KEY`. Nothing in the suite depends on DEBUG being on except the demo passwords.

## Settings and environment (`config/settings.py`)

Everything deployment-specific is a `FUWLOL_*` variable; `.env.example` lists them with the reason
each exists, and `docker-compose.prod.yml` shows the production values. The ones that bite:

| Variable | Default | Why it matters |
|---|---|---|
| `FUWLOL_CACHE_DIR` | `backend/cachedata` | the **file** cache holding every throttle counter — shared between workers and surviving restarts on purpose; a per-process cache would multiply every rate by the worker count |
| `FUWLOL_PROXY_HOPS` / `FUWLOL_TRUST_PROXY` / `FUWLOL_CLOUDFLARE` | `1` / `0` / `0` | `config/middleware.py` takes the N-th address **from the right** of `X-Forwarded-For`; production is 3 (Cloudflare → Caddy → nginx); Cloudflare's header only where the firewall makes it unforgeable |
| `FUWLOL_EVIDENCE_ROOT` | `backend/evidence` | outside `MEDIA_ROOT` by design — never served by path, only streamed by a view that re-checks `is_head_admin` |
| `FUWLOL_SITE_URL` | `http://localhost:5173` | the host in every server-built link: verification mail, consent claims, `og:url`, sitemap |
| `FUWLOL_R2_*` | unset | unset is a supported setup and what the suite runs with: uploads go through Django to `MEDIA_ROOT`, presign answers 503. `FUWLOL_R2_QUARANTINE_BUCKET` must be a *separate private* bucket |
| `FUWLOL_SUBMITTER_IP_RETENTION_DAYS` | `90` | how long `Post.submitter_ip` lives before `forget_submitter_ips` blanks it (`LEGAL.md` §4) |
| `FUWLOL_CONTACT_EMAIL` | `admin@fuw.lol` | the mailbox a human reads (DSA art. 12); deliberately not the `From` address |
| `DATABASE_URL` | unset | set → Postgres (`CONN_MAX_AGE 60`); unset → SQLite at `FUWLOL_DB_PATH` with `timeout: 20` |

`LANGUAGE_CODE='pl'`, `TIME_ZONE='Europe/Warsaw'`. `MAX_UPLOAD_BYTES` = 25 MB, `MAX_FILES_PER_POST` = 6.
The `security` logger is configured on its own (console, INFO, no propagation): every escalation
step writes a row **and** a line here, so a database-only compromise cannot erase the trail.

## Tiers — Django's own flags plus one bit

`is_staff` (staff), `is_superuser` (head-admin — or the grantable
`escalation.can_manage_critical_quarantine`, `escalation/visibility.is_head_admin`), and
`accounts/trust.is_trusted` (a confirmed e-mail at a `TrustedDomain`). Staff is always trusted. No
fourth role model; a new power is attached to one of these three checks, in the rule module of the
app that owns it (`archive/moderation.py`: `is_staff`, `is_trusted`, `IsTrusted`, `can_see_post`,
`visible_posts_q`, `can_see_comment`; `portraits/rules.can_moderate`; `board/trust.can_moderate`).

## The default manager hides the critical statuses

`Post.objects` excludes `quarantined` and `purged` (`PostManager`, `CRITICAL_STATUSES`). That is
the layer which catches the call site nobody thought about — the public API, the board, the admin,
the search, `manage.py shell`. `Post.all_objects` is the unfiltered manager; `Meta.base_manager_name
= 'all_objects'` so `attachment.post` and `comment.post` resolve for the escalation machinery. Use
`all_objects` only where you mean "including what a head-admin is responsible for", and say so in a
comment. Comments and chat messages have no status to project onto; `is_escalated(obj)` governs them.

## Throttles

Scopes and rates are in `settings.py` (`SECURITY.md` has the table). **A per-action scope on a
ViewSet needs `FixedScopeThrottle`** (`archive/views.py`) — DRF's `ScopedRateThrottle` reads
`throttle_scope` off the view, so per-`@action` scopes were a silent no-op until it existed. Login is
limited per IP *and* per submitted username (`LoginUsernameThrottle`). Counters are in the file
cache: when a test or a browser run hits 429, it is the cache, not the code.

## The side app's one endpoint

`feedback/` exists for FwUMU (`fuw.lol/fwumu`), which has no backend of its own. `POST
/api/feedback/`, anonymous, `TokenAuthentication` only — **not** the project default, because the
app is same-origin with the archive and a visitor's stray session cookie would otherwise trip DRF's
CSRF check and answer 403 to somebody filing a bug report. Scope `feedback` is 120/hour, which is
high on purpose: a feedback session is a room behind one NAT. `feedback/CLAUDE.md` has the rest.

## URL include order (`config/urls.py`)

`api/moderation/` → `escalation.urls`; then `portraits.urls` and `consent.urls` under `api/`
**before** `archive.urls`, because the archive router is greedy on `people/<slug>/`; then `share/`.
`MEDIA_URL` is served by Django only under DEBUG — in production nginx serves `/media/` from the
shared volume with a sandboxing CSP.

## Uploads

`archive/validators.py` is the one place that decides what a file is (bytes, not names), and it runs
for a multipart upload, for an R2 object pulled back by `archive/uploads.verify_stored`, and for a
portrait. `config/r2.py` is the only module that talks to the bucket (`PUBLIC_PREFIX`,
`HELD_PREFIX`, presign signed over length **and** checksum, `move_to_held` / `move_to_public`,
`PREVIEW_TTL_SECONDS = 300`); tests swap it with `set_client_for_tests`. `manage.py sweep_uploads`
deletes unclaimed objects after a day.

## Management commands, and which are cron

| Command | App | Run by |
|---|---|---|
| `seed_demo [--reset]` | archive | `setup.sh`; `FUWLOL_SEED_DEMO=1` in a container — never in production |
| `forget_submitter_ips` | archive | nightly cron (`deploy/OVH.md`) — RODO retention |
| `forget_claim_ips` | consent | nightly cron — same, except approved rows, which are the evidence |
| `sweep_uploads [--hours]` | archive | nightly cron — unclaimed R2 objects |
| `sweep_people` | archive | proposals with no post of any status after 30 days |
| `seed_portraits` | portraits | development data |
| `make_share_images` | share | draws the three 1200×630 fallback cards into `frontend/static/`; committed |

## Migrations

17 across six apps (`share` has no models). Four carry data: `accounts/0002` seeds the trusted
domains from `trust.TRUSTED_DOMAINS_SEED`; `archive/0003` back-fills the search columns;
`archive/0007` files every existing person with `people.py`'s pure functions; `archive/0008` seeds
the 35 subjects and back-fills `Person.name_key`. **A data migration imports the rule module's
functions rather than copying them**, and back-fills eagerly rather than on next save.

## Writing tests here

Tests live beside the app; a topic that outgrows `tests.py` gets `test_<topic>.py` (archive has
eight, escalation three). `test.md` says what each pins. Reach escalated rows through
`Post.all_objects`; drive R2 through `set_client_for_tests`; mail is the console backend. When a
whole class of tests starts failing with 429, it is the shared throttle cache — set
`FUWLOL_CACHE_DIR`.
