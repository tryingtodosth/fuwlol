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

## Escalation to NASK (backend/escalation/)
The one state in which "trusted" and even "staff" mean nothing. A trusted user or a moderator
presses 🚨 on a post, a comment or a chat message and gives a reason (required; the dialog says
what is about to happen). From that instant the target is invisible to everybody except a
head-admin (`is_superuser` — Django's own flag, reused rather than inventing a fourth tier):
it leaves every list, the RSS feed, the moderation board and the Django admin
(`escalation/adminmixin.py`), and hide/restore/nuke/moderate refuse with 403/404. The evidence is
frozen INSIDE the same transaction — manifest (content, author, e-mail, dates) plus copies of the
files, chmod 400, SHA-256 of the whole package in `evidence_ref` — because the author may delete
the account and a moderator may restore the message before anybody looks. The live files are
MOVED out of `/media` into the evidence volume (`quarantine.py`), so a kept URL answers 404; a
nuke does the same, and a decline or un-nuke moves them back only when nothing else holds them.
`/eskalacje` shows the head-admin the frozen package and two decisions: approve (the package is
complete; the human forwards it through Dyżurnet.pl — the app never contacts an institution) or
decline (back to ordinary moderation). `is_escalated` fails CLOSED. Every step is a row in the
database and a line in the `security` log. Nothing distinguishes "already escalated" from "does
not exist" to anybody below head-admin.

## The two takedowns, and why they end differently
Taking something down is not one thing here, because the law it answers to is not one law.

**Civil — copyright, defamation, a photo of somebody who never agreed** (art. 81 pr. aut.,
art. 212 k.k., RODO). This is `nuked`: the post stops being readable by anybody below staff, and
its files are HELD — moved off the public path, kept. A claim of this kind can be litigated years
later and the file is the evidence; destroying it would destroy our own defence. This is what the
task brief calls `SOFT_DELETED`, and it deliberately does not get a second status name: two names
for one state is how an illegal state becomes representable.

**Criminal — suspected CSAM or comparable material** (art. 202 k.k., art. 18 DSA). This ends the
opposite way, because the opposite duty applies: art. 202 § 4b k.k. criminalises *possessing* the
material, and Polish law gives an amateur platform no chain-of-custody exemption for keeping a
copy "for the investigation". So the material is reported and then destroyed, and the two steps
happen in that order and only that order — once the bytes are gone this service cannot produce
them again for an investigator who asks.

    escalate ──► quarantined ──► approved ──► [head-admin forwards to Dyżurnet.pl themselves]
                     │                              │
                     │ decline                      ▼ confirmed_dispatch=true
                     ▼                         audit rows written  ──►  bytes destroyed  ──►  purged
              back where it was

`Post.status` gains `quarantined` and `purged`, written by exactly one module
(`escalation/services.py`) as a projection of the `Escalation` row that owns the workflow — and
`PostManager`, the DEFAULT manager, excludes both. That is the layer which catches the call site
nobody thought about: the public API, the board, the admin, the search index, `manage.py shell`.
`Post.all_objects` is the unfiltered escape hatch, used by the escalation machinery, by the API's
own queryset (so a head-admin can still reach what they are responsible for), by `_unique_slug`,
and by `Meta.base_manager_name` so related access keeps working. Comments and board messages have
no status to project onto and stay governed by the `Escalation` row alone — the criminal path is
not Post-only, because an attachment on a comment is the same offence and the same duty.

**Access is head-admin only, and that is a safety rule before it is a privacy one.** A trusted
student volunteering to moderate a meme archive must not acquire art. 202 § 4a/b exposure by
volunteering. `is_head_admin` now accepts either `is_superuser` or a grantable
`escalation.can_manage_critical_quarantine`, so "as few people as possible" can be two people
without the second one getting the keys to everything else. Media previews for a head-admin are R2
presigned GETs capped at **five minutes** (`config/r2.PREVIEW_TTL_SECONDS`) — they are bearer
capabilities, so they are minutes, not hours.

**The purge itself** (`escalation/shred.py`) destroys every copy: the R2 object, the MEDIA_ROOT
file, the `EVIDENCE_ROOT/quarantine/` copy and the frozen evidence copy. Missing one would make
the purge a fiction, and the fiction is the dangerous part — an audit row saying the material was
destroyed while a copy sits on the VPS is exactly the state the statute punishes. A database
transaction cannot roll back a deleted R2 object, so the ordering is chosen instead of pretending
to be atomic: **audit rows commit, then bytes die, then the purge is marked**. A crash in the
middle leaves an incomplete purge — visible, retryable, and finished by running the action again
(the audit rows are not duplicated). The opposite order would leave destroyed bytes with no record
of what was destroyed, which nothing can repair. A failed shred answers **409** with the list of
copies that survived, never a silent success.

What outlives it is `EvidenceAuditLog`: one append-only row per destroyed file (`save` on an
existing row and `delete` both raise), holding the sha256, the uploader's IP and user-agent, the
timestamps, who reported it and the Dyżurnet reference. None of that is the material; all of it is
what an investigator actually asks for. `Post.submitter_ip` is recorded at upload for this one
purpose and blanked after `SUBMITTER_IP_RETENTION_DAYS` by `manage.py forget_submitter_ips` — a
raw address kept past its usefulness is a liability, not an asset. An escalation freezes it into
the manifest first, so a report assembled next month still carries it.

`escalation/nask.py` assembles the package a human sends: target URL, publication and capture
timestamps in UTC, uploader IP and user-agent, every sha256, the package hash — as JSON and as
Polish text to paste into Dyżurnet's form. Nothing here ever contacts an authority by itself.

## Uploads go straight to R2 (backend/config/r2.py, backend/archive/uploads.py)
A 25 MB file posted through Django occupies one gunicorn worker for the whole transfer; six of
them is every worker the VPS has. A single six-file multipart POST is also 150 MB, which
Cloudflare terminates at the edge (100 MB request cap, every plan) before Django sees it. So the
browser asks `POST /api/uploads/presign/` for one signed URL per file and PUTs each one straight
to the bucket.

The presigned PUT is signed over `ContentLength` and `ChecksumSHA256`, not just the key: anything
unsigned is something the uploader chooses freely, and signing those two makes the 25 MB cap
binding at R2 and lets R2 itself reject bytes that are not the bytes declared — which is why
`HeadObject` can later return a sha256 we did not compute and did not download 25 MB to learn.
Keys are random; the uploader's filename is kept only as `original_name`.

Two guarantees the multipart path gave are explicitly kept rather than quietly lost: the decision
about what a file is still made on the BYTES, and EXIF still comes off a photograph. `verify_stored`
pulls the object back at post-creation (R2 egress to the origin is free), runs the same
`archive/validators.py`, and for JPEG/PNG/WebP re-stores the stripped version and records the hash
of *those* bytes — recording the original's hash would put a checksum in a NASK report that does
not match the file the report is about.

**R2 unconfigured is a supported setup** and is what a bare clone and the whole test suite run
with: uploads keep going through Django to MEDIA_ROOT, and the presign endpoint answers 503 rather
than pretending. What is stated rather than solved: between the PUT and the post being created an
unvalidated object sits in the bucket under a random, unreferenced key; `manage.py sweep_uploads`
removes anything unclaimed after a day.

## Security posture (after the review of 16.09.2026)
Uploads are judged by bytes and renamed to UUIDs; JPEG/PNG/WebP lose EXIF. In the browser, both
renderers (Markdown and LaTeX.js) go through DOMPurify with an image allow-list enforced ON THE
DOM: an `<img>` survives only if its `src` is one of our attachment URLs (or a preview blob) —
the older regex over `![](url)` never saw reference-style images or raw tags, and a hot-linked
picture is a tracking pixel fired at every moderator. `class` is not allowed in user content.
nginx sends a CSP (img-src self, frame-src web.archive.org, frame-ancestors self), X-Frame-Options,
Referrer-Policy; `/media` is served with `sandbox` and PDFs as attachments. The client address is
taken from X-Forwarded-For counted from the RIGHT by `FUWLOL_PROXY_HOPS` (Traefik + nginx = 2) and
CF-Connecting-IP only with `FUWLOL_CLOUDFLARE=1` — the leftmost entry is the client's own and used
to drive every per-IP throttle. Per-action throttles on the post ViewSet were a silent no-op
(`ScopedRateThrottle` reads the scope off the VIEW); `FixedScopeThrottle` makes post_create 30/h,
comment_create 60/h and escalate 10/day real. Login is limited per username as well as per IP.
`seed_demo` never resets an existing password and, outside DEBUG, generates random ones; the
Docker image sets `FUWLOL_DEBUG=0` and settings refuse to start with the default SECRET_KEY.
Reporters' e-mails and notes are staff-only; a moderator's review note is the author's only.
Accepted, not forgotten: the token lives in localStorage (CSP is the second line, an httpOnly
cookie would be a different auth model); one trusted account can escalate — and thereby freeze —
any content (10/day, fully logged: the price of acting fast on CSAM); throttles count attempts,
not failures. Two entries on this list were closed on 19.09.2026: the Cloudflare cache is now
purged by URL on quarantine (`escalation/cdn.py`, and it logs rather than lies when unconfigured),
and quarantine no longer assumes FileSystemStorage — it moves an R2 object to the `held/` prefix
just as it moves a local file out of `/media`.

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
- No e-mail (password reset, notifications — a head-admin learns about an escalation only by
  logging in; that mail is the first thing to build, the SMTP for verification already exists).
  No real-time anything.
- No syntax highlighting in the LaTeX editor (a textarea with a line gutter, by choice).
- LaTeX.js covers a subset: no TikZ, no custom packages; the error panel says so.
- No user profiles, no per-user pages beyond "Moje wpisy".
- The German/Latin eras keep post titles in Polish — content is not translated.
- Only the home page has a time machine; other pages are the ground (`versions.ts`) for it.
