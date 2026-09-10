"""Who may hide a message.

Trusted = `accounts.trust.is_trusted(user)`. That module is being written in parallel
with this app, so the import is lazy and its absence is not an error: until it lands,
"trusted" means `is_staff`. The fallback exists for build order only — once
`accounts.trust` is on disk this asks it, and staff keep the power either way.
"""


def can_moderate(user) -> bool:
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_staff:
        return True
    try:
        from accounts.trust import is_trusted
    except ImportError:
        return False  # build-order fallback: staff only, and staff already returned True
    try:
        return bool(is_trusted(user))
    except Exception:
        return False
