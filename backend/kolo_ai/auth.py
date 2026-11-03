"""Who is calling a Koło AI endpoint.

Two credentials, neither of them the archive's:

- `Authorization: Kolo <session>` — a member's session, minted by opening a mailed link;
- `Authorization: KoloKey <key>` — a `PublishKey`, which may post and withdraw status
  entries and nothing else.

`request.user` stays anonymous on purpose: a Koło session is not an archive account and must
never satisfy an archive permission. Views read `member_of(request)` / `publish_key_of(request)`.
"""
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import PublishKey, Session, hash_secret


class KoloAuthentication(BaseAuthentication):
    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if len(parts) != 2:
            return None
        scheme, raw = parts[0].decode('latin-1'), parts[1].decode('latin-1')
        if scheme == 'Kolo':
            s = (Session.objects.select_related('member')
                 .filter(key_hash=hash_secret(raw), revoked_at__isnull=True, expires_at__gt=timezone.now()).first())
            if s is None:
                raise AuthenticationFailed('Sesja wygasła. Zaloguj się ponownie.')
            return AnonymousUser(), s
        if scheme == 'KoloKey':
            k = PublishKey.objects.filter(key_hash=hash_secret(raw), revoked_at__isnull=True).first()
            if k is None:
                raise AuthenticationFailed('Nieważny klucz publikacji.')
            return AnonymousUser(), k
        return None

    def authenticate_header(self, request):
        return 'Kolo'


def member_of(request):
    return request.auth.member if isinstance(request.auth, Session) else None


def session_of(request):
    return request.auth if isinstance(request.auth, Session) else None


def publish_key_of(request):
    return request.auth if isinstance(request.auth, PublishKey) else None
