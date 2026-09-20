# archive — the post and everything filed around it

Models (`models.py`): `Category` · `Person` · `Tag` · `Subject` · `Post` · `Attachment` ·
`Reaction` · `Comment` · `CommentAttachment` · `Report` · `ModerationAction` · `PostRevision` ·
`EditSuggestion`. Rule modules, one concern each: `people.py`, `subjects.py`, `moderation.py`,
`suggestions.py`, `search.py`, `latexguard.py`, `uploads.py`, `validators.py`, `wayback.py`.
Eight test files, 136 tests (`test.md`). The reasoning for all of it is in `DESIGN.md`.

## Post

- `format` `text|latex`; `status` `pending|published|rejected|hidden|nuked|quarantined|purged` —
  **one field**, and `Post.objects` hides the last two (`backend/CLAUDE.md`). `moderation.PUBLIC_STATUSES
  = ('published','pending','rejected')` is what an author's own paths treat as ordinary. Public
  lists, search, random, timeline and stats count `published` only.
- A fuzzy date is `year` + `year_precision` (`exact|approx|decade|unknown`) + `date_note`;
  `catalog_no` is `FUW-0001`; `featured` is staff's (`set_featured`, actions `feature`/`unfeature`).
- `rights_confirmed` is **required** and is the uploader's own declaration, never consent from the
  people depicted (`LEGAL.md` §3). `submitter_ip` / user-agent are recorded for the art. 18 DSA
  report and blanked by `manage.py forget_submitter_ips` after `FUWLOL_SUBMITTER_IP_RETENTION_DAYS`.
- Everything from a non-staff account lands in `pending`; a trusted author's post publishes at once;
  a rejected post can be edited by its author and goes back to the queue. `Report` (anonymous
  allowed — the person a post is about may have no account; `good_faith` + an e-mail make it an
  art. 16 DSA notice) joins the same queue and is resolved by hiding the post.
- Throttles on this app's actions: `post_create` 30/h, `comment_create` 60/h, `suggest` 20/h,
  `report` 20/h, `escalate` 10/day, `presign` 60/h — each through `FixedScopeThrottle`.

## Files — one request, referenced by name, judged by bytes

A post and its files arrive in **one** multipart request (or as `uploads: [{key, filename, sha256}]`
claiming objects already PUT to R2 — the two share the six-file limit; a comment takes three, a literal
`3` in `views.py` rather than a setting). The body says
`![](zdjecie.jpg)` / `\includegraphics{zdjecie.jpg}` and the reader maps the *original name* to the
stored URL; there is no pre-upload endpoint and no orphan. `validators.py` decides the kind from the
bytes (`MAX_PIXELS` 40 M read from the header before decoding; `%PDF`; container signatures; unknown
extensions refused); `strip_image_metadata` re-saves JPEG/PNG/WebP without EXIF and GIF untouched.
`uploads.verify_stored` pulls an R2 object back and runs the same code, recording the hash of the
bytes actually kept. `sweep_uploads` removes objects nobody claimed within a day.

## People — a rule, not a collation (`people.py`)

