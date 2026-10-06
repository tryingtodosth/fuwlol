# wum — the side app's accounts, example templates and anonymised publications

MedApp (deployed here as **WUM**, container `skoki`, served at `fuw.lol/fum`) kept nothing on this
server until 2026-10; `feedback/` was its one call. This app is what it keeps now, and the line
between these three tables and the patient's health data is the design (`models.py` docstring).
39 tests.

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

## Mirrored constants

`PAYLOAD_VERSION`, `WUM_ACCOUNT_TEXT_VERSION`, `WUM_PUBLISH_TEXT_VERSION`, `FORBIDDEN_PAYLOAD_KEYS`,
`MAX_PUBLICATION_BYTES`, `MAX_TEMPLATE_BYTES`, `TEMPLATE_DOCUMENT_VERSION`, `TEMPLATE_KEYS` and the
username regex also live in MedApp (`src/lib/api/wum.ts`, `src/lib/privacy/project.ts`,
`src/lib/templates/types.ts`) — a **separate repository**, so nothing can import across.
`tests.py MirroredConstantsTests` pins this side; `scripts/privacy-check.mjs` pins that one.
**Change the wording of the sign-up disclaimers or the publish statement → bump the matching text
version on both sides**, or every sign-up / publish answers 409 until the app is rebuilt.

## Routes

```
POST /api/wum/auth/{register,login,logout}/   GET|PATCH /api/wum/auth/me/
GET  /api/wum/templates/  GET /api/wum/templates/<slug>/        POST / PUT / DELETE: staff
GET  /api/wum/publications/  GET …/<uuid>/  GET …/mine/  POST …/  POST …/<uuid>/withdraw/
```

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
