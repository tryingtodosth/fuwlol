"""Destroying every copy of a criminal file — and knowing that it is every copy.

By the time a head-admin confirms a report to Dyżurnet.pl, one uploaded picture may exist
in as many as four places, because each of them was added for a good reason:

1. **Cloudflare R2**, under the `held/` prefix, moved there by `quarantine()`. Or, for a
   post from before R2 or from a bare clone, **MEDIA_ROOT**.
2. **`EVIDENCE_ROOT/quarantine/<path>`** — where the local half of `quarantine()` moves a
   MEDIA_ROOT file so the public path stops resolving.
3. **`EVIDENCE_ROOT/<escalation-id>/<n>_<name>`** — the frozen copy the evidence snapshot
   took so that the head-admin reviews what was captured rather than what is live now.
   (R2-backed attachments have no such copy: `evidence.py` records their hash and key
   instead, precisely so there is one fewer copy to find here.)
4. The CDN's edge copy, which is not ours and is handled by `cdn.purge_urls` at
   quarantine time, not here.

Missing any one of them makes the purge a fiction, and the fiction is the dangerous part:
the audit row would say the material was destroyed while a copy sat under EVIDENCE_ROOT on
the VPS, which is the exact state art. 202 § 4b k.k. punishes.

**The ordering rule.** A database transaction cannot roll back a deleted R2 object, so
there is no arrangement of these steps that is atomic. There is, however, one that is
safe, and `services.confirm_nask_report_and_purge` follows it:

    write the audit rows and commit  →  destroy the bytes  →  mark purged and commit

A crash after the first commit leaves a report on record whose bytes may still exist — an
incomplete purge, which is visible, retryable, and fixed by running the action again. The
opposite order would leave destroyed bytes with no record of what was destroyed or why,
which nothing can repair. When in doubt, this module would rather leave a file and shout
than delete one quietly.
"""
import logging
import os
from pathlib import Path

from django.conf import settings

logger = logging.getLogger('security')


class ShredIncomplete(RuntimeError):
    """At least one copy could not be destroyed or could not be proven gone. Carries the
    per-copy detail so the head-admin sees what is still out there, not just 'failed'."""

    def __init__(self, failures):
        self.failures = failures
        super().__init__('; '.join(failures))


def _manifest_files(escalation):
    from .nask import manifest_for
    return manifest_for(escalation).get('files', [])


def collect(escalation, target):
    """One record per binary that has to die, merged from the frozen manifest (the
    authority on what was captured) and the live attachment rows (the authority on where
    the object sits *now*, since quarantine rewrote the key).

    Matching is by sha256 where both sides have one, and falls back to position — a post
    whose attachments were somehow edited between capture and purge still gets every live
    row shredded, because the fallback adds rows rather than dropping them."""
    live = list(getattr(target, 'attachments', None).all()) if hasattr(target, 'attachments') else []
    by_hash = {a.sha256: a for a in live if getattr(a, 'sha256', '')}
    seen_live = set()
    records = []

    for i, f in enumerate(_manifest_files(escalation)):
        sha = f.get('sha256', '')
        att = by_hash.get(sha)
        if att is None and i < len(live) and live[i].pk not in seen_live:
            # Positional fallback, and it must not be conditional on the manifest lacking a
            # hash: a locally stored attachment has a hash in the MANIFEST (computed from
            # the bytes at capture) and an empty `sha256` on the ROW, so hash matching
            # fails for exactly the files that most need matching. Without this the same
            # file is collected twice — once with no row, once from the sweep below — and
            # one destroyed file produces two audit rows.
            att = live[i]
        if att is not None:
            seen_live.add(att.pk)
        records.append({
            'attachment': att,
            'sha256': sha or (getattr(att, 'sha256', '') if att else ''),
            'original_name': f.get('name', '') or (getattr(att, 'original_name', '') if att else ''),
            'size_bytes': f.get('size', 0) or (getattr(att, 'size_bytes', 0) if att else 0),
            'storage_key': (getattr(att, 'storage_key', '') if att else '') or f.get('storage_key', ''),
            'local_name': (att.file.name if att is not None and getattr(att, 'file', None)
                           and not getattr(att, 'storage_key', '') else ''),
            'evidence_copy': f.get('stored_as', ''),
        })

    # Anything live that the manifest did not describe (an attachment added after capture)
    # still has to go: it hangs off content being purged as criminal.
    for att in live:
        if att.pk in seen_live:
            continue
        records.append({
            'attachment': att, 'sha256': getattr(att, 'sha256', ''),
            'original_name': att.original_name, 'size_bytes': getattr(att, 'size_bytes', 0),
            'storage_key': getattr(att, 'storage_key', ''),
            'local_name': att.file.name if getattr(att, 'file', None) and not getattr(att, 'storage_key', '') else '',
            'evidence_copy': '',
        })
    return records


