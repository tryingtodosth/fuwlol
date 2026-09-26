# frontend/ — SvelteKit 2 + Svelte 5 runes + TS, adapter-static SPA, Polish only

Scoped context for frontend work. The root `CLAUDE.md` holds the cross-cutting rules, `DESIGN.md`
the reasoning ("Look", "Rendering", "Naming a person into existence", "The time machine"),
`e2e/CLAUDE.md` the browser-script traps. 26 route pages, 14 top-level components plus `board/`,
`editor/` and `timemachine/`.

## The look is a measured copy of fuw.edu.pl — keep measuring, don't restyle

Measured on m.fuw.edu.pl on 20.09.2026 (www.fuw.edu.pl sends every visitor there) with a headless
browser reading computed styles: Tahoma 13px/1.5 `#444`; plain headings (normal weight, 16/15/14
px); an **amber** `#fdba45` banner and the `#175e4c` nav, both 1000 px centred over the 900 px
column, which `.page` insets by 32/36 px; boxes with 1 px `#bbb` borders and **bold 16 px orange
(`#ee8d30`) title bars**; news headlines 15 px normal weight in rust behind the faculty's own
asterisk (`static/img/asterisk-small.png`, a 16 px indent), justified text indented the same, the
picture floated left at 170 px, "| Więcej" plain, nothing between items; on a phone the grey
hamburger square inside the banner. Every subpage opens with `<Breadcrumb trail=[…]>` (`lib/components/Breadcrumb.svelte`; the front
page, like theirs, has none). An article is that breadcrumb, an `h1.ce_headline` behind
the 10 px orange bar, a grey 14 px `.info` line, `.ce_text` with a 315 px picture floated left,
and „Wróć". The front page is two columns (`.subcolumns`, 66/33). `/ludzie` copies
`osoby-fuw.html` down to `table.employers` and the faculty's own silhouettes
(`static/img/anonymous{ma,fe}bw.png`, plus our neutral `anonymousbw.png` for an unset `sex` — never a
text box, their page always shows a picture). **`src/app.css` holds all of it as reusable classes** and
`DESIGN.md` "Look" has every number and where it was read; a new measurement goes into both. The
point is recognition, so "nicer" is wrong. **A redesign is a new `VersionV<n>.svelte`** registered
in `timemachine/versions.ts`, with the previous version's styles pinned inside its own file — that
is what lets an old date in the time machine render the look the site actually had.

## The layer boundary

`lib/api.ts` is the **only** `fetch()` (two call sites, both inside it). It reads
`PUBLIC_API_BASE_URL` from `$env/dynamic/public` (default `/api`), keeps the token in
`localStorage['fuwlol.token']` behind try/catch, sends `Authorization: Token …`, passes `FormData`
through untouched and JSON otherwise, and throws `ApiError` whose `describe()` unwraps a DRF body —
`detail`, field arrays, `non_field_errors` — into the Polish sentence the backend wrote, with
fallbacks for 401/403/404/429. `downloadBlob(path)` exists because a plain `<a href>` cannot carry
the token (escalation evidence). Components and routes call `api.get/post/patch/delete` or a
`lib/*.ts` helper (`consent.ts`, `portraits.ts`, `queues.ts`); only two files import `API_BASE` for
URL work, never to fetch. `lib/auth.svelte.ts` is the rune singleton (`user`, `ready`,
`isAuthenticated`, `isStaff`, `isHeadAdmin` = `is_superuser`); `init()` clears the token on 401.

## Rendering (`lib/render/`) — two renderers, one sanitizer, guard on read

- `markdown.ts`: `liftMath()` pulls `$$…$$`, `\[…\]`, `\(…\)`, `$…$` out **before** `marked`
  (gfm, breaks) and splices them back escaped — otherwise `*` and `_` inside a formula are Markdown.
  Then DOMPurify (30 tags, `href src alt title target rel`, **no `class`**, URI regexp
  `https?|mailto|blob|/`), with hooks that drop any `<img>` whose `src` is not in the allow-set
  (`withAllowedImages`, `trackingResolver`) plus `srcset`/`loading`, and force `target=_blank
  rel="nofollow noopener"`. `typeset(el)` then runs `checkSource(el.textContent)` and **bails
  silently** on a hit before lazily importing KaTeX `auto-render` (`maxExpand 1000`, `maxSize 25`,
  `throwOnError false`; `ignoredTags` includes `pre code a`).
- `latex.ts`: `checkSource` → lazy `latex.js` → the `FUWIMGMARK` marker swapped for `<img>` so
  `width=0.5\textwidth` becomes 50 % → the same sanitizer with `foreignObject`, `annotation-xml`,
  `maction`, `xlink:href` and data attributes forbidden. There is no TeX engine anywhere: the
  editor's „Rekompiluj" and the post page run this same function.
- `guard.ts` is the twin of `backend/archive/latexguard.py` — identical caps and regexes, **the
  server's copy counts**, both files say so. It checks a whole element, as the backend checks a
  whole body; a post mixing a bomb with an honest formula loses both — safe, not precise.
- `media.ts` maps an attachment's *original name* (case-insensitive, extension-less LaTeX names too)
  to its URL; the editor previews unsaved files through the same resolver with object URLs.
- Both libraries are imported at the point of use; a page without content pays nothing. Keep it so.
- External images are refused (a hot-linked picture is a tracking pixel fired at every moderator).

