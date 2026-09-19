"""Taking the FILES of escalated / nuked content off the public path.

A row's status only governs what the API returns. The attachment bytes sit under
MEDIA_ROOT, which nginx serves straight from the volume with no auth and a 30-day cache
(frontend/nginx.conf) — and their absolute URLs were in every API response before the
content was escalated or nuked, so anyone who kept a URL, and every cache along the way,
could keep fetching the picture after "nobody can see this" became the rule.

So the moment content is escalated (escalation/services.py) or nuked
(archive/moderation.py) its files are MOVED to EVIDENCE_ROOT/quarantine/<relative path>.
The FileField keeps its name, so the row still knows what it had; the path just stops
resolving under MEDIA_ROOT (a 404, not a picture). A decline or an un-nuke moves them
back. Moves are idempotent both ways — content nuked and then escalated has its files
moved once, and released only when neither state still holds.

Since attachments may live in Cloudflare R2 instead of on local disk, the same move
happens there: the object is copied from the `public/` prefix to `held/` and the original
deleted, so every URL ever handed out stops resolving. The row keeps the new key, so a
release can put it back.

The CDN in front is the third copy and the one this origin does not own. `escalation/cdn.py`
purges it by URL, and says so in the log when it cannot — an edge cache that still serves
a quarantined picture is the failure this module exists to prevent, so it is never assumed
away.
"""
import logging
import shutil
from pathlib import Path

from django.conf import settings

logger = logging.getLogger('security')


def _attachments_of(target):
    manager = getattr(target, 'attachments', None)
    if manager is None or not hasattr(manager, 'all'):
        return []
    return list(manager.all())


def _files_of(target):
    """Local FileFields only — the R2-backed rows are handled by key, not by path."""
    return [att.file for att in _attachments_of(target) if getattr(att, 'file', None)
            and not getattr(att, 'storage_key', '')]


def _remote_of(target):
    return [att for att in _attachments_of(target) if getattr(att, 'storage_key', '')]


def _paths(f):
    live = Path(settings.MEDIA_ROOT) / f.name
    held = Path(settings.EVIDENCE_ROOT) / 'quarantine' / f.name
    return live, held


def _move_remote(target, to_held):
    """R2 half. Returns (moved, purged_urls). Failures are logged and re-raised only for a
    move INTO held: an object that should have left the public prefix and did not is a
    live leak, and the caller (an escalation, inside a transaction) must not commit as if
    it had succeeded. A failed release is merely inconvenient, so it is swallowed."""
    from config import r2

    moved, urls = 0, []
    for att in _remote_of(target):
        key = att.storage_key
        if to_held and r2.is_held(key):
            continue
        if not to_held and not r2.is_held(key):
            continue
        if to_held:
            urls.append(r2.public_url(key))
            att.storage_key = r2.move_to_held(key)
        else:
            try:
                att.storage_key = r2.move_to_public(key)
            except Exception:
                logger.exception('quarantine.release r2 failed key=%s', key)
                continue
        att.save(update_fields=['storage_key'])
        moved += 1
    return moved, urls


def quarantine(target):
    """Move every attachment of `target` off the public path — MEDIA_ROOT for a local file,
    the `public/` prefix for an R2 object — and ask the CDN to forget the URLs. Returns how
    many files moved."""
    n, urls = _move_remote(target, to_held=True)
    if urls:
        from . import cdn
        cdn.purge_urls(urls)
    for f in _files_of(target):
        live, held = _paths(f)
        if not live.is_file():
            continue  # already held, or never written
        held.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.move(str(live), str(held))
        n += 1
    if n:
        logger.info('quarantine.hold target=%s:%s files=%d', type(target).__name__, target.pk, n)
    return n


def release(target):
    """Put the files back, unless something else still says they must stay held."""
    if still_held(target):
        return 0
    n, _ = _move_remote(target, to_held=False)
    for f in _files_of(target):
        live, held = _paths(f)
        if not held.is_file():
            continue
        live.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(held), str(live))
        n += 1
    if n:
        logger.info('quarantine.release target=%s:%s files=%d', type(target).__name__, target.pk, n)
    return n


def read_bytes(f):
    """The bytes of an attachment FileField, from MEDIA_ROOT or — if a nuke already moved
    it — from quarantine. Evidence snapshots use this so escalating nuked content works."""
    live, held = _paths(f)
    for p in (live, held):
        if p.is_file():
            return p.read_bytes()
    raise FileNotFoundError(f.name)


def still_held(target):
    """True while ANY reason to hold the files remains: an active escalation, a nuke
    (`status`/`moderation` == 'nuked'), or a criminal quarantine/purge, which nothing ever
    releases from."""
    from .visibility import is_escalated
    if is_escalated(target):
        return True
    if getattr(target, 'status', None) in ('nuked', 'quarantined', 'purged'):
        return True
    return getattr(target, 'moderation', None) == 'nuked'
