# fuw.lol — engineering contract

An unofficial, community-run archive of the *funny* side of the Faculty of Physics, University of
Warsaw — memes, quotes, legendary exam problems, scans, stories — filed by category, person, subject
and year, moderated, with a trusted tier for anybody with a faculty e-mail, a legal escalation path
for the one class of content nobody may look at, and a look that copies fuw.edu.pl on purpose.
Django REST Framework API + SvelteKit SPA. The interface is Polish only.

**This file is what you need to write code here.** It is deliberately short. Everything else:

| File | Holds | Read it when |
|---|---|---|
| `README.md` (Polish) | the feature tour, how to run it, the structure | you are new |
| `DESIGN.md` | the *why* of every subsystem: measurements, decisions, what broke and how it was found | you need to know why something is the way it is |
| `PRODUCT.md` | what it is and is not, the tiers, product decisions, what is left open | you decide what a feature should do |
| `LEGAL.md` | the two takedowns, consent, RODO, DSA, the Dyżurnet step | you touch moderation, personal data, uploads or the terms |
| `SECURITY.md` | the standing security posture and its accepted risks | you touch rendering, uploads, throttles, headers |
| `test.md` | every suite and browser script: what it pins, how to run it | before writing or running a test |
| `backend/MODERATION-API.md` | the trusted-tier / moderation / escalation / R2 / chat API, endpoint by endpoint | you change or call those endpoints |
| `deploy/OVH.md` | the production runbook and the post-deploy checks | you deploy, or production misbehaves |
| `backend/CLAUDE.md`, `frontend/CLAUDE.md`, `backend/<app>/CLAUDE.md`, `frontend/e2e/CLAUDE.md` | scoped rules and traps | always, for the part you are editing |

When a scoped file and this one disagree, the scoped file wins. When `DESIGN.md` and the code
disagree about the present, the code wins.

---

## The shape of the thing

```
frontend/  SvelteKit 2 + Svelte 5 runes + TS, adapter-static SPA (ssr=false, prerender=false, fallback 200.html)
             routes/ + lib/components/  →  lib/api.ts (the only fetch())  →  HTTP
             lib/render/{markdown,latex,guard,media}.ts — the two renderers and their guard
             nginx.conf — the production web server: CSP, /media sandbox, scraper routing
backend/   Django 5.2 + DRF. 7 apps + config/. SQLite locally, Postgres in production.
             views  →  a rule module  →  models
deploy/    OVH runbook, Caddyfile, firewall.sh, backup.sh.   .github/workflows/deploy.yml IS the deploy.
docs/      the Polish draw.io documentation deck and the Gemini research reports.
```

The 7 apps, each with its own `CLAUDE.md`: `accounts` (tiers) · `archive` (everything about a post:
models, API, people, subjects, search, uploads, guards, suggestions) · `board` (the chat) ·
`consent` (a person's own say about their image) · `escalation` (NASK) · `portraits` (elected
profile photos) · `share` (link previews + sitemap, no models).

**Two boundaries are load-bearing and everything else follows from them:**

1. **`frontend/src/lib/api.ts` is the only `fetch()`.** It holds the token, appends
   `Authorization: Token …`, and turns a DRF error body into `ApiError.describe()`. Components and
   routes call `api.get/post/patch/delete` or a `lib/*.ts` helper built on it; none of them fetches.
2. **A rule that more than one endpoint needs lives in one module, and the endpoints ask it.**
   `archive/people.py` (whose post is whose, which people are visible), `archive/moderation.py`
   (who may see, hide, nuke), `accounts/trust.py`, `consent/rules.py`, `portraits/rules.py`,
   `escalation/services.py` + `visibility.py`. `share/previews.py` asks all of them rather than
   restating one. Serializers blank what a caller may not see; views do not filter by hand.

---

## Shapes that repeat

