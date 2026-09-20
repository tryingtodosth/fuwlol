# fuw.lol — design notes

The *why* behind each subsystem: what was measured, what was decided, what broke on the way and how
it was found. This is the reasoning. The rules an editor has to hold while changing the code are
distilled into `CLAUDE.md` at the root and into the scoped `CLAUDE.md` of each half and each app,
which point back here for the argument.

Until 2026-09-19 this file held everything. What moved out, and where:

| Now in | What |
|---|---|
| `PRODUCT.md` | what the archive is and is not, the tiers, the feature set, product decisions, what is left open |
| `LEGAL.md` | the two takedowns and why they end differently, consent, RODO retention, DSA notice-and-action, the Dyżurnet step |
| `SECURITY.md` | the standing security posture, its accepted risks, and how to test a "known vulnerability" claim |
| `deploy/OVH.md` | how the site actually runs (this file's old "Deployment" section described a Hetzner + Coolify plan that never went live) |
| `test.md` | every test suite and browser script, what it covers, how to run it |

When this file and the code disagree, the code is the present and this file is what was true when
it was written. When it and a `CLAUDE.md` disagree about a *rule*, the `CLAUDE.md` wins — it is
closer to the code.

## Look: a copy of fuw.edu.pl, on purpose
Measured twice. In early September 2026 from www.fuw.edu.pl: Tahoma 13 px `#444`, a ~70 px
light-grey banner with the logo left and icons right, a dark green nav bar `#175e4c` (hover
`#1d7a62`), a 900 px white column, boxes with 1 px `#ccc` borders and a bordered title bar, news
items with a typed ✱ before a 15 px black title, a 170 px thumbnail, justified text and a bold
"| Więcej", a grey `#666` "Menu" bar on a phone. That is version 1, which `VersionV1.svelte`
keeps for the time machine. On 20.09.2026 from **m.fuw.edu.pl** — where www.fuw.edu.pl now sends
every visitor, desktop browsers included — with a headless browser reading computed styles, and
this is what the site copies since version 2:

- `body` 13px/1.5 Tahoma, Helvetica, Verdana, `#444`; headings plain — normal weight, `#444`,
  16 / 15 / 14 px, `margin: 6px 0 12px`; paragraphs 12 px apart; links `#a84204`, underlined on
  hover only.
- **Banner** (`.responsive_baner`): amber `rgb(253,186,69)`, 1000 px wide and centred, 71 px tall,
  a flex row — the faculty logo (100×61) flush left, the UW seal beside it, at the right a flag, an
  envelope and a magnifier as plain dark icons. On a phone the grey `#666` hamburger square (a 29 px
  icon with `padding: 4px 4px 3px`) sits at the banner's right end; there is no separate menu bar.
- **Navigation** (`.nav`): `#175e4c`, also 1000 px and centred — the two bars overhang the 900 px
  column by 50 px a side — 31 px tall; links white 13 px, `padding: 5px 15px` (6px 15px on a
  phone), a 1 px `#104336` line along the top; a parent item carries a 9×5 grey arrow at its right
  edge; the submenu is 20 em wide, its items `#1d7a62` with a 1 px `#175e4c` line between, no
  border, no shadow.
- **Column**: `#main` 900 px; `.mod_article` inset `10px 36px 10px 32px` (10 px all round under
  850 px), so content is 832 px wide.
- **Boxes** (`.mod_newslist`): 1 px `#bbb` border, `margin: 10px 0`, `padding: 0 10px 6px 6px`; the
  title bar (`h1`) reaches the border with negative margins (`0 -10px 8px -6px`), `padding: 8px 0
  10px 11px`, **16 px bold orange `#ee8d30`**, a 1 px `#bbb` underline — 35 px tall.
- **News items** (`.layout_short`): nothing between them (`margin: 0 6px 3px 0`); the headline
  `h2` 15 px normal weight with `padding-left: 16px` and the faculty's own 12×12 orange asterisk
  (`/img/asterisk-small.png`, at `0 3px`), the link in rust; paragraphs 13px/1.5 justified,
  `padding: 0 8px 0 16px`, `margin: 0 0 4px`; a picture is `.image_container.float_left`, 170 px
  wide at its natural height, `padding: 5px 10px 0 15px`, the text wrapping round it; "| Więcej"
  is typed text with a plain rust link, not bold. An item without a picture has no placeholder.
- **The front page** is two columns (`.c66l` / `.c33r`, a 10 px gutter): the news box left; right,
  a stack of small boxes with the same orange titles — a welcome paragraph, rows with a 65 px
  picture floated beside one line and `<hr>` between them, link lists. Stacked on a phone.
- **Every subpage** opens with the breadcrumb and gives its headline the same 10 px orange left bar —
  ours too: `Breadcrumb.svelte` on every route but the front page, `h1.ce_headline` and any `h1` that
  is a page's own top-level heading (`.page > h1`).
- **An article** (`.mod_newsreader`): a breadcrumb (`.mod_breadcrumb`, 12 px, links `#5e6a94`,
  "Wydział Fizyki UW > Wydział > Aktualności", the active item `#444`); `h1` 16 px normal weight
  behind a **10 px `#ff8c00` left bar** (`padding-left: 5px`, `margin: 12px 0`); `p.info` — the
  date — 14 px `#888`; `.ce_text` justified, `margin-top: 16px`, the picture
  `.image_container.float_left` at 315 px with `padding: 5px 10px 5px 0` and an 11 px italic
  `#555` caption; `p.back a` "Wróć" (`history.go(-1)`) 18 px below. No box around any of it.
- **Footer** (`#mfooter`): one bare line at the bottom left, `padding: 0 10px`, a rust link.

`frontend/src/app.css` holds all of it as reusable classes, `Header.svelte` and `Footer.svelte`
the bars and the line, `PostCard.svelte` the item, `routes/wpis/[slug]` the article. The point is
recognition: a physics student sees the site and knows where they are — so a measurement that turns
out wrong (the grey banner, the black headlines, the bold "| Więcej", the hairline between items)
is corrected in the live look and kept, pinned, in the version component the time machine mounts
for the dates it was true.

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
would kill animation, which is half of what a meme archive holds. No ClamAV anywhere in this
stack; stated rather than faked (`SECURITY.md`).

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

**Why a nuke keeps the file and a purge destroys it** — the civil and the criminal takedown end in
opposite ways because opposite duties apply (art. 81 pr. aut. versus art. 202 § 4b k.k.), and the
purge's ordering (audit rows commit, then bytes die, then the row is marked) follows from that.
The argument is in `LEGAL.md` §6; the engineering it forces — `Post.status` gaining `quarantined`
and `purged`, the default manager excluding both, `Post.all_objects` as the escape hatch, the
append-only `EvidenceAuditLog`, the 409 on a partial shred — is held in `backend/escalation/CLAUDE.md`.

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

OVHcloud VPS-1 in Warsaw, plain Docker Compose behind Caddy, behind Cloudflare's proxy, with
attachment bytes in Cloudflare R2 and verification mail through Brevo — `deploy/OVH.md` is the
runbook and the post-deploy checklist. Four containers from `docker-compose.prod.yml`: Postgres,
Django + gunicorn, nginx (the static build, `/api` and `/share` proxied, `/media` from a shared
volume), Caddy for TLS with a Cloudflare origin certificate. **Push to `main` is the deploy:**
`.github/workflows/deploy.yml` runs the Django suite and `svelte-check`, builds both images, pushes
them to GHCR and only then pulls them on the box — nothing is ever built on the 2-vCore VPS, and a
rollback is the same `docker compose up` with an older image tag. All secrets and hosts come from
`FUWLOL_*` variables; `FUWLOL_TRUST_PROXY` with `FUWLOL_PROXY_HOPS=3` (Cloudflare → Caddy → nginx)
makes every per-IP throttle see the visitor rather than a proxy. `deploy/HETZNER.md` is the
superseded Coolify plan, kept because `docker-compose.yml` still describes that build-it-here setup
and remains valid for a plain `docker compose up -d --build`.

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

