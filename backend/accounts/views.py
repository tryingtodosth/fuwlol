"""Register / login / logout / me, plus the institutional-address confirmation that turns
an ordinary account into a `trusted` one (see accounts/models.py for the two tiers).
Plain username + password, DRF tokens. The login field accepts a username or an email;
the throttle keys on IP."""
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import EmailVerification, Profile, TrustedDomain
from .trust import accepted_institutions, is_trusted, mask_email, match_domain, profile_for


class UserSerializer(serializers.ModelSerializer):
    is_trusted = serializers.SerializerMethodField()
    affiliation = serializers.SerializerMethodField()
    pending_verification = serializers.SerializerMethodField()

    reputation = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'is_staff', 'is_superuser', 'date_joined',
                  'is_trusted', 'affiliation', 'pending_verification', 'reputation']
        read_only_fields = fields

    def get_is_trusted(self, user):
        return is_trusted(user)

    def get_reputation(self, user):
        return profile_for(user).reputation

    def get_affiliation(self, user):
        """The confirmed institution, or null. Shown even if the domain has since been
        deactivated — `is_trusted` is the field that says whether it still counts."""
        p = profile_for(user)
        if p.verified_at is None or p.affiliation_domain is None:
            return None
        return {'institution': p.affiliation_domain.institution, 'domain': p.affiliation_domain.domain,
                'email_masked': mask_email(p.affiliation_email), 'verified_at': p.verified_at}

    def get_pending_verification(self, user):
        v = _valid_verifications().filter(user=user).first()
        return mask_email(v.email) if v else None


class RegisterSerializer(serializers.Serializer):
    username = serializers.RegexField(r'^[a-zA-Z0-9_.-]{3,30}$', error_messages={
        'invalid': 'Nazwa: 3–30 znaków, litery, cyfry, . _ -'})
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)

    def validate_username(self, v):
        if User.objects.filter(username__iexact=v).exists():
            raise serializers.ValidationError('Ta nazwa jest już zajęta.')
        return v

    def validate_email(self, v):
        if v and User.objects.filter(email__iexact=v).exists():
            raise serializers.ValidationError('Ten e-mail jest już użyty.')
        return v

    def validate_password(self, v):
        try:
            validate_password(v)
        except ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return v

    def create(self, data):
        return User.objects.create_user(data['username'], data.get('email', ''), data['password'])


def _payload(user):
    token, _ = Token.objects.get_or_create(user=user)
    return {'token': token.key, 'user': UserSerializer(user).data}


class RegisterView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'register'

    def post(self, request):
        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(_payload(s.save()), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        ident = (request.data.get('username') or '').strip()
        password = request.data.get('password') or ''
        if '@' in ident:
            u = User.objects.filter(email__iexact=ident).first()
            ident = u.username if u else ident
        user = authenticate(request, username=ident, password=password)
        if user is None:
            return Response({'detail': 'Zła nazwa lub hasło.'}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(_payload(user))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


# --- institutional-address confirmation -------------------------------------------------

def _valid_verifications():
    return EmailVerification.objects.filter(used_at__isnull=True,
                                            created_at__gt=timezone.now() - EmailVerification.VALID_FOR)


def _taken_by_someone_else(email, user):
    """One institutional address confirms one account — otherwise a single FUW mailbox
    could mint any number of trusted accounts."""
    return Profile.objects.filter(affiliation_email__iexact=email, verified_at__isnull=False).exclude(user=user).exists()


class VerifyRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyRequestView(APIView):
    """POST {email} → 202 {sent_to}. Sends the confirmation link; a new request replaces
    the user's older unused ones."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'verify'

    def post(self, request):
        s = VerifyRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        email = s.validated_data['email'].strip().lower()
        domain = match_domain(email)
        if domain is None:
            raise serializers.ValidationError({'email': [
                'Ten adres nie należy do uznawanej instytucji. Akceptujemy adresy: ' + accepted_institutions() + '.']})
        if _taken_by_someone_else(email, request.user):
            raise serializers.ValidationError({'email': ['Ten adres został już potwierdzony na innym koncie.']})
        with transaction.atomic():
            EmailVerification.objects.filter(user=request.user, used_at__isnull=True).delete()
            v = EmailVerification.objects.create(user=request.user, email=email)
        link = f'{settings.FUWLOL_SITE_URL}/potwierdz?token={v.token}'
        body = (f'Cześć {request.user.username},\n\n'
                f'Kliknij, aby potwierdzić adres {email} na fuw.lol:\n\n{link}\n\n'
                f'Potwierdzony adres z instytucji „{domain.institution}” daje dostęp do tablicy moderacji '
                f'archiwum (ukrywanie i przywracanie wpisów) i publikuje Twoje wpisy bez kolejki.\n\n'
                f'Link działa 24 godziny i tylko raz. Jeśli to nie Ty — zignoruj tę wiadomość.\n')
        try:
            send_mail('fuw.lol — potwierdź adres', body, settings.DEFAULT_FROM_EMAIL, [email])
        except Exception:  # SMTP down: say so, and do not leave a link nobody received
            v.delete()
            return Response({'detail': 'Nie udało się wysłać wiadomości. Spróbuj ponownie później.'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({'sent_to': mask_email(email)}, status=status.HTTP_202_ACCEPTED)


class VerifyConfirmView(APIView):
    """POST {token} → {ok, is_trusted, institution}. AllowAny: the link may well be opened
    in a browser where nobody is logged in — the token is the secret, not the session."""
    permission_classes = [AllowAny]

    def post(self, request):
        token = (request.data.get('token') or '').strip()
        v = _valid_verifications().filter(token=token).select_related('user').first() if token else None
        if v is None:
            return Response({'detail': 'Link wygasł lub został już użyty.'}, status=status.HTTP_400_BAD_REQUEST)
        domain = match_domain(v.email)  # re-checked: the domain may have been switched off since the mail went out
        if domain is None:
            return Response({'detail': 'Ten adres nie należy już do uznawanej instytucji.'}, status=status.HTTP_400_BAD_REQUEST)
        if _taken_by_someone_else(v.email, v.user):
            return Response({'detail': 'Ten adres został już potwierdzony na innym koncie.'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            p = profile_for(v.user)
            p.affiliation_email, p.affiliation_domain, p.verified_at = v.email, domain, timezone.now()
            p.save(update_fields=['affiliation_email', 'affiliation_domain', 'verified_at'])
            v.used_at = timezone.now()
            v.save(update_fields=['used_at'])
        return Response({'ok': True, 'is_trusted': is_trusted(v.user), 'institution': domain.institution})


class TrustedDomainsView(APIView):
    """Public: which institutions qualify, so the account page can say so."""
    permission_classes = [AllowAny]

    def get(self, request):
        return Response([{'domain': t.domain, 'institution': t.institution, 'kind': t.kind}
                         for t in TrustedDomain.objects.filter(is_active=True)])