## Svelte / build facts that are not where you expect them

- **There is no `svelte.config.js`.** The adapter lives in `vite.config.ts`:
  `adapter({ fallback: '200.html', strict: false })`, with `compilerOptions.runes` forced for
  everything outside `node_modules`. `src/routes/+layout.ts` sets `ssr = false; prerender = false`
  — a pure SPA, nothing runs at build time.
- `lib/render/latexjs.scoped.css` is **generated** by `scripts/scope-latexjs-css.mjs` (LaTeX.js
  ships `body`/`h2`/`.list` selectors; the script scopes them under `.latex-doc`) from `npm run
  prepare`, and **committed** so a clone builds either way. The Dockerfile runs `npm ci
  --ignore-scripts` and then `npm run prepare` after `COPY . .` — at `npm ci` time the script's
  input does not exist yet.
- CI builds with `PUBLIC_API_BASE_URL=/api`; the dev `.env` names a host. Build it CI's way once
  before pushing anything that touches URLs.
- `lib/dialog.svelte.ts` `dialog.ask()` + `<ConfirmDialog>` in the root layout replace
  `window.prompt()`; a destructive action's button stays disabled until a reason is typed.

## The editor (`components/editor/`)

`PostEditor.svelte` (`MAX_FILES` 6, `MAX_BYTES` 25 MB — mirrors `settings.py`; a draft in
`localStorage`; asks `/api/uploads/presign/` and PUTs straight to R2 when it answers, multipart when
it answers 503). All three filing axes are one typeahead, `TagPicker.svelte`, a real ARIA combobox
(`aria-expanded` / `aria-controls` / `aria-activedescendant`, arrows, Enter, Escape, Backspace takes
the last chip back); typing a name that is not there offers to add it — a two-line mini-form for
title and role, then a chip marked „nowa". `chips.ts` `fold` mirrors `archive/search.normalize_text`
(the backend's `name_key` is authoritative). Caps: five new people and six subjects per post. **Two of
this component's three bugs were found only in a browser**: the listbox reopening over the next field
after a chip was taken (a `focus()` that fired `onfocus`), and Enter creating the very duplicate the
picker exists to prevent when pressed before the previous query's results had settled.

## The time machine (`components/timemachine/`)

`eras.ts` `eraFor(date)` is one pure function: ≥ `SITE_LAUNCH` (2026-09-10) → our archive as of
that day (`?before=`), rendered by the layout version in force then (`versions.ts` `SITE_VERSIONS`
— v1 for 10–19.09.2026, v2 since; the registry a redesign **appends** to, keeping the old component
with its styles pinned, so an old date renders an old look); `WAYBACK_EARLIEST` (1998-01-20) ≤ d < launch → fuw.edu.pl from the Internet Archive in an
iframe (`/api/wayback/` for the caption); 1816 → a Polish paper; 1795 → German; 1400 → Latin;
then cave paintings, dinosaurs, and before the Big Bang nothing. The Big Bang animation plays on
every journey to before fuw.lol existed. Only the home page has one.

## Mirrors of backend values (say so in both files)

`types.ts` `Status` has five values — the critical statuses are never sent to the client;
`PostSummary.trusted_only` mirrors `archive/models.py::Post.trusted_only` („kontrowersyjne") while
`locked` / `lock_notice` are **derived per caller** by `moderation.can_read_body` — draw the badge
from the first and the wall from the second, and never re-derive `locked` here, or the author's own
exception drifts from the server's;
`EscalationStatus` has three (no `purged`). `REACTIONS`, `Sex`, `ImageConsent`, the two
report-reason lists (`routes/wpis/[slug]`, `routes/moderacja`, `board/types.ts`), `board/types.ts`
`MAX_LEN` 2048, `lib/consent.ts` `WISHES` (labels byte-identical to `consent/rules.WISH_LABELS`),
`lib/portraits.ts` statuses / decisions / sorts / `CONSENT_PAGE`, `lib/plural.ts` ↔
`share/previews.plural`, `chips.ts` `fold` ↔ `normalize_text`, `render/guard.ts` ↔ `latexguard.py`.

## `nginx.conf` lives here and is the production web server

The User-Agent `map` mirrors `share/views.CRAWLER_UA`; a path containing a dot is a file, never a
route; `try_files $uri /200.html` deliberately without `$uri/` (that was a 403 on `/`). The CSP and
the other headers are repeated inside `location /` because `add_header` does not inherit. `/media/`
gets `default-src 'none'; sandbox` and PDF/TXT/TEX as attachments; `client_max_body_size 160m`.
There is no nginx locally — `docker compose exec web nginx -t` on the box is the first check after a
change (`deploy/OVH.md`).

It also carries `location /fwumu/`, which is **not this app**: it proxies FwUMU (the `skoki`
container, a separate repository) onto this origin. The `proxy_pass` goes through a variable with a
`resolver` so that a missing side app cannot stop nginx — and therefore the archive — from starting;
that is the one line to leave alone if you touch it.

## Copy

Polish, in the component that shows it; no catalogue. Refusals from the backend are Polish sentences
shown verbatim through `ApiError.describe()` — if a new refusal reads badly, fix the sentence in the
rule module, not in the component.

## Verify

`npm run check` (0 errors), `npm run build`, then the real thing: `npm run e2e` and friends against
both servers, and `npm run survey <dir>` **for looking** — `e2e/CLAUDE.md`, `test.md`.
