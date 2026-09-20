# fuw.lol — security posture

A standing assessment, not a changelog: what protects what, what is accepted rather than solved,
and how to check a claimed vulnerability before acting on it. Rewritten from the review of
16.09.2026 and the re-read of 17.09.2026; two entries were closed on 19.09.2026. `DESIGN.md`
has the reasoning behind each mechanism; `LEGAL.md` has the law it serves.

## Uploads — judged by bytes, renamed, stripped

- `archive/validators.py` decides what a file *is* from its bytes, never from its name or the
  browser's Content-Type: Pillow must decode an image, after a pixel count read from the header
  (`MAX_PIXELS = 40_000_000`) against decompression bombs; a PDF must start with `%PDF`; audio
  and video must carry their container signature; unknown extensions are refused. JPEG, PNG and
  WebP are re-saved without EXIF (a phone writes GPS into every photograph). GIF keeps its bytes
  because a re-encode kills animation, which is half of what a meme archive holds.
- Stored names are UUIDs (`attachment_path`); the uploader's filename survives only as
  `original_name`, which is untrusted input and the body's reference to the file.
- Caps: 25 MB per file, six files per post (`settings.MAX_UPLOAD_BYTES`, `MAX_FILES_PER_POST`);
  nginx `client_max_body_size 160m`.
- **Direct-to-R2 uploads** (`archive/uploads.py`, `config/r2.py`): the presigned PUT is signed
  over `ContentLength` and `ChecksumSHA256` as well as the key, so the size cap and the checksum
  are enforced by R2 rather than requested politely. At post creation `verify_stored` pulls the
  object back, runs the same validators, re-stores stripped JPEG/PNG/WebP and records the sha256
  of the bytes actually kept — a checksum in a NASK report must match the file the report is
  about. Unclaimed objects are deleted by `manage.py sweep_uploads` after a day. R2 unconfigured
  answers `503 {available: false}` and uploads go through Django — stated, never faked.
- **No malware scanner anywhere in this stack.** There is no ClamAV on the VPS and none in the
  images; a PDF is served as an attachment from a sandboxed `/media` and that is the extent of it.

## Rendering in the browser — two renderers, one sanitizer, three guards

- Both renderers (`lib/render/markdown.ts` for Markdown + KaTeX, `lib/render/latex.ts` for
  LaTeX.js) end in DOMPurify **with the image allow-list enforced on the DOM**: an `<img>`
  survives only if its `src` is one of the post's attachment URLs or a preview blob. The older
  regex over `![](url)` never saw reference-style images or raw tags, and a hot-linked picture is
  a tracking pixel fired at every moderator. `class` is not in the allowed attributes; `srcset`
  and `loading` are stripped; links get `target=_blank rel="nofollow noopener"`. For LaTeX.js
  output the sanitizer additionally forbids `foreignObject`, `annotation-xml`, `maction`,
  `xlink:href` and data attributes (mXSS through MathML/SVG).
- Maths is lifted out of the source **before** marked runs and spliced back afterwards, so
  `*` and `_` inside a formula are never Markdown.
