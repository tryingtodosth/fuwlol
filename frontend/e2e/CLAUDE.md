# e2e/ — five check-counting browser scripts (playwright-core, no framework, no CI)

`playwright-core` with the cached Chromium against **both real dev servers** and the demo seed.
Sequential check-counters printing pass/fail lines; zero `pageerror` / console errors is part of
every pass condition. `test.md` §2 says what each script pins and reads. Password everywhere is
`fuwlol123` (DEBUG only): `dziekan` (staff + head-admin), `doktorant` (trusted), `claude-slop` (a
plain account — `survey.mjs`'s `student` role). Scripts log in through the API and inject the token
with `localStorage.setItem('fuwlol.token', …)` after visiting `/logowanie`; `smoke.mjs` also drives
the login **form** on purpose.

## Traps that have each burned a real session

1. **The throttle file cache outlives everything.** `register` 10/h, `verify` 5/h, guest chat 20/h,
   consent claims 3/h — per IP, counted in `backend/cachedata/` (or `FUWLOL_CACHE_DIR`), shared with
   the dev server and surviving restarts. A second `npm run e2e` in the same hour fails its last
   checks with 429, which looks exactly like a regression. Start the test API with `FUWLOL_CACHE_DIR`
   pointing at a scratch directory, or clear the directory with the API stopped.
2. **`:8000` and `:5173` may be somebody else's dev servers** on the same machine, and a screenshot
   of "fuw.lol" is then another project's 404 page. Start on other ports, set `FUWLOL_CORS_ORIGINS`,
   `PUBLIC_API_BASE_URL` (process env beats `frontend/.env`) and `FUWLOL_SITE_URL`, pass `E2E_FRONT`
   / `E2E_API`, and check which application answers (`ss -ltnp`, then a request) before believing
   anything. `escalation.mjs` still hardcodes the default ports.
3. **Editing files while a script runs** triggers a Vite reload underneath it — fake failures. Vite's
   dependency optimizer can also reload the page the first time a heavy import (KaTeX, LaTeX.js) is
   pulled in; a dialog opened before that reload simply vanishes. Warm the page once before
   believing a timeout.
4. **`render-guard.mjs` writes to the development database** through the ORM (`E2E_BACKEND_DIR`,
   `E2E_PYTHON`) — that is the point of it (the admin-panel path that bypasses the API guard). Run it
   against a database you can re-seed.
5. **Servers started from a shell die with it.** `setsid nohup … &` for both halves; check they are
   still up before blaming the script.
6. **`survey.mjs` asserts nothing.** It prints `ok <name> h=<height>` or `FAIL` and collects page
   errors; the value is in opening the PNGs side by side (four roles at 1280 px, the anonymous set
   at 390 px). The people-picker bugs and the layout regressions were found this way, not by a check.
7. **Whole-page text assertions are ambiguous** — scope every check to the box or table it means
   (`.evidence`, `.item`, `table.employers`); list order is newest-first and has flipped a check.
8. **A staff account proves nothing about a rule** — assert refusals as `claude-slop` or anonymously,
   and trusted-tier visibility as `doktorant`. A nuked title visible to `dziekan` is correct; visible
   to `doktorant` it is a bug.
9. **Cleanup through the real API, then re-query.** `escalation.mjs` hides its scratch message at
   the end; a script that creates a post should hide or reject it the same way rather than leaving
   the queue to grow across runs.

## Conventions

Read the front and API from `E2E_FRONT` / `E2E_API` with the `run.sh` defaults; take screenshots
into `E2E_SHOTS` (gitignored `screenshots/`, `survey/`); one `check(name, condition)` per fact;
finish with a count and a non-zero exit on any failure. A new script gets a `package.json` entry and
a row in `test.md` §2.