- **One `status` field per lifecycle, never two booleans** — `Post` (7 values), `Portrait`,
  `PersonClaim`, `Escalation`, `EditSuggestion`. `Post.objects`, the DEFAULT manager, excludes
  the two critical statuses (`quarantined`, `purged`); `Post.all_objects` is the escape hatch and
  every use of it is deliberate.
- **Visibility is derived, never toggled**: `visible_people`, `visible_posts_q`,
  `portraits.rules.visible_q`, `is_escalated` — the last one fails **closed**.
- **A refusal carries its reason** (`upload_block_reason`, `vote_block_reason`, the consent
  errors) and the frontend has a sentence for each — **except where a reason would be an
  oracle**: unknown slug, unlisted person, opted-out name match, already escalated, nuked to a
  non-staff caller all get the same 404 or the same one sentence.
- **Every transition writes a row**: `ModerationAction`, `PortraitAction`, a new `PersonClaim`
  (the old one `superseded`, never edited), `Escalation`, `EvidenceAuditLog` (append-only: saving
  an existing row or deleting one raises).
- **Mirrored constants say so in both files**: `archive/latexguard.py` ↔ `lib/render/guard.ts`
  (the server's copy counts); `archive/search.normalize_text` ↔ `editor/chips.ts` `fold`;
  `share/previews.plural` ↔ `lib/plural.ts`; `consent/rules.WISH_LABELS` ↔ `lib/consent.ts`
  `WISHES`; `share/views.CRAWLER_UA` ↔ the `map` in `frontend/nginx.conf`; `board.MAX_LEN` 2048;
  the report-reason lists. Change one, change the other, keep the comment that names it.

---

## House rules

Each was learned by something breaking. The half-specific ones are in `backend/CLAUDE.md` and
`frontend/CLAUDE.md` — read those too.

**1. Polish for people, English for code.** Every user-facing string, URL segment (`/ludzie`,
`/wpis/`), commit message and demo name is Polish; identifiers, comments, docstrings and these
docs are English (`README.md` and `docs/` are Polish for the humans who run the site). There is no
message catalogue — copy lives in the component that shows it, and the backend's refusal strings
are Polish sentences the frontend displays verbatim.

**2. Verify by running it, not by reading it.** `svelte-check`, the suite and the build have all
passed cleanly on bugs one browser click found: the people picker's listbox reopening over the next
field, Enter creating the very duplicate the picker exists to prevent, a nesting bomb that silently
killed every other formula on the page. Drive the real servers, run `npm run survey`, and **look at
the screenshots**. `frontend/e2e/CLAUDE.md` lists what makes a browser script lie.

**3. Judge a file by its bytes, never by its name or Content-Type.** Pillow must decode an image
after a header pixel check; a PDF must start with `%PDF`; audio and video carry their signature;
JPEG/PNG/WebP are re-saved without EXIF; GIF keeps its bytes (animation). Stored names are UUIDs,
`original_name` is untrusted input. The same validators run on a multipart upload, on an R2 object
pulled back at post creation, and on a portrait.

**4. A guard runs on every write path *and* on read.** `check_source` on posts, comments and chat;
`checkSource` before LaTeX.js *and* before KaTeX typesets. The read half of the KaTeX path was
missing until 17.09.2026 — content that reaches the database some other way (the Django admin, an
old row) must still be inert in every reader. DOMPurify enforces the image allow-list on the DOM,
not with a regex over the source.

**5. No oracle below head-admin.** Escalated content is 404 to everyone else, and so is a second
escalation attempt; a nuked post is 404 to non-staff; a proposed person is invisible to strangers;
a link preview of a hidden post is byte-identical to one of a slug that never existed. Two different
refusals to a stranger are one leak, and a preview leak outlives the takedown in somebody else's
cache.

**6. Tombstone, hide, supersede — do not delete.** Comments tombstone, claims supersede, portraits
hide, hidden posts keep their previous status for the restore. The one deliberate destruction is the
purge, and it happens in one order — audit rows commit, bytes die, the row is marked — because the
opposite order is unrepairable (`LEGAL.md` §6).

**7. Flag it, don't fake it.** Presign answers 503 when R2 is unconfigured; the CDN purge logs when
it cannot run; a partial shred is a 409 naming the survivors; there is no malware scanner and the
docs say so; `seed_demo` never resets a password.

**8. The client address is the N-th from the right.** `FUWLOL_PROXY_HOPS` (3 in production:
Cloudflare → Caddy → nginx); `CF-Connecting-IP` only under `FUWLOL_CLOUDFLARE=1`, which is safe only
because `deploy/firewall.sh` lets nobody else reach the origin. Every per-IP throttle stands on this.

**9. Push to `main` is the deploy.** The workflow runs the suite, `makemigrations --check`,
`svelte-check` and the build first — not the browser scripts — then ships images to the VPS. Commit
on `main` only what may go live; **ask before pushing**; roll back with an older `IMAGE_TAG`. A
commit message is one Polish sentence saying what changed for the reader.

**10. "Left open, not built" is part of the deliverable.** Finish the task, then write what you did
not do and why into `PRODUCT.md` "Left open" or the app's `CLAUDE.md`.

---

## Content pipeline (`frontend/src/lib/render/`)

Storage is the source exactly as typed — Markdown with `$…$` maths (`format=text`) or a LaTeX
document (`format=latex`) — and files are referenced in it by **original name**. Both renderers are
imported lazily and end in one DOMPurify configuration (no `class`; `<img>` only for an attachment
URL or a preview blob). **text**: lift the maths out → `marked` → splice it back → sanitize →
`typeset()` runs `checkSource` and then KaTeX. **latex**: `checkSource` → LaTeX.js in the browser
(there is no TeX engine anywhere) → `\includegraphics` → the same sanitizer. The guard is the twin
of `archive/latexguard.py`; the exact order, options and limits are in `frontend/CLAUDE.md`.

---

## API conventions

```
/api/auth/{register,login,logout,me,verify/request,verify/confirm,trusted-domains}/
/api/{categories,people,subjects,tags,posts,reports}/         posts/{random,timeline,stats,mine,queue}/
/api/posts/<slug>/{react,comments,moderate,suggestions,revisions,feature,hide,restore,nuke,escalate}/
/api/comments/<id>/{hide,restore,nuke,escalate}/   /api/moderation/board/   /api/uploads/presign/   /api/wayback/
/api/people/<slug>/{aliases,claims,portraits}/    /api/claims/…    /api/portraits/…    /api/suggestions/…
/api/board/  (+ rss/, <id>/{hide,restore,report,escalate}/)    /api/moderation/{escalations,evidence-audit}/…
/share/<any path>  + /share/sitemap.xml   — scrapers only, routed by User-Agent in nginx
```

- `Authorization: Token …` (DRF TokenAuthentication); the token lives in `localStorage`
  (`fuwlol.token`) — an accepted risk, `SECURITY.md`.
- **Public GET for what is published; everything else scoped.** 404 for what you may not see,
  403 for what you may see but not do (trusted asking for staff's un-nuke), 400 malformed,
  **409 means the world moved** (a nickname owned by another person, a shred that left copies).
- Ids: slugs for categories, people, subjects, tags and posts; numeric pk for comments, claims,
  portraits, suggestions and escalations.
- Lists paginate with DRF's `PageNumberPagination` (20) where a ViewSet lists; the custom actions
  have their own envelopes, and `lib/queues.ts` `queueSize()` knows all four shapes.
- `portraits.urls` and `consent.urls` are included **before** `archive.urls` because the router is
  greedy on `people/<slug>/`. Keep that order.

---

## Frontend routes

```
/  /przegladaj  /os-czasu  /losowe  /wpis/[slug]  /dodaj  /edytuj/[slug]  /moje
/ludzie  /ludzie/[slug]  /ludzie/[slug]/{potwierdz,ustawienia}  /ludzie/zgoda  /przedmioty  /przedmioty/[slug]
/czat  /tablica  /moderacja  /moderacja/{zgody,portrety}  /eskalacje
/logowanie  /rejestracja  /potwierdz  /konto  /o-archiwum
```

---

## Running, testing, environment

```bash
./setup.sh   # .venv at the repo root, deps, migrate, seed_demo, npm install
./run.sh     # API :8000 + frontend :5173, CORS kept in step; Ctrl+C stops both
```

- Python 3.12, one venv at the repo root. From `backend/`:
  `FUWLOL_CACHE_DIR=<scratch> ../.venv/bin/python manage.py test` (374 tests, about 4 min on
  SQLite), `manage.py check`, `manage.py makemigrations --check --dry-run`.
- Node 22 (what CI runs). From `frontend/`: `npm run check` (0 errors is the bar), `npm run build`
  (CI builds with `PUBLIC_API_BASE_URL=/api`), and with both servers up the browser scripts
  `npm run e2e`, `e2e:escalation`, `e2e:research`, `e2e:render-guard`, `survey <outdir>` — `test.md`.
- **Ports taken?** Start on others and set *three* things: `FUWLOL_CORS_ORIGINS`,
  `PUBLIC_API_BASE_URL` (process env beats `frontend/.env`) and `FUWLOL_SITE_URL` (or every
  server-built link says 5173). Browser scripts take `E2E_FRONT` / `E2E_API`; `escalation.mjs`
  still hardcodes the defaults. Check which application answers a port before trusting a screenshot.
- **Throttle counters live in a file cache** (`backend/cachedata/`, `FUWLOL_CACHE_DIR`) shared by
  the dev server, the suite and the browser scripts, and they outlive restarts: a second e2e run in
  the same hour fails with 429 and looks like a regression. Point the suite and test servers at a
  scratch `FUWLOL_CACHE_DIR`, or clear the directory with the API stopped.
- Demo accounts (`FUWLOL_DEBUG=1` only): `dziekan` (staff + superuser = head-admin), `doktorant`
  (trusted), `claude-slop` (a plain account; `survey.mjs`'s `student` role), password `fuwlol123`.
- A bare clone needs no daemon: R2 unset means uploads go through Django, mail goes to the console
  (the verification link is printed in the API log), the cache is a directory. `DATABASE_URL` set
  means Postgres — what production runs.
- Under `backend/`, `db.sqlite3`, `media/`, `cachedata/` and `evidence/` are gitignored *state*;
  `evidence/` holds escalation packages — do not clean it casually.
- Servers started from a shell die with it: `setsid nohup … &` when you need them to outlive you.

---

## Known engineering gaps

Long-standing, still true. Feature-level gaps are in `PRODUCT.md` "Left open".

- **No mail beyond the verification SMTP**: password reset, the DSA receipt confirmation and the
  head-admin alert for a new escalation all wait on it.
- **No CI for the browser scripts, no frontend unit tests.** `npm run check` plus the five scripts
  in `frontend/e2e/`, run by hand.
- **Search is `LIKE` over two derived columns** (`search_text`, `search_math`); the Postgres half
  (`hunspell-pl`, `pg_trgm`) is not built because there is no Postgres locally.
- **LaTeX.js runs on the main thread** — it builds a DOM, so a Web Worker with `terminate()` would
  need a DOM emulation in the bundle. The size caps are a compromise, not a proof.
- **nginx cannot be tested locally** — there is none outside the `web` image. After touching
  `frontend/nginx.conf`, `docker compose exec web nginx -t` on the box is the first check.
- **`docker-compose.yml` still describes the superseded Coolify setup**; production is
  `docker-compose.prod.yml`. Both are kept valid on purpose (`deploy/HETZNER.md`).
