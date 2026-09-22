# fuw.lol — product notes

What the archive is for, who it serves, the product decisions that are decisions rather than
accidents, and what is deliberately not built. `DESIGN.md` holds the engineering reasoning behind
each subsystem; `README.md` (Polish) is the feature tour for the people who run and use the site.

## What it is

An internet archive of the *funny* side of the Faculty of Physics, University of Warsaw —
folklore, not a news site: things that are only ever passed around by word of mouth, a group chat,
or a scan somebody keeps. The value is that it is one place, browsable by category / person /
subject / year, moderated, and that a post can be *written* — a legendary exam problem needs LaTeX,
a meme needs a picture, a story needs a paragraph.

It is not a research project. Recovering the folklore of 1995–2010 from the Wayback Machine and
Usenet (`docs/gemini/history.txt`) is a separate undertaking whose results would enter the archive
as ordinary posts with a `source_url`; the data model already carries fuzzy dates
(`year_precision`) and a `source_note` for exactly that.

## Who

| Tier | Who | What it adds |
|---|---|---|
| public | anybody | read everything published; write in the chat under a nick; report |
| user | any account | post (into the moderation queue), comment, react, upload portraits, add a subject or propose a person |
| trusted | an account with a confirmed e-mail at an FUW / UW / PAN domain (`TrustedDomain`) | posts publish at once; hide / restore / nuke in one click; escalate to NASK; attach nicknames to people |
| staff | Django `is_staff` — the real administration | the moderation queues, consent decisions, portrait review, the Django admin |
| head-admin | `is_superuser`, or the grantable `escalation.can_manage_critical_quarantine` | the only tier that sees escalated content; decides and purges |

Staff is always trusted. The tiers are Django's own flags plus one confirmed-affiliation bit —
no fourth role model was invented (`DESIGN.md` "The trusted tier").

Demo accounts on a development server: `dziekan` (staff and head-admin), `doktorant` (trusted),
`student`, password `fuwlol123`; outside `FUWLOL_DEBUG=1` the seed draws random passwords and prints
them once.

## What it does

- **Posts** in two formats: *text* (Markdown, `$…$` maths, images) or *LaTeX* (an Overleaf-like
  editor: numbered source, a preview compiled in the browser, an error panel, a file list that
  inserts `\includegraphics`). Up to six files per post — images, PDF, audio, video, `.txt` /
  `.tex`, 25 MB each — judged by their bytes, photographs stripped of EXIF. A file's own name is its
  reference in the body.
