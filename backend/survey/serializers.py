"""Writing one answer sheet, and withdrawing one. There is no read serializer: sheets are read
in the Django admin and exported by `manage.py export_survey`.

Two kinds of field, and they fail differently — the same arrangement as `feedback/`:

- `survey`, `version`, `consent_version`, `answers`, the honeypot, and the two opt-ins the person
  typed or ticked themselves (`contact_email`, `wants_key`) ARE the submission; a problem with any
  of them is a 400 keyed by the field's NAME, because the client (MedApp, trilingual) keys its own
  translated message off that name and only falls back to the Polish sentence sent here.
  `survey`, `version` and `consent_version` are what the person fixes by reloading; `answers` is
  what the client's own form logic should never have let through; a malformed e-mail is refused
  rather than dropped, because silently losing the one channel the person asked for would be
  worse than a sentence.
- `locale` and `duration_s` are bookkeeping. They NEVER refuse a sheet: a malformed one is
  dropped to `''` / `null` and the answers are kept. A questionnaire takes a quarter of an hour;
  losing it over a timer or a language tag is the one failure this endpoint cannot have.
"""
from rest_framework import serializers

from . import rules

NOT_A_SURVEY = 'Nieznana ankieta.'
STALE_VERSION = 'Ta wersja ankiety jest nieaktualna — odśwież stronę i spróbuj ponownie.'
STALE_CONSENT = 'Treść zgody się zmieniła — odśwież stronę i zaznacz ją ponownie.'
BAD_KEY_WISH = 'Nie wiadomo, czy chcesz otrzymać klucz.'
NO_KEY = 'Podaj klucz.'


class SurveyWriteSerializer(serializers.Serializer):
    survey = serializers.CharField(error_messages={
        'required': NOT_A_SURVEY, 'blank': NOT_A_SURVEY, 'null': NOT_A_SURVEY,
        'invalid': NOT_A_SURVEY})
    version = serializers.IntegerField(error_messages={
        'required': STALE_VERSION, 'invalid': STALE_VERSION, 'null': STALE_VERSION,
        'max_string_length': STALE_VERSION})
    consent_version = serializers.CharField(error_messages={
        'required': STALE_CONSENT, 'blank': STALE_CONSENT, 'null': STALE_CONSENT,
        'invalid': STALE_CONSENT})
    # JSONField, not CharField / IntegerField, ON PURPOSE for both bookkeeping fields: a
    # CharField refuses a list and an IntegerField refuses "abc", and a field whose job is never
    # to refuse a sheet must not refuse it by type either. Whatever arrives is judged in the
    # `validate_*` below and dropped when it does not fit.
    locale = serializers.JSONField(required=False, allow_null=True)
    duration_s = serializers.JSONField(required=False, allow_null=True)
    answers = serializers.JSONField(error_messages={
        'required': rules.ANSWERS_EMPTY, 'null': rules.ANSWERS_EMPTY,
        'invalid': rules.ANSWERS_NOT_AN_OBJECT})
    # The two opt-ins. Absent, null or '' means "no, thank you" and is the common case.
    contact_email = serializers.CharField(required=False, allow_blank=True, allow_null=True,
                                          error_messages={'invalid': 'Ten adres e-mail nie wygląda poprawnie.'})
    wants_key = serializers.BooleanField(required=False, default=False, allow_null=True,
                                         error_messages={'invalid': BAD_KEY_WISH})
    # Honeypot, as on the board and in feedback/: a real form leaves it empty because no reader
    # can see it.
    website = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_website(self, value):
        if (value or '').strip():
            raise serializers.ValidationError('Spam?')
        return ''

    def validate_survey(self, value):
        if value not in rules.SURVEYS:
            raise serializers.ValidationError(NOT_A_SURVEY)
        return value

    def validate_locale(self, value):
        """Never refuses — anything that is not a language tag becomes ''."""
        locale = value.strip() if isinstance(value, str) else ''
        return locale if rules.LOCALE_RE.fullmatch(locale) else ''

    def validate_duration_s(self, value):
        """Never refuses — anything that is not an integer within a day becomes null."""
        # bool before int: `true` is an int in Python and is not a duration.
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value if 0 <= value <= rules.MAX_DURATION_S else None

    def validate_answers(self, value):
        clean, problem = rules.clean_answers(value)
        if problem:
            raise serializers.ValidationError(problem)
        return clean

    def validate_contact_email(self, value):
        email, problem = rules.clean_email(value)
        if problem:
            raise serializers.ValidationError(problem)
        return email

    def validate(self, attrs):
        # Reached only when every field passed on its own, so `survey` is a known slug here.
        problems = {}
        if attrs['version'] != rules.SURVEYS[attrs['survey']]['version']:
            problems['version'] = STALE_VERSION
        if attrs['consent_version'] != rules.CONSENT_VERSION:
            problems['consent_version'] = STALE_CONSENT
        if problems:
            raise serializers.ValidationError(problems)
        return attrs


class SurveyWithdrawSerializer(serializers.Serializer):
    key = serializers.CharField(error_messages={'required': NO_KEY, 'blank': NO_KEY, 'null': NO_KEY,
                                                'invalid': NO_KEY})
