# portraits — the profile photo is elected

Once a person's `image_consent` is `granted` (written by the `consent` app or staff, never here),
logged-in users may add photographs of them and vote; the published portrait with the most votes is
the profile photo on `/ludzie/<slug>`, replacing the faculty silhouette. Reasoning: `DESIGN.md`
"Portraits". 31 tests. All rules in `rules.py`; the views ask it.

## Rules

- **Consent gates everything, and is re-checked on every read.** `consent_granted(person)` for
  upload and vote; `visible_q` requires the person's consent to *still* be `granted` **for
  everybody, staff included** — withdrawing consent empties the gallery at the next request without
  deleting anything, which is what makes the consent switch a single write.
- **One vote per user per person**, movable and toggleable (`cast_vote`; `PortraitVote` unique on
  portrait + user). The election: most votes, **tie → the older** (`SORT_ORDERS['votes']` =
  `-vote_count, created_at, id`); `current_portrait(person)` is the one function that answers "which
  photo", and `share/previews.py` asks it too.
- **Trusted uploads publish at once**, everybody else's wait in `/moderacja/portrety`
  (`initial_status` via `can_moderate`) — a confirmed member of the faculty adding a photograph to a
  colleague's page is the case the queue exists to filter *for*.
- `status` `pending|published|rejected|hidden`; `moderate` maps decisions `publish|reject|hide|
  restore` through `DECISION_TARGET`; every transition writes a `PortraitAction` with the previous
  status, never edited.
- Files go through `archive.validators.validate_upload` and lose EXIF like any attachment; `sha256`
  is of the stored bytes; the uploader's own `rights_confirmed` is required.
- Refusals carry their reason: `upload_block_reason` / `vote_block_reason` return the sentence the
  frontend shows (consent missing → a link to `CONSENT_PAGE` `/ludzie/zgoda`).
- Caps: `MAX_PENDING_PER_UPLOADER` 3, `MAX_PUBLISHED_PER_PERSON` 100; paging `DEFAULT_LIMIT` 12,
  `MAX_LIMIT` 60; throttles `portrait_upload` 10/h, `portrait_vote` 60/h.

## Mirrors

`frontend/src/lib/portraits.ts` repeats the statuses, decisions, sort keys (`votes|new|old`) and
`CONSENT_PAGE`; the queue filter adds `all`. Change a value in `rules.py`, change it there.

## Not built

An escalation path for a portrait, a direct-to-R2 upload path, a per-photo report button — today
the person's own consent entry is the door. Named in `PRODUCT.md` "Left open".

## Routes

`/api/people/<slug>/portraits/` (GET gallery, POST upload), `/api/portraits/<pk>/vote/`,
`/api/portraits/<pk>/moderate/`, `/api/portraits/queue/` — included **before** the archive router.
`manage.py seed_portraits` makes development data.
