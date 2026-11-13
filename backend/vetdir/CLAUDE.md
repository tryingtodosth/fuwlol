# vetdir — MedApp's clinic directory: a clinic's public card, and owners' visit requests

Built 2026-11-13 for MedApp's vet clinic app on https://medapp.net (VETDIR-S1, the medapp
repository's `docs/work/VETDIR-S1-BRIEF.md` and `VETDIR-S1.md`). A clinic that runs the vet app
fills a *Public page* card in its settings and lists itself; once it presses the link mailed to its
address, the card is public at medapp.net's `/vets/<id>`. Where the clinic chose it, a pet owner
with **no account** asks for a visit there — a day and a part of the day, never a slot — presses
the link mailed to them, and the request appears in the vet app as *requested*. Staff confirm it
(after making the real diary entry in the app) or decline it; the owner gets one mail either way.

**A tester service.** Holding requests here knowingly overrides ISS-009's default in the medapp
repository ("the project hosts nothing but a demo until there is a legal entity and someone on
call") for this prototype; MedApp's ISS-063 says what this holds and what a lawyer must answer.
Every MedApp surface says requests sit on a tester service with nobody on call.

## Rules

- **Two tables, nothing about the sender**: `Listing` (the card, the clinic's e-mail for the one
  confirmation mail, the key's SHA-256, `status` pending | listed | unlisted, the idle clock
  `seen_at`) and `VisitRequest` (the owner's name, phone, e-mail, species, the animal's name, the
  wished day and part of day, one sentence ≤ 300, the locale, `status`, the start staff set). No IP,
  no user agent, no account; `tests.py` pins both field sets.
- **The card is structured facts only** (`rules.clean_card`, keys `CARD_KEYS`): name, register type
  (closed), address, town, phone, hours windows (`wum`'s shape), species, services and languages
  (closed lists), an out-of-hours choice (closed) plus an optional phone, `accepts_requests`. A key
  outside the list is dropped, never stored: **no free paragraph, no price, no person's name, no
  photo.** Nothing anywhere ranks, rates, counts or reviews.
- **Public is derived** (`rules.is_public`): `listed` and refreshed by a key-holder call within
  `LISTING_IDLE_DAYS` (180). Pending, unlisted, idle and unknown are one 404 (root rule 5). A lost
  key cannot change or unlist the page; it stops being public by itself.
- **The clinic's key**: minted at the first listing, returned ONCE in the 201, kept as a SHA-256,
  presented in the `X-Vetdir-Key` header and compared with `hmac.compare_digest`. A wrong key is the
  same 404 as an unknown id.
- **The one transition table** (`rules.REQUEST_TRANSITIONS`, mirrored in MedApp):
  `pending_email → requested` (the owner's mailed link) · `requested → confirmed | declined` (the
  key; `confirmed` carries the start) · `pending_email | requested | confirmed → cancelled` (the
  owner's signed cancel link, in every mail with something left to cancel). Nothing leaves
  `declined` or `cancelled`; anything else is 400 `status`. A retried clinic decision with the same
  outcome is 200 with no second mail.
- **The clinic never sees an unconfirmed request**: `GET listings/<id>/requests/` returns only rows
  the owner confirmed (`email_confirmed_at` set) and not yet blanked — not even one cancelled
  before it was confirmed.
- **Every request answer is the same 202** — new, repeated within MAIL_COOLDOWN_MINUTES (10, per
  listing and address), honeypot — as `newsletter/` does. A listing that is not public or does not
  take requests is the page's own 404; a field refused is 400 naming it (Polish sentences, the client
  keys off the name).
- **Kept and swept** (`rules.sweep`, run at every write and by `manage.py vetdir_sweep`; there is no
  scheduler): a request's personal fields are blanked REQUEST_KEEP_DAYS (30) after a terminal
  decision or after the wished day (or the confirmed start, if later); an unconfirmed one after
  REQUEST_UNCONFIRMED_DAYS (2), which is also how long its link works. The row stays, empty (root
  rule 6). A listing never confirmed is deleted after LISTING_PENDING_DAYS (30): it was never public
  and its address may be somebody else's. An SMTP failure on a request blanks it at once (503).
- **Tokens signed, never stored** (`models.py`): the listing's and the request's confirmation links
  are `TimestampSigner` over the row and its `created_at` (7 days / 2 days); the cancel link is a
  `Signer` over the row, no expiry. SECRET_KEY rotation voids them all.
- **Mail** (`mail.py`, `newsletter/mail.py`'s way): plain text in en / pl / uk, from
  `settings.FUWLOL_VETDIR_MAIL` (by default the newsletter's mailbox, `info@medapp.net`),
  `Auto-Submitted`, the Message-ID on the sender's domain; links are
  `FUWLOL_VETDIR_SITES[source]` + `/pl` or `/uk` (English bare) + `/vets/confirm#listing=|confirm=|cancel=…`
  — the fragment, so no token reaches an access log. Four mails: the clinic's confirmation; the
  owner's confirmation; *confirmed* (the time in Europe/Warsaw and the clinic's phone); *declined*
  (the phone). **No mail to the clinic per request** in S1: the app shows them when opened.
- **Transport**: no authentication class at all (a session cookie means nothing here and can never
  be a CSRF 403); CORS answered by the views for `settings.FUWLOL_VETDIR_ORIGINS` (default medapp.net
  and www), methods GET/POST/PUT, header `X-Vetdir-Key`, `Vary: Origin`, no credentials;
  `CORS_URLS_REGEX` leaves `/api/vetdir/` to them. A write needs a known Origin (403 otherwise). The
  public GET answers any caller, with CORS only for a known origin. Scopes: `vetdir_listing` 10/hour
  (list, update, unlist), `vetdir_request` 20/hour, `vetdir_token` 60/hour (the three link presses),
  `vetdir_clinic` 600/hour (the key's list and decisions), `vetdir_read` 600/hour; a preflight is
  never throttled.
- **Admin**: listings only — list, search, *unlist* (the takedown); no add, no delete, the key hash
  excluded. **Requests have no admin and no export.**

## Example data (Amendment 1)

`manage.py vetdir_seed_examples [--clear]` makes five fictional listings under the fixed ids
`example-0001` … `example-0005` (every register type; a lunch break, a closed Wednesday, a Saturday
morning, around the clock; one phone-only and one more; the out-of-hours notes) and, at
`example-0001`, a request in every status — the demo clinic's people, `.example` addresses,
`+48 000 000 …` phones, "(PRZYKŁAD)" in every name and "adres przykładowy" in every address. Every
row has `example = True`: the public card answers `example: true` (MedApp draws "an example, not a
real clinic"), a request to an example listing is the same 202 and is **kept and mailed nowhere**,
a seeded request is never mailed (the views check the flag; `mail._send` refuses a `.example`
address as a second look). Idempotent; `--clear` removes exactly those rows and stops if a real
listing ever held one of the ids. **Never run by a migration or at start-up** — the coordinator
decides whether a server carries it.

## Mirrored constants

Everything in `rules.py` with a MIRRORED comment — `CONSENT_VERSION`, `REGISTER_TYPES`, `SPECIES`,
`SERVICES`, `LANGUAGES`, `OUT_OF_HOURS`, `PARTS_OF_DAY`, `LISTING_STATUSES`, `REQUEST_STATUSES`,
`REQUEST_TRANSITIONS`, `CARD_KEYS`, `REQUEST_KEYS`, the limits — also lives in the medapp
repository's `src/lib/vetdir/api.ts`. `tests.py MirroredConstantsTests` pins this side and
`scripts/vetdir-check.mjs` group A pins the same literals there. `CONSENT_TEXT_EN` is MedApp's
`vd_consent` in English byte for byte (vetdir-check A7). `VISIT_REASON_MAX` and
`HOURS_MAX_ENTRIES` are `wum`'s (a test says so), so the two apps can be merged later.

## Accepted, and left open

- The clinic's e-mail is fixed at listing; changing it is a new listing (S1).
- `unlisted` is final for that listing; listing again is a new page with a new key.
- Owners' names, phones and e-mails sit here unencrypted beyond Postgres for up to 30 days after the
  visit — ISS-063 in MedApp, with the six questions for a lawyer.
- No list or search of clinics, no map, no slots (S2 and later); no reminders, no SMS.
- The throttle counter keys on the address for an hour in the file cache, like every scope here.
- Tests: `vetdir/tests.py` (49).
