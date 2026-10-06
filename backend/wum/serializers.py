"""Reading and writing the three tables. Refusals are Polish sentences keyed by FIELD NAME, like
`feedback/`: the caller (MedApp, trilingual) keys its own translated message off the field and
falls back to the sentence — `src/lib/api/wum.ts` in the medapp repository is the other half.

Two refusals are **409**, not 400, because they mean "the world moved", not "you typed it wrong":
a `consent_text_version` the server no longer shows, and a `payload_version` it no longer
understands. The app's answer to either is "refresh / update the app", and a 400 would make it
look like the person's input.
"""
import re

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import APIException

from . import rules
from .models import (NAME_MAX, PAYLOAD_VERSION, PHONE_MAX, Publication, Template, WumProfile)

# Same shape as the archive's own usernames (`accounts/views.py` RegisterSerializer), so one rule
# covers both populations and a collision is a collision. MIRRORED in MedApp `src/lib/api/wum.ts`
# USERNAME_RE.
USERNAME_RE = r'^[a-zA-Z0-9_.-]{3,30}$'
USERNAME_MESSAGE = 'Nazwa: 3–30 znaków, litery, cyfry, . _ -'
# A language tag like `pl`, `en`, `pt-BR`. Same regex as feedback's, but here it REFUSES: a
# template's language is a fact the app shows, not a hidden field.
LOCALE_RE = re.compile(r'^[a-z]{2}(-[A-Za-z]{2})?$')
AGREE_MESSAGE = 'Bez zaznaczenia oświadczenia nie możemy tego zrobić.'


class Moved(APIException):
    """409 with the body keyed by the field that moved, so the app can name it."""
    status_code = 409

    def __init__(self, field, sentence):
        super().__init__({field: [sentence]})


class StaleConsentText(Moved):
    def __init__(self):
        super().__init__('consent_text_version', 'Treść oświadczenia się zmieniła — odśwież aplikację.')


class StalePayloadVersion(Moved):
    def __init__(self):
        super().__init__('payload_version', 'Aplikacja wysyła rekord w wersji, której serwer nie zna — zaktualizuj ją.')


def _agree(value):
    if value is not True:
        raise serializers.ValidationError(AGREE_MESSAGE)
    return True


# --- accounts ---------------------------------------------------------------------------------

class ProfileSerializer(serializers.ModelSerializer):
    """The four optional fields the person may say about themselves. Nothing else on the profile
    is writable through the API."""
    class Meta:
        model = WumProfile
        fields = ['first_name', 'surname', 'contact_email', 'contact_phone']
        extra_kwargs = {
            'first_name': {'error_messages': {'max_length': f'Najwyżej {NAME_MAX} znaków.'}},
            'surname': {'error_messages': {'max_length': f'Najwyżej {NAME_MAX} znaków.'}},
            'contact_email': {'error_messages': {'invalid': 'To nie wygląda na adres e-mail.'}},
            'contact_phone': {'error_messages': {'max_length': f'Najwyżej {PHONE_MAX} znaków.'}},
        }


def account_row(user):
    """What the app shows under "your account" and stores beside the token. Includes the id of
    the live publication so the publish screen can say "published" without a second call."""
    profile = user.wum_profile
    live = Publication.objects.filter(account=user, status='published').order_by('-created_at').first()
    return {
        'username': user.username,
        'first_name': profile.first_name,
        'surname': profile.surname,
        'contact_email': profile.contact_email,
        'contact_phone': profile.contact_phone,
        'created_at': profile.created_at,
        'agreed_text_version': profile.agreed_text_version,
        'live_publication': str(live.public_id) if live else None,
        'publications_total': Publication.objects.filter(account=user).count(),
    }


