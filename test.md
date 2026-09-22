# Testing fuw.lol

Two kinds of test, deliberately different:

| | What it is | Where | Count |
|---|---|---|---|
| **Backend** | Django's test runner against a throwaway database | `backend/*/tests.py` and `test_*.py` | 374 (see below) |
| **Browser** | `playwright-core` driving the real frontend against the real backend | `frontend/e2e/*.mjs` | 5 scripts |

The Django suite pins **rules** — who may see what, what is refused and why — because those fail
silently. The browser scripts pin **what a person experiences**, which no unit test reaches: three
of the real bugs in the people picker, and the nesting bomb that killed every other formula on the
page, were found only by looking. CI (`.github/workflows/deploy.yml`) runs the Django suite,
`makemigrations --check`, `svelte-check` and the production build on every push to `main` — and
**not** the browser scripts. Run those yourself, and say so in the commit or the board entry.

---

## 1. Backend

```sh
cd backend
FUWLOL_CACHE_DIR=/tmp/fuwlol-test-cache ../.venv/bin/python manage.py test          # everything
../.venv/bin/python manage.py test escalation                                        # one app
../.venv/bin/python manage.py test archive.test_people_naming                        # one module
../.venv/bin/python manage.py test archive.test_content_guards.ContentGuardTests.test_deep_nesting_is_refused_without_touching_a_forbidden_primitive
```

`--keepdb` reuses the test database, `-v 2` names every test, `--failfast` stops at the first
failure. Nothing needs to be running first and nothing touches `db.sqlite3`.

**Set `FUWLOL_CACHE_DIR` to a scratch directory.** Throttle counters live in a *file* cache
(`backend/cachedata/` by default) that the dev server shares and that outlives every process. A
suite that registers or verifies a few times spends the same hourly budget the dev server and the
browser scripts spend, and a 429 in the middle of a test looks exactly like a regression.

### What each file pins

| File | Tests | Covers |
|---|---|---|
| `accounts/tests.py` | 24 | registration, login (per-IP and per-username throttles), `/me/`, trusted-domain matching (`x@fuw.edu.pl.evil.com` does not match), verification request/confirm, 24 h single-use tokens, masking |
| `archive/tests.py` | 19 | posts, attachments referenced by original name in one multipart request, reactions, comments, reports, timeline, random, catalogue numbers |
| `archive/test_content_guards.py` | 14 | `latexguard.check_source` on posts, comments and chat: the `\def` family, recursive `\newcommand`, length, environment count, the depth cap that touches no forbidden primitive |
| `archive/test_locked.py` | 22 | „kontrowersyjne" (`trusted_only`): the teaser keeps the title and loses body, summary, cover, filing and counts; the author and the trusted tier read it; the body is not searchable (prose **and** formulas) and not reachable through the person filter; comments, reactions and suggestions refuse (a suggestion's `base` is a frozen body); a teaser is no view; who may set and unset it, and that every turn is audited |
| `archive/test_moderation.py` | 15 | the trusted tier: hide / restore / nuke on posts and comments, the board payload, what a non-staff caller sees of a nuked item, restore to the previous status |
| `archive/test_people.py` | 11 | filing by surname (`split_degree`, `derive_surname`, `sort_key_for`, `letter`), nicknames as alias tags, `annotate_people` counting a post once across both joins, alias ownership 409 |
| `archive/test_people_naming.py` | 22 | naming a person into existence: reuse on `name_key`, visibility derived from a published post, opted-out match refused, five-per-post cap, `is_new` on the queue card, `sweep_people` |
| `archive/test_subjects.py` | 17 | subjects: seeded rows always offered, named rows listed once published, slug folding keeps `ł`, `retrieve` never narrows, six-per-post cap, merge |
| `archive/test_suggestions.py` | 23 | reader edit suggestions and post revisions: who may decide, snapshots, accept / reject / withdraw, what the author sees |
| `archive/test_uploads.py` | 15 | presign (signed over length and checksum, 503 when R2 is off), `verify_stored`, EXIF stripped and the *stored* hash recorded, keys outside `public/attachments/` refused, `sweep_uploads` |
| `board/tests.py` | 38 | the chat: guests, nick ≠ username, 2048 chars, no images, ≤ 5 links, honeypot, paging by id, RSS, reports (self-report 403, one per user, three trusted auto-hide), reputation ±1, hide / restore, escalation blocking moderation |
| `consent/tests.py` | 31 | claims: request, mailbox confirm, precautionary tightening at a trusted domain, staff decide, `ConsentHide` reverting exactly what a claim hid, supersede on change, manage link, withdraw, throttles, `forget_claim_ips` |
| `escalation/tests.py` | 25 | escalate → invisible to everyone but head-admin (lists, detail, RSS, board, admin), evidence frozen in the same transaction, decide, files quarantined and released, no oracle |
| `escalation/test_hardening.py` | 22 | the 19.09 closures: R2 objects moved to the private `held/` bucket, CDN purge called (and logged when unconfigured), grantable head-admin permission, 5-minute previews |
| `escalation/test_purge.py` | 24 | the purge: refuses unless approved and `confirmed_dispatch`, audit rows before bytes, every copy destroyed, 409 with survivors on a partial shred, retry does not duplicate audit rows, `EvidenceAuditLog` append-only |
| `portraits/tests.py` | 31 | gallery gated on `granted`, `visible_q` re-checks for everyone, one movable vote, election with the older winning a tie, trusted publish at once, caps, `PortraitAction`, queue |
| `share/tests.py` | 46 | link previews: every route kind, hidden / nuked / escalated / restricted posts get the generic card and a 404 byte-identical to a missing slug, absolute image URLs, person cards, sitemap, crawler detection, human redirect, `FUWLOL_SPA_INDEX` splice mode |