- **Filing**: `split_degree` peels the title („dr Kwant Niepewny" → `degree='dr'`), `derive_surname`
  takes the last word (editable — „Pani z portierni" files under P by hand), `sort_key_for` folds so
  Łoś sits next to Lis whatever the database collates, `letter_for` keeps the diacritic because the
  A…Ż strip does. Migration 0007 filed every existing row with these same functions.
- **Nicknames are alias tags**: `Person.aliases` (M2M to ordinary `Tag`, `MAX_ALIASES` 12). A post
  tagged „Hamiltonianka" *is* prof. Hamiltonian's post — `person_posts_q` is the **one** definition
  of whose post is whose (named or tagged); `annotate_people` counts a post once across both joins.
  One nickname belongs to one person (`Conflict` → 409); attaching is a trusted power (`add_alias`,
  `remove_alias`); a tag left with no owner and no posts goes with the alias.
- **Naming a person into existence** (`resolve_people`, from the editor's picker): a typed name that
  already exists is **reused** on `name_key` (the folded bare name, filled at save and back-filled by
  0008); visibility is **derived** by `visible_people_q` — a published post, or seeded / staff-made,
  or proposed by you — so a rejected submission never leaves a stranger a readable page; an
  opted-out match is **refused, never reused** (one sentence, the same as for an unknown slug —
  `NO_SUCH_PERSON`); the moderator sees `is_new` on the queue card. Caps: `MAX_NEW_PEOPLE_PER_POST`
  5, names 2–120 characters, no „@", no URLs. `sweep_people` deletes proposals with no post of any
  status after 30 days.
- `Person.image_consent` is written only by the `consent` app or staff — never here, never by a
  submitter. `is_listed` is what `no_mention` turns off.

## Subjects (`subjects.py`)

Its own model, not a flagged tag (a free tag is forty spellings of itself) and not a `Person` (no
consent, no opt-out, no queue) — so **anybody with an account may add one by naming it**.
De-duplication is `get_or_create` on `subject_slug`, which folds through `search.normalize_text`
first because Django's `slugify` drops „ł" („Fizyka ciała stałego" would file as `fizyka-ciaa-staego`)
— and deliberately nothing fuzzier: „Mechanika klasyczna" and „Mechanika klasyczna R" are two courses.
Real duplicates are a moderator's `SubjectAdmin.merge`. The list offers every seeded row always and a
named row once it has a published post; `retrieve` never narrows. `MAX_SUBJECTS_PER_POST` 6; named
rows get `NAMED_SUBJECT_ORDER` 900, after the 35 seeded by 0008 in the order a student meets them.

## Moderation and the trusted tier (`moderation.py`)

`hide_post` / `nuke_post` / `restore_post` and the comment triplet are the only writers of `hidden`
and `nuked`; every call goes through `record` → `ModerationAction`. A restore returns to the
**previous** status (a never-approved post goes back to `pending`, never straight to `published`).
A nuke needs a reason (`NUKE_NEEDS_REASON`); un-nuking is staff only (`ONLY_STAFF_UNNUKE`); every
action first calls `require_not_escalated`. `can_see_post` / `can_see_comment` / `visible_posts_q`
are what the views and `share/previews.py` ask; the serializers blank `review_note`, reporter
`note` and `contact_email` for callers who may not see them. `MODERATION-API.md` has the payloads.

## Suggestions and revisions (`suggestions.py`)

A reader proposes changes to `SUGGESTABLE_FIELDS` (title, summary, body, format, the date fields,
the source fields); `EditSuggestion.status` is `pending|accepted|rejected|withdrawn`; `can_decide`
says who may accept (author or staff); accepting writes a `PostRevision` with `source =
suggestion`, as an author's own edit writes `author` and a moderator's `moderator`. `snapshot` /
`current_values` are the diff basis; `visible_suggestions_for` and `can_see_revisions` scope the
read side.

## Search (`search.py`)

Two derived columns on `Post`, filled at save by `index_fields` and back-filled by 0003:
`search_text` (prose without diacritics or case) and `search_math` (formulae after
`canonicalize_math` — `x^2` ≡ `x^{2}`, `\dfrac` ≡ `\frac` via `SYNONYMS`, spacing normalised). A
query goes through `query_parts` with the same folding, so `calkowanie` finds „Całkowanie". It is
`LIKE` today; the Postgres half is a known gap. `normalize_text` is mirrored by `editor/chips.ts`
`fold` — change both.

## The macro guard (`latexguard.py`)

`check_source(src, max_chars=MAX_POST_CHARS)` refuses the `\def` family and other expansion
primitives, self-referential `\newcommand` / `\newenvironment`, more than 60 000 characters (10 000
for a comment), more than 400 `\begin{`, brace nesting deeper than 40. It runs on every write
path here and in `board`; its twin `frontend/src/lib/render/guard.ts` runs on read. **This copy is
the one that counts**; the two must stay identical, and both files say so. `test_content_guards.py`
pins each cap, including the depth cap that touches no forbidden primitive.

## Wayback (`wayback.py`)

`/api/wayback/` resolves the Internet Archive capture of `www.fuw.edu.pl` nearest a date (from
`EARLIEST` 1998-01-20) for the time machine's caption, cached a day.

## Commands

`seed_demo [--reset]` (demo accounts and nine posts; passwords `fuwlol123` only under DEBUG),
`forget_submitter_ips`, `sweep_people`, `sweep_uploads [--hours]`.

## Verify

`../.venv/bin/python manage.py test archive` (136). Browser: `npm run e2e` drives submit → queue →
publish → render; `e2e:research` pins the search canonicalisation, the rights declaration and the
`\def` refusal; `e2e:render-guard` the read-side guard. Two of the three bugs in the people picker
were found only in a browser.
