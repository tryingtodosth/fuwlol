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
`Category` · `Person` (fictional in seeds; `is_listed` hides from the index; filed like the faculty
directory — see "People" below) · `Tag` ·
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

## People (/ludzie) — the faculty directory, copied on purpose
`/ludzie` is `fuw.edu.pl/osoby-fuw.html` and `/ludzie/<slug>` is `osoby-fuw.html?show=…`, measured from
the live site in September 2026: the breadcrumb, the orange-barred "Osoby", the alphabet strip
(A…Ż, Ż its own letter), the search form, `table.employers` with a title column, a surname-filed name
column and rows alternating odd/even straight through the letter rows; the profile's `single_record`
table with the 130 px photo, the bold name with its title, the function in italics, the unit line and
label/value rows. Where the faculty prints a room, a phone and an e-mail icon, we print **nicknames**
and the number of posts; where it links USOSweb, we link the person's posts chronologically. The
placeholders are the faculty's own silhouettes (`static/img/anonymous{ma,fe}bw.png`, picked by
`Person.sex`), and a grey "Miejsce na foto" box when neither applies — the same three outcomes the
faculty's page has.

**Filing is a rule, not a collation** (`archive/people.py`). `split_degree` peels the title off a name
("dr Kwant Niepewny" → `degree='dr'`), `derive_surname` takes the last word (editable — "Pani z
portierni" files under P by hand), `sort_key_for` folds it so Łoś files next to Lis whatever SQLite
thinks, and `letter` keeps the diacritic because the strip does. Migration 0007 filed every existing
row the same way.

**Nicknames are alternative tags.** `Person.aliases` is a many-to-many to ordinary `Tag` rows: a post
tagged "Hamiltonianka" IS prof. Hamiltonian's post — on her page, in her count, in `?person=`. This is
why the old bug ("no such person in the checkbox? put her in the tags" — and nothing ever promoted the
tag) cannot recur: attaching the tag as an alias retroactively files every post that ever carried it,
with no re-filing and no second copy. `person_posts_q` is the one definition of "whose post is whose";
`annotate_people` counts distinct posts across both joins (a post both named and tagged counts once)
and derives the years the archive covers. One nickname belongs to one person (409 otherwise); the
trusted tier attaches and detaches them (`POST/DELETE /people/<slug>/aliases/…`), and a tag left with
no owner and no posts is deleted with the alias.

**Consent is the person's, not the uploader's.** `Person.image_consent` (`unknown | granted | refused |
opted_out`) is what the person themself said about their image (art. 81 pr. aut.), written by the
`consent` app's claims flow or by staff — never by a submitter, whose `rights_confirmed` remains their
own declaration. `granted` draws the ✓ badge (`ConsentBadge.svelte`, explained at `/ludzie/zgoda`) and
opens the `portraits` gallery; `refused` and `opted_out` tighten what may be published. Both apps hang
off this one field so that revoking consent is a single write that every reader sees at once.

## Przedmioty (/przedmioty) — the third filing axis
A post is filed by category, by the people it is about, by free tags — and by the university course
it happened on (`archive.Subject`: `slug`, `name`, `short`, `order`). Seeded in migration 0008 from the
Faculty's own first- and second-cycle programmes (m.fuw.edu.pl, „Materiały dydaktyczne” for I/II/III
rok, read September 2026): 35 rows ordered by the year they are usually sat in rather than
alphabetically, because that is the order a physics student has them in their head.

Its own model rather than a flagged `Tag`, because a free tag „mechanika” is forty spellings of
itself. Not a `Person` either: no consent question, no opt-out, no directory that has to hide a
proposal — which is why **anybody with an account may add one by naming it**, with no queue.
De-duplication is `get_or_create` on the slug and deliberately nothing cleverer: fuzzy matching would
collapse „Mechanika klasyczna” and „Mechanika klasyczna R”, which the Faculty runs as two different
courses. Real duplicates are a moderator's merge in the admin (`SubjectAdmin.merge`). Slugs fold
through `search.normalize_text` first (`subjects.subject_slug`), because Django's `slugify` drops „ł”
— „Fizyka ciała stałego” would otherwise file itself as `fizyka-ciaa-staego`. `/api/subjects/` lists a
seeded row always (it is an *offer*) and a named row once it has a published post; `retrieve` does
not narrow, so a shared link always opens.

## Naming a person into existence
The editor used to show checkboxes for the people who already existed and tell you „Brak osoby?
Wpisz ją w tagach” — and nothing ever promoted such a tag to a `Person`, so /ludzie stood at the seed
data from launch day. Now all three axes are one typeahead (`editor/TagPicker.svelte`, a real ARIA
combobox: `aria-expanded`/`aria-controls`/`aria-activedescendant`, arrows, Enter, Escape, Backspace
takes the last chip back), and typing a name that is not there offers to add it — a two-line
mini-form for the title and the role, then a chip marked „nowa”.

Four rules make that safe enough for an ordinary account to add a row to a public index of named
human beings, all in `archive/people.py`:
- **A typed name that already exists is REUSED**, matched on `Person.name_key` (the folded bare
  name, filled at save). The third person to write about Anna Nowak lands on the same page as the
  first, not on a twin that splits her posts in half.
- **Visibility is derived, never toggled** (`visible_people`): a published post, or seeded/staff-made,
  or proposed by you. A proposed person appears the instant the post naming them is published, is
  visible meanwhile only to their proposer, and a rejected submission never leaves a stranger a
  readable page about somebody.
- **The refusals are not an oracle.** Unknown slug, unlisted person, and a name matching somebody who
  opted out all get one sentence. An opted-out match is refused rather than reused: reusing would let
  anybody undo an art. 81 opt-out by typing a name.
