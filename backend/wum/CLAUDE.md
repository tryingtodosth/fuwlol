# wum — the side app's accounts, example templates, anonymised publications and, since 2026-10-07, practitioners' diaries and notes

MedApp (deployed here as **WUM**, container `skoki`, served at `fuw.lol/fum`) kept nothing on this
server until 2026-10; `feedback/` was its one call. This app is what it keeps now, and the line
between these tables and the patient's health data is the design (`models.py` docstring).
64 tests.

## The rows

- `WumProfile` (1:1 `User`): the MARK that makes a user a WUM account, plus four optional fields
  (`first_name`, `surname`, `contact_email`, `contact_phone`) and `agreed_text_version`. `User.email`
  stays blank for these accounts — the contact address is on the profile, so the archive's e-mail
  uniqueness never collides and a WUM address is never an archive login.
- `Template`: a fictional example patient, `document` = the app's own `medapp.export/2` document
  minus consent state and audit trail (`TEMPLATE_KEYS` / `TEMPLATE_REFUSED_KEYS`), one `status`
  `draft | published | retired`. Authored in the app (export → "Example template"), pasted into
  `/admin/wum/template/` or POSTed by staff. New demo data is a row, not an image rebuild.
- `Publication`: a record a person chose to publish, ANONYMISED BY THE APP before it left the phone
  (`projectForPublication` in the medapp repository, field by field). `public_id` (uuid) is the
  only id ever exposed; `account` is kept for one reason — withdrawal — and never serialised
  publicly. One `status` `published | withdrawn | superseded`; `consent_text_version` stamped.

