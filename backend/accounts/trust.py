"""Who is trusted, and how an e-mail address earns it.

`is_trusted(user)` is THE answer the archive asks before showing the moderation board:
staff, or a user whose Profile carries a confirmed institutional address whose domain is
still active. `match_domain(email)` is the strict parser behind the confirmation flow.
"""
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator

from .models import Profile, TrustedDomain

# (domain, institution, kind, match_subdomains, is_active)
#
# A STARTING POINT, not a verdict — the owner prunes and extends this in the admin
# (migration 0002 only seeds rows that do not exist yet, so edits there survive).
# `uw.edu.pl` deliberately does NOT match subdomains: that would swallow every unit of the
# university, which is exactly the opposite of "people around FUW". `mimuw.edu.pl` ships
# switched off — a neighbour, not the Faculty.
TRUSTED_DOMAINS_SEED = [
    ('fuw.edu.pl', 'Wydział Fizyki UW', 'fuw', True, True),          # also okwf/igf/… .fuw.edu.pl
    ('uw.edu.pl', 'Uniwersytet Warszawski', 'uw', False, True),       # staff addresses only, no subdomains
    ('student.uw.edu.pl', 'Studenci UW', 'uw', True, True),
    ('cent.uw.edu.pl', 'CeNT UW', 'uw', True, True),
    ('astrouw.edu.pl', 'Obserwatorium Astronomiczne UW', 'uw', True, True),
    ('mimuw.edu.pl', 'MIM UW', 'uw', True, False),                    # off by default
    ('ifpan.edu.pl', 'Instytut Fizyki PAN', 'pan', True, True),
    ('cft.edu.pl', 'Centrum Fizyki Teoretycznej PAN', 'pan', True, True),
    ('camk.edu.pl', 'CAMK PAN', 'pan', True, True),
    ('ncbj.gov.pl', 'NCBJ', 'pan', True, True),
    ('ifpilm.pl', 'IFPiLM', 'pan', True, True),
    ('unipress.waw.pl', 'Instytut Wysokich Ciśnień PAN', 'pan', True, True),
    ('ichf.edu.pl', 'IChF PAN', 'pan', True, True),
    ('ippt.pan.pl', 'IPPT PAN', 'pan', True, True),
]

_email_validator = EmailValidator()


def match_domain(email):
    """The active `TrustedDomain` an address belongs to, or None.

    Strict on purpose — this decides who gets to hide content. Lowercase, exactly one
    '@', nothing with whitespace, quotes or non-ASCII (Django's validator would let a
    quoted local part through), then an exact match, then — only for domains that opt in —
    a suffix match on '.' + domain, longest domain first. So `x@fuw.edu.pl.evil.com`,
    `x@gmail.com@fuw.edu.pl` and `x@evil.com` all come back None."""
    if not isinstance(email, str) or not email:
        return None
    email = email.lower()
    if not email.isascii() or any(c.isspace() for c in email) or '"' in email or "'" in email:
        return None
    if email.count('@') != 1:
        return None
    try:
        _email_validator(email)
    except ValidationError:
        return None
    domain = email.split('@', 1)[1]
    active = list(TrustedDomain.objects.filter(is_active=True))
    for td in active:
        if td.domain == domain:
            return td
    for td in sorted((t for t in active if t.match_subdomains), key=lambda t: -len(t.domain)):
        if domain.endswith('.' + td.domain):
            return td
    return None


def profile_for(user):
    """The user's Profile, created on the spot for accounts older than this app."""
    try:
        return user.profile
    except Profile.DoesNotExist:
        profile, _ = Profile.objects.get_or_create(user=user)
        return profile


def is_trusted(user):
    """Staff, or a confirmed institutional address whose domain is still active.
    Anonymous / None → False. Never raises for a user without a Profile row."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_staff:
        return True
    p = profile_for(user)
    return p.verified_at is not None and p.affiliation_domain is not None and p.affiliation_domain.is_active


def mask_email(email):
    """'jan.kowalski@fuw.edu.pl' → 'j***@fuw.edu.pl' — enough to recognise, not to harvest."""
    if not email or '@' not in email:
        return ''
    local, domain = email.rsplit('@', 1)
    return f'{local[:1]}***@{domain}'


def accepted_institutions():
    """'Wydział Fizyki UW (fuw.edu.pl), …' — for the refusal message and the account page."""
    return ', '.join(f'{t.institution} ({t.domain})' for t in TrustedDomain.objects.filter(is_active=True))