class RegisterSerializer(serializers.Serializer):
    username = serializers.RegexField(USERNAME_RE, error_messages={
        'invalid': USERNAME_MESSAGE, 'required': USERNAME_MESSAGE, 'blank': USERNAME_MESSAGE})
    password = serializers.CharField(write_only=True, error_messages={
        'required': 'Podaj hasło.', 'blank': 'Podaj hasło.'})
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=NAME_MAX,
                                       error_messages={'max_length': f'Najwyżej {NAME_MAX} znaków.'})
    surname = serializers.CharField(required=False, allow_blank=True, max_length=NAME_MAX,
                                    error_messages={'max_length': f'Najwyżej {NAME_MAX} znaków.'})
    contact_email = serializers.EmailField(required=False, allow_blank=True,
                                           error_messages={'invalid': 'To nie wygląda na adres e-mail.'})
    contact_phone = serializers.CharField(required=False, allow_blank=True, max_length=PHONE_MAX,
                                          error_messages={'max_length': f'Najwyżej {PHONE_MAX} znaków.'})
    # The person ticked "I have read this and I am not entering real health data". Required, and
    # required to be true: an account without it was not agreed to.
    agree = serializers.BooleanField(error_messages={'required': AGREE_MESSAGE})
    consent_text_version = serializers.CharField(error_messages={
        'required': 'Brak wersji oświadczenia.', 'blank': 'Brak wersji oświadczenia.'})
    # Honeypot, as on the board and in feedback: a real app leaves it empty.
    website = serializers.CharField(required=False, allow_blank=True)

    def validate_website(self, value):
        if (value or '').strip():
            raise serializers.ValidationError('Spam?')
        return ''

    def validate_username(self, value):
        # Across BOTH populations: a WUM username that an archive account already holds is taken.
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('Ta nazwa jest już zajęta.')
        return value

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def validate_agree(self, value):
        return _agree(value)

    def validate_consent_text_version(self, value):
        if value != rules.WUM_ACCOUNT_TEXT_VERSION:
            raise StaleConsentText()
        return value

    def create(self, data):
        with transaction.atomic():
            # `email` stays blank on the User — see models.py. The contact address, if any, is on
            # the profile, where it is the person's contact and not a login.
            user = User.objects.create_user(data['username'], '', data['password'])
            WumProfile.objects.create(
                user=user,
                first_name=data.get('first_name', '').strip(),
                surname=data.get('surname', '').strip(),
                contact_email=data.get('contact_email', '').strip(),
                contact_phone=data.get('contact_phone', '').strip(),
                agreed_text_version=data['consent_text_version'],
            )
        return user


# --- templates --------------------------------------------------------------------------------

class TemplateListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Template
        fields = ['slug', 'title', 'locale', 'summary', 'updated_at']
        read_only_fields = fields


class TemplateDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Template
        fields = ['slug', 'title', 'locale', 'summary', 'document', 'document_version', 'updated_at']
        read_only_fields = fields


class TemplateWriteSerializer(serializers.ModelSerializer):
    """Staff only (views.py). `document` goes through `rules.template_problems` here and in the
    admin form — the same function, so the two write paths cannot drift."""
    class Meta:
        model = Template
        fields = ['slug', 'title', 'locale', 'summary', 'document', 'status']
        extra_kwargs = {
            'slug': {'error_messages': {'invalid': 'Slug: litery, cyfry, myślniki.',
                                        'unique': 'Szablon o tym slugu już istnieje.'}},
            'title': {'error_messages': {'blank': 'Podaj tytuł.', 'required': 'Podaj tytuł.'}},
        }

    def validate_locale(self, value):
        value = (value or '').strip()
        if not LOCALE_RE.match(value):
            raise serializers.ValidationError('Język: kod jak „pl”, „en” albo „pt-BR”.')
        return value

    def validate_document(self, value):
        problems = rules.template_problems(value)
        if problems:
            raise serializers.ValidationError(problems)
        return value


# --- publications -----------------------------------------------------------------------------

class PublicationPublicSerializer(serializers.ModelSerializer):
    """What anybody may read. `id` is the opaque uuid; there is no `account`, no username, no
    day — and no field can be added here without re-reading models.py's docstring first."""
    id = serializers.UUIDField(source='public_id', read_only=True)
    published_month = serializers.CharField(read_only=True)

    class Meta:
        model = Publication
        fields = ['id', 'payload', 'payload_version', 'published_month']
        read_only_fields = fields


class PublicationMineSerializer(serializers.ModelSerializer):
    """The person's own rows, every status — so the app can show "withdrawn on …"."""
    id = serializers.UUIDField(source='public_id', read_only=True)

    class Meta:
        model = Publication
        fields = ['id', 'status', 'payload_version', 'consent_text_version', 'created_at', 'withdrawn_at']
        read_only_fields = fields


class PublishSerializer(serializers.Serializer):
    payload = serializers.JSONField(error_messages={'required': 'Brak rekordu.'})
    payload_version = serializers.CharField(error_messages={
        'required': 'Brak wersji rekordu.', 'blank': 'Brak wersji rekordu.'})
    consent_text_version = serializers.CharField(error_messages={
        'required': 'Brak wersji oświadczenia.', 'blank': 'Brak wersji oświadczenia.'})
    agree = serializers.BooleanField(error_messages={'required': AGREE_MESSAGE})

    def validate_payload_version(self, value):
        if value != PAYLOAD_VERSION:
            raise StalePayloadVersion()
        return value

    def validate_consent_text_version(self, value):
        if value != rules.WUM_PUBLISH_TEXT_VERSION:
            raise StaleConsentText()
        return value

    def validate_agree(self, value):
        return _agree(value)

    def validate(self, data):
        problems = rules.payload_problems(data['payload'], data['payload_version'])
        if problems:
            raise serializers.ValidationError({'payload': problems})
        return data
