# consent — the person's own say about their image

`Post.rights_confirmed` is the uploader's declaration. The person a post is about — usually with
no account here — gets this channel: **„Jesteś tą osobą?"** on their profile. The legal basis
(art. 81 pr. aut., art. 7 RODO) is `LEGAL.md` §3; the reasoning `DESIGN.md` "Consent". 31 tests.

## The rows

- `PersonClaim`: one row per claim with **one** `status` — `sent | verified | approved | rejected |
  superseded | withdrawn` (`LIVE_STATUSES` = approved). Fields: the wish, the e-mail, `token`
  (24 h, single use) and `manage_token`, `consent_text_version`, `requester_ip` / user-agent,
  `applied_at`, `previous_consent`, `previous_listed`, `decided_by/at/note`. **The approved row is the
  evidence of consent and is never deleted**; a change writes a new row and marks the old one
  `superseded`.
- `ConsentHide`: which posts a claim hid and from which status (`previous_status`), one per claim
  per post — so a rejection or a later loosening reverts **exactly** those and nothing a moderator
  hid for other reasons.

## Wishes, and what they write

| wish (`WISH_CHOICES`) | worded for the person | `Person.image_consent` |
|---|---|---|
| `images_ok` | zdjęcia ze mną mogą tu być | `granted` |
| `no_images` | wzmianki tak, zdjęć nie | `refused` |
| `no_mention` | nie chcę być w archiwum | `opted_out` |

`WISH_CONSENT` is that mapping; `STRICTNESS` orders them; `TIGHTENING = ('no_images', 'no_mention')`.
`Person.image_consent` is written **only here and by staff** — never by a submitter, whose
`rights_confirmed` remains their own. Both `portraits` and the profile page hang off this one field,
so revoking is a single write every reader sees at once.

## The asymmetry is the design

A fraudulent `images_ok` is real harm; a fraudulent `no_images` only hides content until staff reject
it. So (`rules.py`):

- `request_claim` mails a link to the mailbox — **never the claimant's note** (relay spam) —
  `MAX_SENT_PER_PERSON_PER_DAY` 3, throttle `claim_request` 3/h; `MailFailed` is a 503, not a
  pretend success.
- `confirm` proves the mailbox (`verified`) and calls `maybe_apply_precaution`: **a tightening wish
  from a mailbox at a `TrustedDomain` applies immediately** (`apply_wish`); everything else waits.
- `decide` is **staff only** — not the trusted tier, because confirming an identity is a different
  power from "hide fast". The queue at `/moderacja/zgody` shows plausibility signals (institutional
  domain, surname in the local part, an existing account, earlier claims).
- `apply_wish`: `no_images` hides the person's posts that carry an image attachment — through
  `archive.people.person_posts_q`, so aliases count, and `HIDEABLE` includes `pending` (public
  tomorrow); `no_mention` hides all of them and sets `is_listed = False`, remembering
  `previous_listed`. Hidden, not deleted: a moderator still decides what a lawful version looks
  like. The `ModerationAction` reason is `HIDE_REASON` („na wniosek osoby, której wpis dotyczy") and
  **never the address**. `revert` undoes precisely the `ConsentHide` rows.
- Withdrawal is as easy as consent (art. 7 ust. 3 RODO): `send_manage_link` to the same mailbox
  (`claim_manage` 3/h), `change_wish` / `withdraw_claim` act at once with no second review — the
  mailbox is the identity.

## Things that must move together

- `CONSENT_TEXT_VERSION` (`'2026-09-19'`) is stamped on every claim. **Change the wording at
  `/ludzie/zgoda` → bump the version**, or an approved row no longer says which text was agreed.
- `WISH_LABELS` ↔ `frontend/src/lib/consent.ts` `WISHES` — labels byte-identical; both files say so.
- `manage.py forget_claim_ips` blanks `requester_ip` after the retention window **except on
  approved rows** — they are the evidence.
- The ✓ badge (`ConsentBadge.svelte`) links to `/ludzie/zgoda`, which explains all of this to the
  person: a badge nobody can look up is a rumour.

## Routes

`/ludzie/[slug]` (the „Jesteś tą osobą?" box), `/ludzie/[slug]/potwierdz` (the mailbox link),
`/ludzie/[slug]/ustawienia` (the manage link), `/ludzie/zgoda` (the explanation), `/moderacja/zgody`
(staff). API under `/api/people/<slug>/claims/…` and `/api/claims/…` — included **before** the
archive router (`config/urls.py`).