- **The moderator sees what they are publishing.** `is_new` on the queue card, drawn as NOWA chips
  with „usuń z wpisu” and „scal z…”, both an ordinary staff PATCH of the post's `people`.
  `manage.py sweep_people` deletes proposals with no post of any status after 30 days.

Caps: five new people per post, six subjects, 2–120 characters, no „@”, no URLs. Two of the three
bugs in this feature were found only by driving it in a browser: the listbox reopening over the next
field after a chip was taken (a `focus()` that fired `onfocus`), and Enter creating the very duplicate
the picker exists to prevent when pressed before the previous query's results had settled.

## Consent — the person's own say (backend/consent/)
`Post.rights_confirmed` is the uploader's declaration. The person a post is about — usually with no
account here — gets their own channel: **„Jesteś tą osobą?”** on their profile. They give an e-mail
and one of three wishes, worded for the person: *zdjęcia ze mną mogą tu być* (`images_ok`), *wzmianki
tak, zdjęć nie* (`no_images`), *nie chcę być w archiwum* (`no_mention`). A link goes to the mailbox
(never the claimant's note — that is how relay spam is born); the click proves the mailbox
(`verified`); staff — not the trusted tier, because confirming an identity is a different power from
"hide fast" — see the claim in `/moderacja/zgody` with plausibility signals (institutional domain,
surname in the local part, an existing account, earlier claims) and approve or reject. `PersonClaim`
is one row per claim with one `status` (`sent | verified | approved | rejected | superseded |
withdrawn`), the consent text version, and the requester's IP for the retention window — the
approved row is the archive's *evidence of consent* (art. 7 ust. 1 RODO) and is never deleted; a
change writes a new row and marks the old one `superseded`.

**The asymmetry is the design.** A fraudulent `images_ok` is real harm; a fraudulent `no_images` only
hides content until staff reject it. So the two tightening wishes apply **at verification already,
when the mailbox is at a `TrustedDomain`** — everything else waits for staff — and `ConsentHide` rows
record exactly which posts a claim hid and from which status, so a rejection (or a later loosening)
reverts precisely those and nothing a moderator hid for other reasons. `no_images` hides the person's
posts with an image attachment (through `person_posts_q`, aliases included, pending ones too — a
pending post is public tomorrow); `no_mention` hides all of them and delists the person. Hidden, not
deleted: a moderator still has to decide what a lawful version of each post looks like. The audit
line says „na wniosek osoby, której wpis dotyczy” and never the address. Withdrawal is as easy as
consent (art. 7 ust. 3 RODO): a settings link to the same mailbox changes the wish immediately, no
second review — the mailbox is the identity. `/ludzie/zgoda` explains all of this to the person; the
badge links there, because a badge nobody can look up is a rumour.

## Portraits — the profile photo is elected (backend/portraits/)
Once a person's `image_consent` is `granted`, logged-in users may upload photos of them (bytes judged
by `archive/validators.py`, EXIF stripped, `sha256` of the stored bytes, the uploader's own rights
declaration required) and vote: **one vote per user per person**, movable, toggleable; the published
portrait with the most votes — tie → the older — is the profile photo, and the `/ludzie/<slug>` page
swaps the faculty silhouette for it. Trusted uploads publish at once, everybody else's wait in
`/moderacja/portrety`; every transition writes a `PortraitAction`. `visible_q` requires the person's
consent to *still* be `granted` for everybody, staff included — withdrawing consent empties the
gallery at the next request without deleting anything, which is what makes the consent switch a
single write. Not built: an escalation path for a portrait, an R2 upload path, a per-photo report
button (today: the person's own consent entry is the door).

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

## Link previews (backend/share/)
Every URL is served the same `200.html` and no scraper — Messenger, WhatsApp, Telegram, Slack,
Google — runs JavaScript, so a shared `/wpis/…` used to preview as the bare site title. nginx now
routes the scrapers (by User-Agent, `frontend/nginx.conf`) to Django, which renders `<title>`,
`og:*` and `twitter:*` for the route from `share/previews.preview_for`. It asks the existing rules
(`can_see_post(None, …)`, `visible_people(None)`, `person_posts_q`, `portraits.rules.current_portrait`)
rather than restating them: a hidden, nuked or escalated post gets the generic site card and a 404,
byte-identical to a slug that never existed — a leak here would outlive the takedown, because a
preview is cached on somebody else's servers. Images are absolute (R2 as-is, `/media` prefixed with
`FUWLOL_SITE_URL`); a person without a portrait gets a 1200×630 card with the faculty silhouette,
because Facebook drops any image under 200×200 and the bug report was Messenger. Humans who reach
`/share/…` are redirected to the real page. The splice-into-the-real-shell mode (`FUWLOL_SPA_INDEX`)
is implemented and tested for the day the SPA and Django share a filesystem; today they are two
containers. `/sitemap.xml` comes from the same app. After a deploy, already-shared links stay as
Facebook cached them until re-scraped (developers.facebook.com/tools/debug) — `deploy/OVH.md`.

## Left open
- No e-mail (password reset, notifications — a head-admin learns about an escalation only by
  logging in; that mail is the first thing to build, the SMTP for verification already exists).
  No real-time anything.
- No syntax highlighting in the LaTeX editor (a textarea with a line gutter, by choice).
- LaTeX.js covers a subset: no TikZ, no custom packages; the error panel says so.
- No user profiles, no per-user pages beyond "Moje wpisy".
- The German/Latin eras keep post titles in Polish — content is not translated.
- Only the home page has a time machine; other pages are the ground (`versions.ts`) for it.
