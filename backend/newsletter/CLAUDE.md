# newsletter — the MedApp newsletter's list

Built 2026-11-10 for MedApp's vet clinic app on https://medapp.net, whose prototype banner has a
"Read more" with a sign-up form. The page calls this API with `fetch`; nobody is redirected here.
**Double opt-in**: a sign-up is `pending` until the person presses the button on the page the
mailed link opens (MedApp's `/newsletter`).

- `POST /api/newsletter/` `{email, consent_version, locale?}` → **202 `{ok: true}`, always the
  same** — new, pending, active, unsubscribed, cooldown, honeypot — so the endpoint never tells
  whether an address is on the list; the difference goes to the mailbox only (a confirmation link,
  or "already on the list" with the unsubscribe link). 403 for an origin not in
  `FUWLOL_NEWSLETTER_ORIGINS` (the links need a copy to point at); 503 `{mail: ['unavailable']}`
  when SMTP fails (the cooldown is not started).
- `POST /api/newsletter/confirm/` `{token}` → 200 (also on a second press), 410 expired
  (CONFIRM_DAYS = 7), 404 unknown, forged, voided by a newer sign-up, or after an unsubscribe.
- `POST /api/newsletter/unsubscribe/` `{token}` → 200 (also when already off), 404 unknown.
- **Tokens are signed, never stored** (`models.py`): confirm = `TimestampSigner` over the row id and
  `subscribed_at` in microseconds; unsubscribe = `Signer` over the row id, no expiry, so every
  issue can carry it. Rotating SECRET_KEY voids both.
- **The mail** (`mail.py`): plain text in en / pl / uk, from `medapp.net <info@medapp.net>` through
  medapp.net's own OVH mailbox (`FUWLOL_NEWSLETTER_MAIL`, `FUWLOL_NEWSLETTER_EMAIL_USER` /
  `_PASSWORD` in `/srv/fuwlol/.env`, ssl0.ovh.net:465) — not fuw.lol's Brevo relay; through the
  project's `EMAIL_BACKEND`, so console in DEBUG and locmem under tests. Links:
  `FUWLOL_NEWSLETTER_SITES[source]` + `/pl` or `/uk` (English bare) + `/newsletter#confirm=…` — a
  fragment, so the token is in no access log. `List-Unsubscribe` and `Auto-Submitted` headers.
- One mail per address per MAIL_COOLDOWN_MINUTES (10); a pending row older than PENDING_DAYS (30)
  is deleted at the next sign-up.
- CORS answered by the views themselves for `settings.FUWLOL_NEWSLETTER_ORIGINS` (default
  medapp.net and www), as `feedback/` does; `CORS_URLS_REGEX` leaves `/api/newsletter/` to them.
  Token auth only (a session cookie must not become a CSRF 403). Honeypot `website`. Throttle scope
  `newsletter` 20/hour over all three; a preflight is not throttled.
- **Mirrored in MedApp** `src/lib/newsletter/api.ts`: `EMAIL_MAX` (254), `CONSENT_VERSION`,
  `CONFIRM_DAYS` (7), `TOKEN_MAX` (200). Changing the consent wording means bumping the version on
  both sides.
- Stored: email, locale, source (by Origin), consent_version, status (`pending` / `active` /
  `unsubscribed`, one field), subscribed_at, confirmed_at, unsubscribed_at, mailed_at. No IP, no
  user agent, no account, no key.
- The admin's *Eksportuj potwierdzone adresy z linkiem do wypisania (CSV)* is how a list leaves:
  active rows only, each with its own unsubscribe URL. LEGAL.md §9d binds whoever sends an issue.
- Tests: `newsletter/tests.py` (24).
