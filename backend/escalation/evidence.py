"""Freezing what an escalation is about, once, before anything about it can change.

The whole point of reporting to a national authority is that the evidence outlives the
live content: the author might delete their account, a moderator might restore the
message, an attachment might be replaced. So `snapshot_target` runs INSIDE the same
transaction that creates the `Escalation` row (services.py) and never reads the target
again afterwards — everything downstream (the head-admin's review, the eventual NASK
package) comes from these frozen bytes, not from a live query.

Files are copied — not referenced — into `EVIDENCE_ROOT/<escalation-id>/`, a directory
outside `MEDIA_ROOT` that no view ever serves by path (see EscalationEvidenceFileView).
Read-only permissions are set immediately after writing, and the whole package (manifest +
every file's bytes) is hashed so a later dispute about what was captured has an answer.
"""
import hashlib
import json
import os
import shutil
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .quarantine import read_bytes


def _user_info(user):
    if user is None:
        return None
    return {'id': user.id, 'username': user.username, 'email': user.email,
           'date_joined': str(user.date_joined)}


def _describe(target):
    """Duck-typed on purpose: this module never imports archive/board's models, so the
    escalation app stays a leaf nothing else has to depend on."""
    kind = type(target).__name__
    base = {'kind': kind, 'pk': target.pk, 'created_at': str(getattr(target, 'created_at', ''))}
    if kind == 'Post':
        base.update(title=target.title, body=target.body, format=target.format,
                    status=target.status, submitted_by=_user_info(target.submitted_by),
                    catalog_no=target.catalog_no)
    elif kind == 'Comment':
        base.update(body=target.body, format=target.format, post_id=target.post_id,
                    author=_user_info(target.author))
    elif kind == 'Message':
        base.update(nick=target.nick, body=target.body, format=target.format,
                    author=_user_info(target.author), ip_hash=target.ip_hash)
    else:
        raise ValueError(f'escalation: no evidence description for {kind!r}')
    return base


def _attachment_files(target):
    for rel in ('attachments',):
        manager = getattr(target, rel, None)
        if manager is not None and hasattr(manager, 'all'):
            for att in manager.all():
                f = getattr(att, 'file', None)
                if f:
                    yield f


def snapshot_target(escalation, target):
    """Writes EVIDENCE_ROOT/<escalation.pk>/manifest.json plus a copy of every attachment,
    all read-only. Returns the sha256 hex digest of the whole package. Cleans up after
    itself and re-raises if anything goes wrong partway — `services.create_escalation`
    runs this inside a transaction, so a failed snapshot must never leave a half-written
    Escalation row behind."""
    evidence_dir = Path(settings.EVIDENCE_ROOT) / str(escalation.pk)
    try:
        evidence_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        data = _describe(target)
        data['captured_at'] = str(timezone.now())
        hasher = hashlib.sha256()
        files_meta = []
        for i, f in enumerate(_attachment_files(target)):
            safe_name = f'{i}_{Path(f.name).name}'
            dest = evidence_dir / safe_name
            content = read_bytes(f)
            dest.write_bytes(content)
            os.chmod(dest, 0o400)
            file_hash = hashlib.sha256(content).hexdigest()
            hasher.update(file_hash.encode())
            files_meta.append({'name': f.name, 'stored_as': safe_name, 'sha256': file_hash})
        data['files'] = files_meta
        manifest = json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2).encode()
        hasher.update(manifest)
        manifest_path = evidence_dir / 'manifest.json'
        manifest_path.write_bytes(manifest)
        os.chmod(manifest_path, 0o400)
        os.chmod(evidence_dir, 0o500)
        return hasher.hexdigest()
    except Exception:
        shutil.rmtree(evidence_dir, ignore_errors=True)
        raise
