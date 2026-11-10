from rest_framework import serializers

from .models import CONSENT_VERSION, EMAIL_MAX, TOKEN_MAX


class SubscribeSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=EMAIL_MAX)
    consent_version = serializers.CharField(max_length=40)
    # Dropped rather than refused when odd: a sign-up is not lost over its language tag.
    locale = serializers.CharField(max_length=32, required=False, allow_blank=True)
    # Honeypot, as on feedback: a person never sees it; a bot that fills it gets a quiet 202.
    website = serializers.CharField(required=False, allow_blank=True)

    def validate_email(self, value):
        return value.strip().lower()

    def validate_consent_version(self, value):
        if value != CONSENT_VERSION:
            raise serializers.ValidationError('consent_version')
        return value

    def validate_locale(self, value):
        value = (value or '').strip().lower()
        return value if len(value) <= 8 and value.replace('-', '').isalpha() else ''


class TokenSerializer(serializers.Serializer):
    """The token from a mailed link (models.py: signed, never stored)."""
    token = serializers.CharField(max_length=TOKEN_MAX)