- KaTeX runs with `maxExpand: 1000`, `maxSize: 25`, `trust: false`, `throwOnError: false`.
- **The macro guard** (`backend/archive/latexguard.py` ↔ `frontend/src/lib/render/guard.ts`,
  identical by contract, the server's copy is the one that counts) refuses: the `\def` family and
  other expansion primitives, a `\newcommand` or `\newenvironment` that refers to itself, more
  than 60 000 characters (10 000 in a comment), more than 400 `\begin{`, and a brace nesting deeper
  than 40. It runs on every write path — posts, comments, chat — **and on read**: `renderLatex`
  and `typeset()` both call the guard before compiling, so a row that reached the database some
  other way (the Django admin, an old row) is shown as plain text and never executed.
  The read half of the KaTeX path was missing until 17.09.2026 — KaTeX implements `\def`/`\edef`
  itself, ungated by `trust` — and the depth cap was added the same day after measuring that a
  `\sqrt{\sqrt{…}}` a few thousand levels deep, which touches no forbidden primitive, costs ~370 ms
  at 3000 levels and blows the JS stack at 8000, which `auto-render` does not catch, killing the
  typesetting of every *other* formula on the page silently. Both fixes were in our code, not the
  library. Regression tests: `archive/test_content_guards.py` and `npm run e2e:render-guard`
  (which creates the bomb straight through the ORM, exactly the path the guard on read exists for).
- The guard checks a whole element at once, as the backend checks a whole `body`: a post mixing a
  bomb with an honest formula loses the typesetting of both. Safe, not precise, by choice.

## HTTP layer

- nginx (`frontend/nginx.conf`) sends on every response: `Content-Security-Policy: default-src
  'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self'
  blob: data:; font-src 'self' data:; connect-src 'self'; frame-src https://web.archive.org;
  media-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors
  'self'`, plus `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`,
  `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: camera=(),
  microphone=(), geolocation=()`. The headers are repeated inside `location /` because
  `add_header` does not inherit. `/media/` is served with `Content-Security-Policy: default-src
  'none'; sandbox`, and PDF / TXT / TEX under it as attachments.
- Django outside DEBUG: `SECURE_PROXY_SSL_HEADER`, `USE_X_FORWARDED_HOST`, secure + httponly
  session cookie, secure CSRF cookie, nosniff, `strict-origin-when-cross-origin`, HSTS for a year
  with subdomains (preload deliberately off). `FUWLOL_DEBUG=0` is baked into the API image, and
  settings refuse to start with the default `SECRET_KEY` when DEBUG is off.
- **One URL answers differently by User-Agent** (scrapers get `/share/…`, humans the SPA shell), so
  Cloudflare must never get a "Cache Everything" rule on HTML — it honours `Vary` on
  `Accept-Encoding` only. HTML is outside its default cache set; keep it that way and keep the
  bypass on `/api/*` (`deploy/OVH.md`).

## The client address, and everything that depends on it

`config/middleware.py` takes the visitor's address as the **N-th entry from the right** of
`X-Forwarded-For` (`FUWLOL_PROXY_HOPS`; 3 in production: Cloudflare → Caddy → nginx), and reads
`CF-Connecting-IP` only under `FUWLOL_CLOUDFLARE=1` — which is correct only because
`deploy/firewall.sh` lets nobody but Cloudflare reach 80/443, so the header cannot be forged by
talking to the origin directly. The leftmost entry is the client's own and is the classic mistake.
At the wrong hop count every per-IP throttle keys on an edge address and one visitor's budget is
everybody's. `curl -I https://146.59.103.167` must fail from anywhere (`deploy/OVH.md`, check 2).

Throttles (DRF, counters in a **file cache** shared between workers and surviving restarts):

| Scope | Rate | | Scope | Rate |
|---|---|---|---|---|
| `register` | 10/hour per IP | | `board_anon` / `board_user` | 20/hour / 60/hour |
| `login` | 20/min per IP | | `board_report` | 20/hour |
| `login_user` | 10/min per **username** | | `report` | 20/hour |
| `verify` | 5/hour | | `escalate` | 10/day |
| `post_create` | 30/hour | | `presign` | 60/hour (one per file) |
| `comment_create` | 60/hour | | `claim_request` / `claim_manage` | 3/hour |
| `suggest` | 20/hour | | `portrait_upload` / `portrait_vote` | 10/hour / 60/hour |
| `anon` / `user` (defaults) | 300/min / 600/min | | | |

Per-action scopes on a ViewSet were a **silent no-op** until `FixedScopeThrottle`
(`archive/views.py`): DRF's `ScopedRateThrottle` reads the scope off the view, not the action.
Any new per-action limit must use it.

## Secrets, seeds, identities

- `/srv/fuwlol/.env` is never in git and never touched by a deploy; `FUWLOL_IP_SALT` hashes visitor
  addresses for the chat and the evidence manifests, and falls back to `SECRET_KEY` when unset.
- `seed_demo` never resets an existing password and, outside DEBUG, draws random ones and prints
  them once. `FUWLOL_SEED_DEMO` is `0` in production.
- Trusted-domain matching is strict: lowercase ASCII, one `@`, Django's validator, exact match,
  then a `.domain` suffix only where the row allows subdomains. `x@fuw.edu.pl.evil.com` and
  `x@gmail.com@fuw.edu.pl` do not match. Verification links are 24 h, single use; a new request
  voids the older ones.
- The Django admin hides escalated content too (`escalation/adminmixin.py`), so staff cannot reach
  it through the back door either.

## Escalation and evidence

Escalated content is invisible to everyone below head-admin — lists, detail, RSS, board, admin,
and every moderation action answers 403/404 — and `is_escalated` **fails closed**. Evidence is
frozen in the same transaction as the escalation (manifest plus file copies, `chmod 400`, one
sha256 over the package), because the author may delete the account or a moderator may restore
the message before anybody looks. Live files are *moved* out of `/media` (or from R2's public
prefix to the `held/` prefix of a **separate private bucket** — a custom domain publishes a whole
bucket, measured), the Cloudflare edge copy is purged by URL (`escalation/cdn.py`; unconfigured, it
logs rather than lies), and presigned previews for a head-admin live five minutes. The purge is
ordered — audit rows commit, bytes die, then the row is marked — and a partial shred is a **409**
naming the copies that survived. `LEGAL.md` §6 has the argument. Every step is a row and a line
in the `security` logger, which is configured on its own so a database-only compromise cannot
erase the trail.

## Who sees which fields

A reporter's e-mail and note are staff-only; a moderator's review note goes to the author only;
a nuked post is a stub (id, catalogue number, moderation block) to a non-staff trusted caller and
a 404 to everybody else; the consent audit line never carries the person's address; the
evidence-audit register, which holds uploader addresses, is head-admin only. The serializers
blank what a caller may not see rather than trusting views to filter.

## Accepted, not forgotten

- The API token lives in `localStorage` (`fuwlol.token`). CSP is the second line; an httpOnly
  cookie would be a different authentication model.
- One trusted account can escalate — and thereby freeze — any content, 10 a day, fully logged.
  That is the price of acting fast on the worst material.
- Throttles count attempts, not failures.
- The 60 000-character and 400-environment caps are a compromise against a pathologically large
  *legal* document, not a proof; LaTeX.js runs on the main thread because it builds a DOM and a
  Web Worker would need a DOM emulation in the bundle (`docs/gemini/note.md`).
- Between a presigned PUT and the post that claims it, an unvalidated object sits in the bucket
  under a random, unreferenced key for up to a day.
- `script-src 'unsafe-inline'` and `style-src 'unsafe-inline'` are in the CSP because SvelteKit's
  bootstrap and Svelte's scoped styles need them.

## Checking a "known vulnerability" claim

Test it against the library version this project actually installs before changing anything.
The safety report named GHSA-64fm-8hw2-v72w (`\edef` bypassing KaTeX's `maxExpand`); a 30-level
`\edef` cascade run directly against the installed KaTeX 0.18.7 threw `ParseError` in
milliseconds — already patched upstream, nothing to do. The same session then found two real gaps
the report had *not* named (the missing guard on the KaTeX read path, and the nesting bomb) by
trying the attacks rather than reading about them. A report is a list of things to try, not a
list of things that are true.
