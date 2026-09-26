# feedback — one note about one screen, from an app that has no backend of its own

MedApp (deployed here as **FwUMU**, container `skoki`, served at `fuw.lol/fwumu`) calls exactly
one endpoint on this server, and this is it. 16 tests.

## Rules

- `Feedback`: `app` (`skoki` today), `kind` `bug|suggestion|idea|comment`, `text` ≤ `MAX_LEN`
  4096, `location` (the screen path, **filled in by the app, hidden from the person writing**),
  `locale`, `ip_hash` (`board.models.hash_ip` — the one place in this project that hashes an
  address; not a second copy of the salt logic), `author` (null in practice: FwUMU has no
  accounts and sends no token), `status` `new|triaged|done|spam`, `created_at`.
- **Only `text` can refuse a note.** `location` and `locale` are hidden fields with no
  `max_length` and `allow_null`, and anything that is not a path / not a language tag is dropped
  to `''`. Both of those refused a submission the first time the suite ran — a note lost because
  a *hidden* field was malformed is the one failure this endpoint cannot afford.
- `POST /api/feedback/` only, `AllowAny`, honeypot `website`, throttle scope `feedback`
  **120/hour** — generous on purpose: a feedback session is a room behind one NAT, and the
  fourth person to speak up must not get a 429 (`settings.py` says the same).
- **There is no GET.** The queue is read in the Django admin (`/admin/feedback/feedback/`),
  where `status` is the only editable field. Listing notes over the API would let one person at a
  session read what everybody else wrote — root `CLAUDE.md` rule 5.
- The refusals are Polish sentences like everywhere else, but the caller is trilingual, so the
  widget keys its own translated message off the **field name** (`text`, `kind`) and falls back
  to the sentence. `src/lib/feedback/api.ts` in the MedApp repo is the other half.

## Mirrored constants

`KIND_CHOICES` and `MAX_LEN` also live in MedApp's `src/lib/feedback/api.ts` — a **separate
repository**, so nothing can import across the two. `tests.py MirroredConstantsTests` pins this
side so that a change is a visible diff on both.

## The text is never rendered

`text` is plain text: it is read in the Django admin, which escapes it, and no renderer in this
project touches it. That is why `archive.latexguard.check_source` does **not** run on it — a bug
report quoting `\includegraphics` is a bug report, not an attack. **If a `/moderacja` view ever
draws these notes with `lib/render/`, rule 4 applies and the guard has to go on this write path
first.**

## Left open

- No mail and no alert when a note arrives; somebody opens the admin. Same gap as everywhere
  else in this project (root `CLAUDE.md`, "No mail beyond the verification SMTP").
- No API read path, so no in-site queue and no reply-to-the-reporter. There is nowhere to reply
  *to*: the endpoint asks for no address, on purpose.
- Notes are never deleted or retained-out. `ip_hash` has no sweeper here, unlike
  `Post.submitter_ip` (`forget_submitter_ips`); it is a hash, not an address, and the table is
  expected to hold hundreds of rows, not millions. Revisit if either changes.
