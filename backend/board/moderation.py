"""Reports on shoutbox messages: the crowd's half, and the moderator's half.

Deliberately lighter than `archive/moderation.py` — no nuke tier, no ModerationAction audit
row. The board's whole design is "hide, not delete, no ceremony" (see board/models.py); this
adds exactly one thing that was missing: a way for the community to flag something, and a
consequence for being right or wrong about it.

Two moving parts:

* **Auto-hide** — once `AUTO_HIDE_TRUSTED_REPORTS` distinct *trusted* accounts (confirmed
  institutional address, `accounts.trust.is_trusted`) have reported the same still-visible
  message, it is hidden immediately, `hidden_by=None` — that null is what marks a hide as
  "the reports did this" rather than a moderator's own call (`hidden_by=<user>`). A guest
  report, or a second report from an account that isn't trusted, is still stored (it's a
  signal in the queue) but never moves this counter on its own.

* **Reputation settlement** — a moderator's `hide` or `restore` on a message resolves every
  one of its open reports at once (`_settle_reports`) and marks them upheld or not. Each
  distinct *trusted* reporter's `accounts.models.Profile.reputation` moves +1 (hide: the
  crowd was right) or -1 (restore: it was not) — except the acting moderator's own report,
  if they'd filed one, which counts for nothing: confirming your own flag is not a
  reputation source. Nothing today *gates* on reputation — it is a record, not yet a lever —
  but it is the one built specifically so a pattern of bad-faith reporting becomes visible
  before it has to become a problem.
"""
from django.db import transaction
from django.db.models import F

from accounts.models import Profile
from accounts.trust import is_trusted

from .models import Message, Report, hash_ip

AUTO_HIDE_TRUSTED_REPORTS = 3


class SelfReportError(Exception):
    """Raised when a message's own author tries to report it."""


class DuplicateReportError(Exception):
    """Raised when a signed-in user reports the same message twice."""


def _distinct_trusted_reporters(message):
    """The trusted accounts with a currently-open report on this message, deduplicated."""
    reporters = {r.reporter for r in
                 message.reports.filter(resolved=False, reporter__isnull=False).select_related('reporter__profile')}
    return {u for u in reporters if is_trusted(u)}


@transaction.atomic
def register_report(message, user, ip, reason, note=''):
    """Store one report and, if it just pushed a still-visible message over the trusted
    quorum, hide it. `user` is `request.user` or None for a guest; `ip` is the raw address —
    hashed here exactly like a posted message's is (never stored in the clear)."""
    if user is not None and getattr(user, 'is_authenticated', False) and message.author_id == user.id:
        raise SelfReportError
    if user is not None and getattr(user, 'is_authenticated', False):
        if Report.objects.filter(message=message, reporter=user).exists():
            raise DuplicateReportError
        report = Report.objects.create(message=message, reporter=user, reason=reason, note=note)
    else:
        report = Report.objects.create(message=message, ip_hash=hash_ip(ip or ''), reason=reason, note=note)

    if not message.is_hidden and len(_distinct_trusted_reporters(message)) >= AUTO_HIDE_TRUSTED_REPORTS:
        message.is_hidden = True
        message.hidden_by = None  # None + is_hidden=True: the reports did this, not a moderator
        message.save(update_fields=['is_hidden', 'hidden_by'])
    return report


@transaction.atomic
def settle_reports(message, actor, upheld):
    """Called from the hide/restore endpoints. Resolves every open report on `message`,
    marks each `upheld` (True on hide, False on restore) and moves the reputation of every
    distinct trusted reporter — except `actor`, whose own report (if any) settles but pays
    nothing, so confirming your own flag cannot be a reputation source."""
    open_reports = message.reports.filter(resolved=False)
    reporters = {r.reporter for r in open_reports.select_related('reporter__profile') if r.reporter_id}
    for u in reporters:
        if u.pk == actor.pk or not is_trusted(u):
            continue
        Profile.objects.filter(user=u).update(reputation=F('reputation') + (1 if upheld else -1))
    open_reports.update(resolved=True, upheld=upheld)
