# survey — one anonymous questionnaire sheet, from the LSD copy of MedApp

LSD (`fuw.lol/lsd`, the `lsd` container; MedApp from `github.com/tryingtodosth/medapp`, built
with `/lsd` baked in and pushed under the `lsd-` image tags) carries a retrospective questionnaire
about psychedelic use, run as **preparation for a student experiment by a project not affiliated
with any university**; the controller is Piotr Putyło, `admin@fuw.lol` (`rules.CONTROLLER`). This
app is where a finished sheet lands. 41 tests.

## Rules

- `SurveyResponse`: `survey` (a key of `rules.SURVEYS`), `version`, `consent_version`, `status`
  (`received | withdrawn`, ONE field), `withdrawn_on`, `locale`, `duration_s`, `answers` (JSON),
  `contact_hash`, `key_hash`, `received_on` (a DATE). **Nothing about the sender**: no `ip_hash`,
  no `author`/`user`, no user agent, no timestamp — `models.py` says why and `tests.py` pins the
  exact field list. Do not add any of them "for debugging".
- `POST /api/survey/` and `POST /api/survey/withdraw/` only; `TokenAuthentication` only
  (same-origin with the archive, so a stray session cookie must not be a CSRF 403 —
  `feedback/views.py`), `AllowAny`, honeypot `website`, scopes `survey` **60/hour** (a lecture
  room behind one NAT must finish) and `survey_withdraw` 20/hour, per IP.
- **Refusals name the field** (`survey`, `version`, `consent_version`, `answers`, `contact_email`,
  `wants_key`, `website`, `key`) in Polish; the client is trilingual and keys its translation off
  the name. Unknown `survey`, stale `version` and stale `consent_version` are 400 (the client
  says "reload"). `answers` is checked for SHAPE only (`rules.clean_answers`: an object, 1..200
  keys matching `KEY_RE`, values string ≤ 2000 / int within ±1 000 000 / bool / null / list of
  ≤ 50 strings ≤ 200, no control characters but `\n` and `\t`, ≤ 64 kB of UTF-8). Which question
  ids exist is the client's business.
- **`locale` and `duration_s` never refuse a sheet**: they are `JSONField`s in the serializer so
  that no type refuses them, and anything that does not fit is dropped to `''` / `null`.
- **The consent text lives here too.** `CONSENT_STATEMENTS` are the three required checkboxes the
  client shows (the goal — preparation of a student experiment; no university; the controller),
  byte-identical, and `CONSENT_VERSION` is their date; the sheet records which version was
  ticked. Change a word → bump the date on both sides, or every sheet is 400 `consent_version`.
- **Two opt-in ways back, hashes only.** `contact_email` (refused by name if malformed, because
  the person typed it on purpose) is stored as `hash_contact` — HMAC under `FUWLOL_IP_SALT` in its
  own context — and the controller honours a request from that address with `manage.py
  survey_withdraw --email`. `wants_key: true` makes the server mint a 256-bit key, return it
  ONCE in the 201 (`key`, else `null`) and keep its SHA-256; `POST /api/survey/withdraw/
  {key}` blanks the sheet (`rules.withdraw`: `answers = {}`, `contact_hash = ''`, `status =
  withdrawn`, `withdrawn_on` = today; the row stays, root rule 6). Unknown key 404, known key
  200 whether or not already withdrawn — the key is the holder's secret, so that is no oracle.
  Neither hash appears in the admin or the export.
- **No GET.** The admin (`/admin/survey/surveyresponse/`) is read-only; deletion is
  `is_superuser` only — that is how the table is emptied when the study is done (`LEGAL.md` §9b).
  `manage.py export_survey <slug> [--format jsonl|csv] [--since YYYY-MM-DD] [--include-withdrawn]`
  writes to stdout; `manage.py survey_withdraw --email|--key|--id [--dry-run]` is the
  controller's half of a withdrawal.
- The answers are never rendered: the admin shows them through `format_html` in a `<pre>`, and
  no renderer in this project touches them. Rule 4 applies the day that changes.

## Mirrored constants

Everything in `rules.py` with a MIRRORED comment — `SURVEYS`, `CONSENT_VERSION`,
`CONSENT_STATEMENTS`, `MAX_KEYS`, `KEY_RE`, `MAX_STRING`, `MAX_LIST`, `MAX_LIST_ITEM`, `MAX_INT`,
`MAX_ANSWERS_BYTES`, `MAX_DURATION_S`, `MAX_EMAIL`, `MAX_KEY` — also lives in the medapp
repository's `src/lib/survey/api.ts`. Separate repository, nothing imports across;
`tests.py MirroredConstantsTests` pins this side. A new questionnaire or a changed one is a new
key or a bumped `version` here AND there.

## Accepted, and left open

- The `id` orders sheets within a day, and the throttle counter keys on the address for an hour
  in the file cache (no row id in it). Both accepted; a random public id would remove the first.
- The proxies' access logs (Cloudflare, Caddy, nginx, gunicorn) still record that *somebody* at an
  address POSTed `/api/survey/` at a second — the date-only row is what keeps that line unjoinable
  to a sheet. Their retention is theirs, not this app's.
- A sheet with an e-mail hash is findable by whoever knows the address AND the salt; that is the
  person's own choice, made after the client's second look ("this links your answers to you"),
  and withdrawal blanks the hash too. No confirmation mail is sent (the mail gap of root
  `CLAUDE.md`); a typo in the address means no way back, and the client should say so.
- "Modify" is withdraw + send again (a new row, a new key); there is no PUT.
- No retention clock: rows stay until the head admin empties the table after the export; the
  restic dump holds them until then (`LEGAL.md` §10).
- Notes filed from the LSD copy through `POST /api/feedback/` are tagged `app='skoki'` like the
  first copy's — `feedback.APP_CHOICES` has one value. A second value would tell them apart.
- A CSV cell beginning with `=` is exported verbatim (`export_survey` docstring); the JSON Lines
  form has no such problem.
- Django parses the whole request body before the 64 kB check runs (`DATA_UPLOAD_MAX_MEMORY_SIZE`
  30 MB) — the same as every endpoint here; the cap bounds the ROW, not the request.