- **The practice round** (2026-10-07) — three more rows, and the first that hold something a
  person said about a body, said knowingly to somebody:
  - `Practice` (1:1 `User`, `PROTECT`): the row is the mark that a WUM account is a practitioner
    (`rules.is_practitioner`). `display_name` is what patients see — never the username;
    `profession` is a closed list (`PROFESSIONS`, mirrored in the app); `hours` is a JSON list
    of `{weekday 0–6 Monday-first, open, close}` in Europe/Warsaw (`rules.hours_problems`, on
    the API and the admin form alike); `slot_minutes` cuts the hours into bookable slots;
    `listed` is off until the practitioner says so.
  - `Visit`: one slot in the diary. `patient` null = the practitioner's own block. One `status`
    (`requested | confirmed | declined | cancelled | completed | no_show`); `requested` and
    `confirmed` hold the slot (`VISIT_HOLDING_STATUSES`). `reason` is the patient's sentence
    (300 chars) and goes to the practitioner only; `note` is the practitioner's word on the row
    (a decline reason the patient reads, a block's label). Rows are never deleted.
  - `PracticeNote`: the practitioner's note about a patient, **append-only at the model**
    (`save()` refuses every update but sharing, `delete()` always); a correction is a new note
    whose `amends` names the old one. Private to the practice unless `shared_with_patient`, and
    sharing is ONE WAY (`rules.share_note`): a patient who could read it has read it.

## Rules (`rules.py`)

- **Token authentication only on every view**, like `feedback/`: the app is same-origin with the
  archive, and a stray session cookie would otherwise be a CSRF 403. The app sends
  `credentials: 'omit'` and its own `Authorization: Token …`, stored under `medapp:account`, never
  `fuwlol.token`.
- **Two populations, one user table, nothing else shared.** `is_wum_account(user)` is what the
  WUM views ask (`IsWumAccount`). A WUM account has no archive powers; an archive account's correct
  password at `/api/wum/auth/login/` is the SAME 401 as a wrong password (no oracle, root rule 5).
- **One live publication per account.** `publish()` supersedes the previous live row atomically
  (`superseded_by` set) and the public list shows one record per person, newest first.
- **Withdrawal is one tap and no review** (art. 7 ust. 3 RODO): `withdraw()` sets `withdrawn`;
  a stranger's attempt, a withdrawn row and an unknown uuid are the same 404. Rows are never
  deleted (root rule 6); the payload is kept on a withdrawn row — blanking it after a retention
  window is left open.
- **Defence in depth on the payload**: `payload_problems()` refuses a size over
  `MAX_PUBLICATION_BYTES`, a `version` that is not `PAYLOAD_VERSION`, an `ageBand` that is not
  `NN–NN`, and ANY key of `FORBIDDEN_PAYLOAD_KEYS` at any depth (400 keyed `payload`). The app's
  projection is the boundary; this is the second look. A bare `name` is deliberately allowed —
  medicines carry one.
- **409 means the world moved**: a `consent_text_version` the server no longer shows, or a
  `payload_version` it does not understand. Keyed by the field so the app says "refresh / update".
- Templates: `template_problems()` runs on BOTH write paths (the serializer and the admin form).
  `DELETE` retires, never deletes. Only `published` rows are listed or fetched; a draft is a 404.
- Throttles (`settings.py`): `wum_register` 10/h, `wum_login` 20/min (+ the archive's
  `login_user` per submitted name), `wum_profile` 60/h, `wum_publish` 20/h, `wum_template_write`
  60/h — all per IP, and all on WRITES only (`UnsafeScopedThrottle`): `GET /api/wum/auth/me/` runs
  on every app start.

- **The practice round.** The server is the authority on what is free: `open_slots()` cuts
  the hours into slots minus the past, minus anything beyond `VISIT_HORIZON_DAYS` (60) and minus
  the held; `request_visit()` re-checks under `select_for_update` so two phones asking for the
  same slot get one visit and one refusal (400 keyed `start`). A patient's request must be a slot
  `open_slots` would offer; the practitioner's own entry (`practitioner_visit`) may be outside
  the hours and is `confirmed` at once. Who may move a visit where is `PRACTITIONER_TRANSITIONS`
  / `PATIENT_TRANSITIONS`: the patient only cancels, and only before the end; `completed` /
  `no_show` only after the start; final states are final; a visit that is neither the caller's
  as patient nor in their practice is the 404 of an unknown id. A practice's "patients" are the
  people with a visit here; `practice/me/patients/<username>/` answers the same 404 for a
  stranger with an account as for a name that does not exist. What the practitioner sees of a
  patient is `patient_card`: the username and whatever the patient put on their own account —
  nothing from any health store, because the server has none.

## Mirrored constants

`PAYLOAD_VERSION`, `WUM_ACCOUNT_TEXT_VERSION`, `WUM_PUBLISH_TEXT_VERSION`, `FORBIDDEN_PAYLOAD_KEYS`,
`MAX_PUBLICATION_BYTES`, `MAX_TEMPLATE_BYTES`, `TEMPLATE_DOCUMENT_VERSION`, `TEMPLATE_KEYS`, the
username regex — and, from the practice round, `PROFESSIONS`, `VISIT_REASON_MAX`,
`VISIT_NOTE_MAX`, `PRACTICE_NOTE_MAX`, `VISIT_HORIZON_DAYS` and the two transition tables — also
live in MedApp (`src/lib/api/wum.ts`, `src/lib/privacy/project.ts`,
`src/lib/templates/types.ts`) — a **separate repository**, so nothing can import across.
`tests.py MirroredConstantsTests` pins this side; `scripts/privacy-check.mjs` pins that one.
**Change the wording of the sign-up disclaimers or the publish statement → bump the matching text
version on both sides**, or every sign-up / publish answers 409 until the app is rebuilt.

## Routes

```
POST /api/wum/auth/{register,login,logout}/   GET|PATCH /api/wum/auth/me/
GET  /api/wum/templates/  GET /api/wum/templates/<slug>/        POST / PUT / DELETE: staff
GET  /api/wum/publications/  GET …/<uuid>/  GET …/mine/  POST …/  POST …/<uuid>/withdraw/

GET  /api/wum/practices/  GET …/<uuid>/  GET …/<uuid>/slots/?from=YYYY-MM-DD&days=14    public
GET|PUT /api/wum/practice/me/                                     any WUM account (PUT opens it)
GET|POST /api/wum/practice/me/visits/?from=&to=                   the diary; POST = block or by-hand visit
GET  /api/wum/practice/me/patients/   GET|POST …/<username>/      the card, visits and notes; POST = a note
POST /api/wum/practice/me/notes/<uuid>/share/
POST /api/wum/visits/   GET /api/wum/visits/mine/   POST /api/wum/visits/<uuid>/{confirm,decline,cancel,complete,no_show}/
GET  /api/wum/notes/mine/                                          the notes shared with this patient
```

Throttles (writes only): `wum_practice` 120/h, `wum_visit` 120/h.

## Left open

- No e-mail verification, no password reset, no account-deletion endpoint: an account is
  deactivated in the admin (DRF refuses an inactive user's token); `Publication.account` is
  `PROTECT`, so a user with publications cannot be deleted at all.
- Withdrawn and superseded payloads stay in Postgres and in the restic backups. A sweeper that
  blanks them after a window (model: `consent`'s `forget_claim_ips`) is the candidate.
- A single person's record cannot be k-anonymous. The app minimises (age band, month precision, no
  names, no places, free text off by default); it does not anonymise statistically, and the
  publish screen says so. A lawyer's and an ethics read are owed before this is promoted.
- Nothing stops a WUM account from logging in to the ARCHIVE as a plain user (same credentials, no
  powers). One `is_wum_account` check in `accounts/views.LoginView` would refuse it if wanted.
- The app refuses publication under 18 on the phone; this server cannot verify an age.
- **The practice round holds health-shaped text on this server**: a visit's `reason` and a
  practice's notes. Both are behind the sign-up disclaimer ("no real health data") and the app
  says on both screens where the text goes; neither is encrypted at rest beyond Postgres and the
  restic backups, and nothing blanks them after a window. A practitioner is anybody with a WUM
  account who opens a practice — no licence check (the app's `/clinician` mockup has the PWZ
  check-digit; this does not). Whether a practice's rows are the practitioner's record (and
  theirs to export) or the patient's (and theirs to erase) is the controller question of
  ISS-036/ISS-037 in the medapp repository; today a patient can cancel a visit and read what
  was shared, and cannot delete either.
