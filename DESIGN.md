# fuw.lol — design notes

## What it is
An internet archive of the *funny* side of the Faculty of Physics, University of Warsaw —
folklore, not a news site: things that are only ever passed around by word of mouth, a
group chat, or a scan somebody keeps. The value is that it is one place, browsable by
category/person/year, moderated, and that a post can be *written* — a legendary exam
problem needs LaTeX, a meme needs a picture, a story needs a paragraph.

## Look: a copy of fuw.edu.pl, on purpose
Measured from the real site (Sept 2026): Tahoma 13 px `#444`, a ~70 px light-grey banner
with the logo left and icons right, a dark green nav bar `#175e4c` (hover `#1d7a62`) with
white 13 px links and ▾ dropdowns, a 900 px white column, content in boxes with 1 px `#ccc`
borders and a bordered title bar ("Aktualności"), news items with a ✱ bullet before a 15 px
black title, a 170 px thumbnail, justified text and a bold "| Więcej". Mobile: a grey `#666`
"Menu" bar. `frontend/src/app.css` holds all of it as reusable classes. The point is
recognition: a physics student sees the site and knows where they are.

## Data model (backend/archive/models.py)
`Category` · `Person` (fictional in seeds; `is_listed` hides from the index) · `Tag` ·
`Post` (`format` text|latex, `body`, fuzzy date = `year` + `year_precision` + `date_note`,
`source_note`/`source_url`, `status` pending|published|rejected|hidden, `featured`, `views`,
`catalog_no` = FUW-0001) · `Attachment` (file, `original_name`, `kind`) · `Reaction`
(one per user per post) · `Comment` (threaded, `format`, tombstoned) · `CommentAttachment` ·
`Report` (anonymous allowed — the person a post is about may have no account).

**Files are referenced by original name.** A post and its files arrive in ONE multipart
request; the body says `![](zdjecie.jpg)` / `\includegraphics{zdjecie.jpg}` and the reader
maps the name to the stored URL (`render/media.ts`). No pre-upload endpoint, no orphaned
files, and the editor previews unsaved files with object URLs through the same mapping.

**Uploads are judged by bytes** (`archive/validators.py`): Pillow must decode an image
(after a pixel-count check from the header, against decompression bombs), a PDF must start
with `%PDF`, audio/video must carry their container signature; unknown extensions are
refused; JPEG/PNG are re-saved without EXIF (GPS). GIF/WebP keep their bytes — a re-encode
would kill animation, which is half of what a meme archive holds. No ClamAV here: OVH
shared hosting has none; stated rather than faked.

## Rendering
- Text = Markdown (marked) → DOMPurify → KaTeX auto-render for `$…$`. External images are
  refused (a hot-linked picture is a tracking pixel); only attachment names resolve.
- LaTeX = LaTeX.js in the browser (sections, lists, text macros, KaTeX math). There is no
  TeX engine anywhere in this stack, so this *is* the compiler: the editor's "Rekompiluj"
  and the post page run the same function. `\includegraphics` is handled by us (a marker
  word swapped for `<img>` after parsing, `width=0.5\textwidth` → 50 %). Unsupported
  packages are dropped rather than fatal; a real error is shown with its line, and the raw
  source stays readable. Both libraries are imported lazily — a page without content pays
  nothing.
- Comments use the same two renderers and take up to 3 images.

## Moderation & trust
Everything from a non-staff account waits for a moderator; staff posts publish at once.
A rejected post can be edited by its author and goes back to the queue. Reports (privacy /
wrong / offensive / copyright / other) join the same queue; hiding a post resolves them.
Removal requests from the people concerned are a first-class path, not an e-mail address.
Throttles: registration 10/h, login 20/min, post creation 30/h, reports 20/h, per IP, in a
file cache shared between processes.

## The trusted tier (backend/accounts/trust.py, backend/archive/moderation.py)
Three tiers: user, **trusted** (a confirmed e-mail at an FUW/UW/PAN domain — the curated
`TrustedDomain` table, subdomains per row, `uw.edu.pl` without), staff. Trusted users get the
moderation *tools* without the moderation *queue*: their own posts publish at once; they can
hide any post or comment in one click (it leaves the public page, lands on the board where
every trusted user can read and restore it, and its reports are resolved); and they can use the
nuclear option for illegal or disgustingly offensive content — after which only staff can read
or restore it, and the board shows the others just a stub (catalog number, who, when, why).
Every transition writes a `ModerationAction`. A restore returns a post to the status it had
(a never-approved one goes back to pending, never straight to published). The rules live in
one module and every endpoint asks it; the serializers blank what a caller may not see rather
than trusting views to filter.

## The chat (backend/board/)
An old-school shoutbox: anyone may write, guests under a nick (never an existing username),
2048 characters (2^11), links yes, images no, LaTeX yes (the same two renderers with images
switched off), ≤ 5 links, a honeypot, per-IP throttles, an RSS feed. The frontend shows the
first 100 characters of each message and folds the rest under a spoiler; the list pages by id
(`before`/`since`) because the stream grows at the top.

## The time machine (frontend/src/lib/components/timemachine/)
`eraFor(date)` is one pure function with these boundaries:
- ≥ 2026-09-10 (launch): our archive as of that day (`?before=`), rendered by the layout
  version in force then (`versions.ts` — the registry future redesigns append to, keeping
  the old component, which is what makes an old date render an old look).
- 1998-01-20 ≤ d < launch: fuw.edu.pl from the Internet Archive in an iframe
  (`/web/<date>if_/` redirects to the nearest capture; `/api/wayback/` resolves the exact
  timestamp for the caption, cached a day).
- 1816 ≤ d < 1998: a printed Polish paper (UW founded 1816). 1795 ≤ d < 1816: German
  (Prussian Warsaw). 1400 ≤ d < 1795: Latin, Copernicus's handwriting. Before: cave
  paintings, then dinosaurs, then — before the Big Bang — nothing, since "before" is not a
  thing there.
- The Big Bang animation plays on every journey to before fuw.lol existed.

## Deployment
Hetzner Cloud (CX23) with Coolify, behind Cloudflare's proxy — see `deploy/HETZNER.md`. Three
containers from `docker-compose.yml`: Postgres, Django+gunicorn, nginx (static build, `/api`
proxied, `/media` from a shared volume). All secrets and hosts come from `FUWLOL_*` variables;
`FUWLOL_TRUST_PROXY` makes per-IP throttles see the real visitor behind the proxy.

## Left open
- No e-mail (password reset, notifications). No real-time anything.
- No syntax highlighting in the LaTeX editor (a textarea with a line gutter, by choice).
- LaTeX.js covers a subset: no TikZ, no custom packages; the error panel says so.
- No user profiles, no per-user pages beyond "Moje wpisy".
- The German/Latin eras keep post titles in Polish — content is not translated.
- Only the home page has a time machine; other pages are the ground (`versions.ts`) for it.
