# board — the chat, an old-school shoutbox

Anyone may write, guests under a nick. Reasoning: `DESIGN.md` "The chat"; endpoints:
`MODERATION-API.md` "Chat" and "Chat reports". 38 tests.

## Rules

- `Message`: `author` (SET_NULL — the message outlives the account), `nick` (`DEFAULT_NICK`
  „Anonim"; a guest nick may **not** equal an existing username), `body` ≤ `MAX_LEN = 2 ** 11`
  (2048; mirrored in `frontend/src/lib/components/board/types.ts`), `format` `text|latex`,
  `ip_hash` = HMAC-SHA256 under `FUWLOL_IP_SALT` (`hash_ip`) — never the address.
- **Links yes, images no, LaTeX yes**: `![`, `<img`, `\includegraphics`, `data:image` → 400;
  at most 5 links; a `website` honeypot field that must stay empty; the body goes through
  `archive.latexguard.check_source` like a post. The frontend renders with the same two renderers,
  images switched off, and folds everything past 100 characters under a spoiler.
- The list pages **by id** (`before` / `since`, `limit` ≤ 100) because the stream grows at the top;
  `include_hidden` is honoured for trusted and staff only. `feeds.BoardFeed` is RSS 2.0 of the last
  `FEED_SIZE` 50 visible messages at `/api/board/rss/`.
- Throttles: `board_anon` 20/h, `board_user` 60/h, `board_report` 20/h, `escalate` 10/day.

## Reports and reputation (`moderation.py`)

`Report.REASONS` `spam|offensive|illegal|privacy|other` (mirrored in `board/types.ts`
`REPORT_REASONS`). `register_report`: the author cannot report their own message
(`SelfReportError` → 403), a signed-in user only once (`DuplicateReportError`, unique constraint
when the reporter is known), guest reports are stored but **never count**. **Three distinct trusted
accounts** auto-hide a still-visible message (`AUTO_HIDE_TRUSTED_REPORTS`, `hidden_by = null`).
`settle_reports` on a hide / restore resolves every open report and moves each *trusted* reporter's
`Profile.reputation` by +1 / −1 — except the acting moderator's own. Reputation is a **record, not a
lever**: nothing is unlocked by it (`PRODUCT.md`). Hide and restore are refused (403) while the
message is escalated.
