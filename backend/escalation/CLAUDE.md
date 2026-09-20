# escalation — reporting to NASK, and the one state in which staff means nothing

The argument — why a civil takedown keeps the file and a criminal one destroys it, and why the purge
happens in the order it does — is `LEGAL.md` §6–7. This file is the engineering that argument forces.
`MODERATION-API.md` documents the endpoints; 71 tests in `tests.py`, `test_hardening.py`,
`test_purge.py`.

## The rows

- `Escalation`: a `GenericForeignKey` target (a `Post`, a `Comment` or a `board.Message`),
  `requested_by` (PROTECT — the record must outlive the account), a **mandatory** `reason`,
  `status` `pending|approved|declined|purged` (`ACTIVE_STATUSES` = pending, approved),
  `target_previous_status`, `evidence_ref` (one sha256 over the frozen package),
  `reported_to_nask_at`, `nask_case_reference`, `purged_at`. One pending escalation per target
  (conditional unique constraint). `Meta.permissions` declares `can_manage_critical_quarantine`.
- `EvidenceAuditLog`: **append-only** — `save()` on an existing row raises, `delete()` always
  raises. One row per destroyed **file**: sha256, storage location, original name, size, uploader
  IP and user-agent, upload time, who reported, when, the Dyżurnet reference. None of it is the
  material; all of it is what an investigator asks for. Head-admin only — it holds addresses.

## Who is head-admin

`visibility.is_head_admin(user)` — `is_superuser` **or** the grantable
`escalation.can_manage_critical_quarantine`, so "as few people as possible" can be two people
without the second getting the keys to everything else. `permissions.IsHeadAdmin` answers 403
**before any lookup**. A trusted student volunteering to moderate a meme archive must not acquire
art. 202 § 4a/b exposure by volunteering: nothing here is ever widened to staff.

## Escalate (`services.create_escalation`)

A trusted user or staff presses 🚨 with a reason. In **one transaction**: the `Escalation` row;
`evidence.snapshot_target` — manifest (content, author, e-mail, dates, `ip_hash`) plus copies of the
files, `chmod 400`, the package hash into `evidence_ref` — because the author may delete the account
or a moderator may restore the message before anybody looks; `quarantine.quarantine` **moves** the
live files out of `/media` into `EVIDENCE_ROOT/quarantine/` (or from R2's `public/` prefix to
`held/` in the **separate private** quarantine bucket — a custom domain publishes a whole bucket,
measured); `cdn.purge_urls` evicts the edge copies (logs, never lies, when unconfigured); a `Post`
gets `status = quarantined` with its previous status remembered. A line goes to the `security`
logger. From that instant:

- `Post.objects` no longer returns it; comments and messages are filtered through
  `visibility.active_escalation_ids` / `is_escalated`, which **fails closed**;
- lists, detail, RSS, the moderation board and the Django admin
  (`adminmixin.HideEscalatedMixin` on every target's `ModelAdmin`) all lose it;
- hide / restore / nuke / moderate / delete answer 403 or 404 (`archive.moderation.require_not_escalated`,
  `board`'s hide view);
- a second escalation attempt is **404, not "already escalated"** — no oracle below head-admin.

## Decide (`services.decide_escalation`)

`approve`: the package is complete; the content stays invisible and the files stay held; **a human
forwards it through Dyżurnet.pl** — the application never contacts an institution
(`nask.build_package` / `render_text` assemble what their form asks for, from the *frozen* manifest,
as JSON and as Polish text; any `preview_url` is a presigned GET that dies after
`config/r2.PREVIEW_TTL_SECONDS` = 300 s). `decline`: back to ordinary moderation — the previous
status returns, `quarantine.release` moves the files back **only when nothing else holds them** (a
nuke does). A decided row cannot be decided again (400).

## Purge (`services.confirm_nask_report_and_purge`) — the one irreversible action

Refuses unless the row is `approved` (400) and unless `confirmed_dispatch` is explicitly true
(400): calling the endpoint is not itself the statement "I have sent it to NASK". Then, in this
order and only this order:

1. `EvidenceAuditLog` rows are written and **committed** (`shred.collect` gathers every copy first);
2. `shred.destroy` deletes every copy — the R2 object, the `MEDIA_ROOT` file, the quarantine copy,
   the frozen evidence copy — and `strip_attachment_rows` blanks the file fields;
3. the row becomes `purged`, `Post.status` too.

A database transaction cannot roll back a deleted R2 object, so the ordering is chosen instead of
pretending to be atomic. A crash in the middle leaves an incomplete purge — visible, retryable,
finished by running the action again (audit rows are not duplicated). A shred that leaves copies
answers **409 `{detail, failures}`**, never a silent success: an audit row saying the material was
destroyed while a copy sits on the VPS is exactly the state the statute punishes.

**The storage must cooperate**: the R2 buckets have versioning OFF and no retention lifecycle
(`.env.example`), or the hard delete is not a delete.

## Adding a new kind of target, or a new place content is listed

Comments and chat messages have no status to project onto and are governed by the `Escalation`
row alone — the criminal path is not Post-only, because an attachment on a comment is the same
offence and the same duty. Anything new that shows user content must: filter through
`active_escalation_ids` / `is_escalated`; mix in `HideEscalatedMixin` in the admin; call
`require_not_escalated` before any moderation action; and, if it has files, be reachable by
`quarantine`, `shred.collect` and `evidence._attachments`. `share/previews.py` already asks
`can_see_post` and gets the generic card. `test_hardening.py` is where the 19.09 closures live
(private `held/` bucket, CDN purge, grantable permission, five-minute previews) — extend it rather
than starting a fourth file.

## Frontend

`/eskalacje` (head-admin nav shows „NASK (n)"); the confirm dialog (`lib/dialog.svelte.ts`) refuses
to enable its button until a reason is typed; evidence files are fetched with `api.ts`'s
`downloadBlob` because a plain link cannot carry the token. `types.ts` `EscalationStatus` lists
pending / approved / declined only. **Left open:** `/api/auth/me/` exposes `is_superuser` but not
the grantable permission, and `auth.svelte.ts` `isHeadAdmin` reads `is_superuser` — a head-admin by
permission alone has the API and not the nav entry. `npm run e2e:escalation` drives the whole path from the click
to the decline.