- **Filing on four axes**: category; the **people** a post is about (`/ludzie`, a copy of the
  faculty directory, with nicknames as alternative tags); the **subject** it happened on
  (`/przedmioty`, the Faculty's own course list); free tags. Plus a timeline with fuzzy years
  (exact / about / decade), search that ignores diacritics and case and canonicalises maths
  (`x^2` finds `x^{2}`, `\frac` finds `\dfrac`), a random post, and `FUW-0001` catalogue numbers.
- **Community**: reactions (lol / klasyk / wow / cringe), threaded comments in either format with
  up to three images, and a shoutbox **chat** (`/czat`) anybody may write in, with an RSS feed.
- **Moderation**: a queue (`/moderacja`) for everything from ordinary accounts; reports, anonymous
  ones included, that become formal DSA notices when they carry an e-mail and a good-faith
  statement; a reason and an appeal path for every refusal; a **moderation board** (`/tablica`)
  where every trusted user sees what was hidden and can restore it; a nuclear option for illegal or
  disgustingly offensive content; and **escalation to NASK** (`/eskalacje`) for the one class of
  material where even staff must not look. `LEGAL.md` explains why those end differently.
- **The person's own say**: „Jesteś tą osobą?” on a profile lets the person depicted state, from
  their own mailbox, whether pictures of them may be here (`/ludzie/zgoda`, queue at
  `/moderacja/zgody`). With consent granted, logged-in users may add **portraits** and the profile
  photo is elected by vote (`/moderacja/portrety`).
- **The time machine** on the home page: a date in fuw.lol's life shows the archive as of that day
  in the layout of that day; 1998–2026 shows fuw.edu.pl from the Internet Archive after a Big Bang
  animation; earlier dates get a Polish newspaper, a German one, Copernicus's Latin, cave paintings,
  dinosaurs, and — before the Big Bang — nothing.
- **Link previews** for scrapers (Messenger, WhatsApp, Telegram, Slack, Google) and a sitemap, so a
  shared post shows its title and picture rather than the bare site name.

## Product decisions

- **The look is a copy of fuw.edu.pl, on purpose** — recognition is the joke and the point. A
  physics student sees the site and knows where they are. `DESIGN.md` has the measurements.
- **Chronological, no algorithm.** Newest first, a random button, a timeline. The competitor study
  (`docs/gemini/konkurencja.txt`) documents what feeds and karma do to niche communities; the
  archive has neither.
- **No karma.** `Profile.reputation` moves when a trusted user's chat report is upheld or overturned,
  and that is a *record*, not a lever — nothing is unlocked by it, and it should stay that way.
- **Trust is an institutional e-mail, not a reputation.** A confirmed FUW / UW / PAN address gives the
  moderation tools; the moderation queue is what it removes. The domain list is curated, one row per
  institution, subdomains per row (`uw.edu.pl` deliberately without).
- **Consensus hides on the chat, one click on posts.** Three reports from distinct trusted accounts
  hide a chat message on their own; a post is hidden by any one trusted user (and lands on the board
  where the others can put it back). Consensus for posts was considered and not taken — a product
  decision, not a technical one.
- **Hermetic is a feature.** In-jokes nobody outside the Faculty understands are the material; the
  content is Polish and is not translated (the German and Latin eras of the time machine keep Polish
  post titles).
- **Anybody with an account may add a subject by naming it; a person appears only once a post
  naming them is published**, and the moderator sees a NOWA chip on the queue card first. A subject
  has no consent question; a person does (`DESIGN.md` "Naming a person into existence").
- **Nothing takes money, nothing runs ads.** The site is one small VPS and free tiers
  (`deploy/OVH.md`).
- **The application never contacts an authority.** A human forwards an approved escalation through
  Dyżurnet.pl and only then confirms it (`LEGAL.md` §7).

## Left open

Named so that somebody can close them; the engineering-level gaps are in `CLAUDE.md`.

- **No e-mail beyond address verification.** Password reset, any notification, the confirmation of
  receipt a DSA notice is owed, and the alert that tells a head-admin an escalation is waiting —
  today they learn by logging in. The SMTP for verification already exists; that alert is the first
  thing to build on it.
- **We never learn whether a verification mail landed.** `send_mail` returns once Brevo accepts the
  message, so the account page says „wysłaliśmy” and that is the last the site knows; a bounce, a
  block or a greylist delay goes to Brevo and nobody reads it (22.09.2026: a `@fuw.edu.pl` tester
  waited, assumed it was broken, and it arrived later — `deploy/OVH.md` step 3). Brevo posts
  delivery events to a webhook; an endpoint for it, the event stored on `EmailVerification` and one
  honest sentence — „nie doszło”, „czeka u odbiorcy” — would end the guessing, and would say it in
  the one place the person is already looking.
- **„Kontrowersyjne" is per post and nothing else.** No per-person or per-category equivalent, no
  second tier between trusted and public, and a locked post may still be `featured` — nothing stops
  the two, and the home strip prints a title and no picture for it. The time machine's own layout
  versions (`VersionV1/V2.svelte`) draw their card markup themselves, so a locked post shows there
  as a bare title with no lock pill; harmless (nothing leaks) and not yet pretty.
- **No real-time anything.** The chat polls.
- **No syntax highlighting in the LaTeX editor** — a textarea with a line gutter, by choice.
- **LaTeX.js covers a subset**: no TikZ, no custom packages; the error panel says so.
- **No user profiles** beyond „Moje wpisy” (`/moje`) and the account page.
- **Only the home page has a time machine**; the layout registry (`versions.ts`) is the ground for
  other pages to get one.
- **Portraits**: no escalation path for a portrait, no direct-to-R2 upload, no per-photo report
  button — the person's own consent entry is the door today.
- **Consensus moderation for posts**, as on the chat — see above.
- **Search on Postgres** (`hunspell-pl` + `pg_trgm` on the two derived columns) — half built: the
  columns exist and the query shape is portable; the other half needs Postgres locally
  (`docs/gemini/note.md`).
- **Recovering the pre-2010 folklore** from the Wayback Machine and Usenet — a separate project.

## Research

Five Gemini Deep Research reports answer parts of `docs/research-brief-gemini.md`
(`docs/gemini/*.txt`, one paragraph each — read with `fold -s -w 120`); `docs/gemini/note.md` says
what each contains, what went into the code and what was deliberately deferred.
`docs/hosting-brief-gemini.md` is the hosting brief that preceded the move to OVH.
