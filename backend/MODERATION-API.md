# Trusted tier, moderation board, chat — API

Tiers: **public** (anyone) · **user** (any account) · **trusted** (an account with a confirmed
institutional e-mail, `is_trusted`) · **staff** (Django `is_staff` — the real administration).
Staff is always trusted. Auth: `Authorization: Token …`.

## Verification (`accounts`)

| Method & path | Tier | Body → response |
|---|---|---|
| `POST /api/auth/verify/request/` | user | `{email}` → `202 {sent_to: "j***@fuw.edu.pl"}`. `400 {email:[…]}` if the domain is not on the active list (the message names the accepted institutions) or another account already confirmed that address. Throttle `verify` 5/hour. Sends a mail with `{FUWLOL_SITE_URL}/potwierdz?token=…` (24 h, single use; a new request voids older links). `503` if SMTP fails. |
| `POST /api/auth/verify/confirm/` | public | `{token}` → `200 {ok: true, is_trusted: true, institution}`; `400 {detail: "Link wygasł lub został już użyty."}` (also for a domain deactivated meanwhile). |
| `GET /api/auth/trusted-domains/` | public | `[{domain, institution, kind}]` — active domains only. Curated in the admin (`TrustedDomain`, subdomain matching per row; `uw.edu.pl` deliberately without it). |
| `GET /api/auth/me/` | user | adds `is_trusted`, `affiliation: {institution, domain, email_masked, verified_at} | null`, `pending_verification: masked email | null`. Same shape under `user` in login/register responses. |

Domain matching is strict: lowercase ASCII, exactly one `@`, Django's EmailValidator, exact
match, then a `.domain` suffix only where `match_subdomains` is on. `x@fuw.edu.pl.evil.com`
and `x@gmail.com@fuw.edu.pl` do not match.

## What a trusted user may do (`archive`)

- Their own new posts publish immediately (no queue).
- `POST /api/posts/{slug}/hide/` `{reason?}` → the post leaves the public page, its open reports
  are resolved, a `ModerationAction` is written. Response: the board row.
- `POST /api/posts/{slug}/restore/` → back to its previous status (`published`, or `pending` if
  it had never been approved). A **nuked** post: staff only (`403` for trusted).
- `POST /api/posts/{slug}/nuke/` `{reason}` — reason **required** (`400` without). From then on
  only staff can read it.
- `POST /api/comments/{id}/hide/ | restore/ | nuke/` — same rules for comments.
- `GET /api/moderation/board/?status=hidden|nuked&kind=posts|comments&page=N` → trusted/staff:
  `{count, page, pages, page_size, next, previous, posts: [...], comments: [...]}`, newest action
  first. A **hidden** post is the full post payload plus `moderation: {action, actor, reason,
  at, previous_status}`; a **nuked** post for a non-staff caller is ONLY
  `{id, catalog_no, status: "nuked", moderation: {actor, reason, at}}` — no title, body, files or
  slug. Comments likewise (`{id, post_id, moderation}` when nuked and not staff; otherwise the
  comment plus `post_id`, and `post_slug`/`post_title` when the caller may see the post).
- `GET /api/posts/{slug}/` → for a trusted reader a hidden post comes back with
  `moderation_notice` and `moderation`; a nuked post is `404` for everybody but staff.
  Every detail response carries `can_moderate` (= caller is trusted).
- `GET /api/posts/{slug}/comments/` → a hidden/nuked comment stays in the thread as a placeholder
  (`body: ""`, `author: ""`, `moderation: "hidden"|"nuked"`); trusted callers get a hidden
  comment's real body, staff a nuked one's.
- Public lists, search, random, timeline and stats only ever count `published`.
- Staff-only `POST /api/posts/{slug}/moderate/` gained decisions `hide` and `nuke` (audited).

## Chat (`board`)

| Method & path | Tier | Notes |
|---|---|---|
| `GET /api/board/?limit=50&before=<id>&since=<id>&include_hidden=1` | public | `{count, latest_id, results: [{id, nick, is_guest, author_id, format, body, created_at, is_hidden, can_hide}]}` newest first; `limit` ≤ 100; `include_hidden` honoured for trusted/staff only. |
| `POST /api/board/` | public | `{nick?, body, format?: text|latex, website: ""}` (honeypot must be empty). Body ≤ **2048** characters (2^11), no images (`![`, `<img`, `\includegraphics`, `data:image` → `400`), ≤ 5 links, a guest nick may not equal an existing username. Throttles `board_anon` 20/hour, `board_user` 60/hour. |
| `POST /api/board/{id}/hide/` / `restore/` | trusted | |
| `GET /api/board/rss/` | public | RSS 2.0 of the last 50 visible messages. |

The frontend shows only the first 100 characters of a message; the rest folds under a spoiler.
