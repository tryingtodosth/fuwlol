# accounts — registration, login, and the trusted tier

Three tiers plus one: user, **trusted**, staff (`is_staff`), head-admin (`is_superuser` or the
grantable escalation permission — `escalation/visibility.py`, not here). Reasoning: `DESIGN.md`
"The trusted tier"; endpoints: `MODERATION-API.md` "Verification". 24 tests.

## Rules

- **Trust is a confirmed e-mail at a curated domain** (`TrustedDomain`: `domain`, `institution`,
  `kind` `fuw|uw|pan|other`, `match_subdomains`, `is_active`; lowercased on save). Seeded by
  migration 0002 from `trust.TRUSTED_DOMAINS_SEED` (14 rows; `mimuw.edu.pl` inactive;
  `uw.edu.pl` deliberately **without** subdomains — `student.uw.edu.pl` is its own row). Curate in
  the admin, not in code.
- **Matching is strict** (`trust.match_domain`): lowercase ASCII, exactly one `@`, Django's
  `EmailValidator`, exact match, then a `.domain` suffix only where the row allows it.
  `x@fuw.edu.pl.evil.com` and `x@gmail.com@fuw.edu.pl` do not match. A refused domain's 400 names the
  accepted institutions (`accepted_institutions()`).
- `trust.is_trusted(user)` is what every other app's rule module asks (`archive.moderation`,
  `board.trust`, `portraits.rules`, `consent`). Never re-implement the check; staff is always trusted.
- `Profile` (1:1, created by a `post_save` signal): `affiliation_email`, `affiliation_domain`,
  `verified_at`, `reputation` (moved only by `board.moderation.settle_reports`).
  `EmailVerification`: `VALID_FOR` 24 h, single use; a new request voids the older links; the mail
  goes to `{FUWLOL_SITE_URL}/potwierdz?token=…`, and a failing SMTP is a **503**, not a pretend 202.
- Throttles: `register` 10/h and `login` 20/min per IP, `login_user` 10/min per **submitted
  username** (`LoginUsernameThrottle`), `verify` 5/h. These are the ones a browser-script session
  exhausts first (`frontend/e2e/CLAUDE.md`).
- `/api/auth/me/` carries `is_staff`, `is_superuser`, `is_trusted`, `affiliation` (with
  `mask_email`), `pending_verification`, `reputation`; the same `user` shape comes back from login
  and register.

## Routes

`/api/auth/{register,login,logout,me,verify/request,verify/confirm,trusted-domains}/`. Frontend:
`/logowanie`, `/rejestracja`, `/konto` (the verification form and the trusted badge), `/potwierdz`.