def _unlink(path: Path, failures, label):
    try:
        if path.is_file():
            os.chmod(path, 0o600)  # evidence copies are written 0o400 in a 0o500 directory
            path.unlink()
        if path.exists():
            failures.append(f'{label}: {path} still exists')
    except OSError as exc:
        failures.append(f'{label}: {path} ({exc})')


def destroy(escalation, records):
    """Delete every copy named in `records`. Raises `ShredIncomplete` listing what survived.

    Deliberately keeps going after the first failure: a head-admin needs the full list of
    what is still out there, and a partial shred that stopped early would leave more."""
    from config import r2

    failures = []
    evidence_dir = Path(settings.EVIDENCE_ROOT) / str(escalation.pk)
    if evidence_dir.is_dir():
        try:
            os.chmod(evidence_dir, 0o700)
        except OSError as exc:
            failures.append(f'evidence dir: {evidence_dir} ({exc})')

    for rec in records:
        key = rec.get('storage_key')
        if key:
            if not r2.is_configured():
                failures.append(f'r2: {key} (R2 is not configured — cannot delete)')
            else:
                try:
                    r2.delete_object(key)
                    if r2.exists(key):
                        failures.append(f'r2: {key} still exists after delete')
                except Exception as exc:
                    failures.append(f'r2: {key} ({exc})')

        if rec.get('local_name'):
            _unlink(Path(settings.MEDIA_ROOT) / rec['local_name'], failures, 'media')
            _unlink(Path(settings.EVIDENCE_ROOT) / 'quarantine' / rec['local_name'], failures, 'quarantine')

        if rec.get('evidence_copy'):
            _unlink(evidence_dir / rec['evidence_copy'], failures, 'evidence')

    if failures:
        logger.error('shred.incomplete escalation=%s failures=%s', escalation.pk, failures)
        raise ShredIncomplete(failures)

    logger.warning('shred.complete escalation=%s files=%d', escalation.pk, len(records))
    return len(records)


def strip_attachment_rows(records):
    """Blank every field that pointed at bytes, and keep the row.

    The row is a tombstone on purpose (house rule: a thread that references an attachment
    must not break): the post still knows it had six files and what they were called, and
    the body's `![](zdjecie.jpg)` reference still resolves to a row that renders as a
    removed file rather than to nothing at all. `sha256` stays too — it is metadata about a
    file that no longer exists, it is in the NASK report already, and it is what lets a
    later question about this row be answered without the file."""
    for rec in records:
        att = rec.get('attachment')
        if att is None:
            continue
        # Field-by-field rather than a fixed list: a Post's Attachment carries the R2
        # columns and a Comment's CommentAttachment does not, and the criminal path covers
        # both — an attachment on a comment is the same offence as one on a post. Naming
        # columns that only one of them has would make a comment purge raise at the very
        # last step, after the bytes were already destroyed.
        fields = []
        for name, blank in (('file', ''), ('storage_key', ''), ('size_bytes', 0), ('content_type', '')):
            if any(f.name == name for f in att._meta.fields):
                setattr(att, name, blank)
                fields.append(name)
        if fields:
            att.save(update_fields=fields)