The counts are `def test_` per file as of 2026-09-22; re-count rather than trust them after adding tests.

### Conventions

- Tests live beside the app; a topic that outgrows `tests.py` gets its own `test_<topic>.py`.
- `FUWLOL_DEBUG` defaults to `1`, so the suite needs no secret key and runs on SQLite. Nothing in
  it touches R2 (`config/r2.set_client_for_tests` is the seam) or sends real mail (console backend).
- A test that needs escalated content reaches it through `Post.all_objects` — the default manager
  will not show it, which is the point.

---

## 2. Browser scripts

`playwright-core` with the cached Chromium; no framework, no X server. Sequential check-counters
printing a pass/fail line each; zero `pageerror` / console errors is part of every pass condition.
Both dev servers must be up with the demo seed (`manage.py seed_demo`). Password everywhere is
`fuwlol123` (DEBUG only). Scripts log in through the API and inject the token with
`localStorage['fuwlol.token']` after visiting `/logowanie`.

| Script | `npm run …` | Drives | Reads |
|---|---|---|---|
| `smoke.mjs` | `e2e` | ~30 checks across the whole site: home (nav colour, chat widget, time machine), browse, a LaTeX post typesets, catalogue stamp, `/ludzie`, timeline, guest chat (nick, „(gość)", 100-char fold, maths, `rel=nofollow`, image refused), RSS, time-machine eras (2005 → Internet Archive iframe, launch day → own archive), student submits a post with an image → queue → staff publishes → renders inline, comment, hide / nuke, board stub, trusted vs nuked visibility, `/konto` badge, gmail refused with the institution list, `@fuw.edu.pl` accepted | `E2E_FRONT`, `E2E_API`, `E2E_SHOTS`, `E2E_SKIP_ANON`; logs in as `student`, `dziekan`, `doktorant` through the **form** |
| `escalation.mjs` | `e2e:escalation` | a trusted user escalates a chat message through the confirm dialog (button disabled until a reason is typed, Esc closes), the head-admin sees „NASK (1)" in the nav, reads the frozen evidence, declines, the message is public again; cleans up | `E2E_SHOTS` only — **front and API are hardcoded** to `:5173` / `:8000` |
| `research-followups.mjs` | `e2e:research` | what the Gemini research changed: Markdown-hostile maths survives, `x^{2}` finds `x^2`, `\frac` finds `\dfrac`, the report form is an art. 16 notice, `/dodaj` demands the rights declaration and warns about likeness, `/o-archiwum` has the regulamin, a `\def` bomb is refused with 400 | `E2E_FRONT`, `E2E_API`; `dziekan` |
| `render-guard.mjs` | `e2e:render-guard` | creates two bomb posts **straight through the ORM** (the admin-panel path that bypasses the API guard), then checks the reader never executes them, the page loads in bounded time, and an honest formula on another post still typesets | `E2E_FRONT`, `E2E_API`, `E2E_BACKEND_DIR` (`../backend`), `E2E_PYTHON` (`../.venv/bin/python`) |
| `survey.mjs` | `survey <outdir>` | screenshots every page for four roles (anonymous, `claude-slop` = student, `doktorant`, `dziekan`) at 1280 px, and the anonymous set at 390 px; prints `ok <name> h=<height>` or `FAIL` and collects every page error. **For looking, not asserting** — this is how the UX bugs were found | `E2E_FRONT`, `E2E_API`; out dir from argv (default `/tmp/fuwlol-survey`) |

```sh
cd frontend
E2E_FRONT=http://localhost:5273 E2E_API=http://localhost:8100/api npm run e2e
E2E_FRONT=http://localhost:5273 E2E_API=http://localhost:8100/api node e2e/survey.mjs /tmp/survey
```

### Traps

- **The throttle file cache.** `register` is 10/hour, `verify` 5/hour, guest chat 20/hour, consent
  claims 3/hour — and the counters survive restarts. A second `npm run e2e` in the same hour fails
  its last checks with 429. Start the API with `FUWLOL_CACHE_DIR` pointing at a scratch directory,
  or clear `backend/cachedata/` with the API stopped.
- **Ports.** `:8000` and `:5173` may belong to another project's dev servers on the same machine, and
  a screenshot of "fuw.lol" is then somebody else's 404 page. Start on other ports and set
  `FUWLOL_CORS_ORIGINS`, `PUBLIC_API_BASE_URL` (process env beats `frontend/.env`) and
  `FUWLOL_SITE_URL`; pass `E2E_FRONT` / `E2E_API`; check which app answers before believing a result.
- **Editing files while a script runs** triggers a Vite reload underneath it — fake failures.
- **`render-guard.mjs` writes to the development database** through the ORM. Run it against the
  dev database you can afford to seed again, not against anything you care about.
- **Servers started from a shell die with it.** Use `setsid nohup … &` for both halves.

More of these, and the conventions, in `frontend/e2e/CLAUDE.md`.

---

## 3. Static checks

```sh
cd backend && ../.venv/bin/python manage.py check && ../.venv/bin/python manage.py makemigrations --check --dry-run
cd frontend && npm run check && npm run build         # 0 errors is the bar; build with PUBLIC_API_BASE_URL=/api to match CI
```

`npm run build` alone does not prove the production shape: CI builds with `PUBLIC_API_BASE_URL=/api`
(same-origin behind nginx), so run it that way once before pushing anything that touches URLs.
