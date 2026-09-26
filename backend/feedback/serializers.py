"""Writing one note. There is no read serializer: the queue is read in the Django admin.

The refusals are deliberately few, because every one of them is a note somebody meant to
leave and did not. Only the *text* can be refused — it is the whole content. The hidden
fields (`location`, `locale`) never refuse anything: a widget that sends a malformed path is
a bug in the widget, and losing the sentence over it would be a worse one, so they are
normalised away to blank instead (`models.py`, "A blank `location` is still a note worth
keeping").

The sentences are Polish, like every other refusal in this project — and MedApp's widget, which
is the only caller, is trilingual. It therefore keys its own translated message off the FIELD
NAME in the DRF error body (`text`, `kind`) and only falls back to the sentence it was given.
`src/lib/feedback/api.ts` on the MedApp side is the other half of that arrangement.
"""
import re

from rest_framework import serializers

from .models import APP_CHOICES, KIND_CHOICES, MAX_LEN

# A router path and nothing else: one leading slash (never two — `//host` is a URL), then no
# whitespace, no control characters, no scheme. Query and fragment are allowed because a screen
# can be a filter state (`/history?symptom=3`) and that is worth knowing.
LOCATION_RE = re.compile(r'^/(?!/)[^\s\x00-\x1f]{0,199}$')
# `pl`, `uk`, `en`, and a regional pair like `pt-BR`. Anything else is dropped, not refused.
LOCALE_RE = re.compile(r'^[a-z]{2}(-[A-Za-z]{2})?$')


class FeedbackWriteSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(
        choices=[c[0] for c in KIND_CHOICES],
        error_messages={'invalid_choice': 'Wybierz rodzaj uwagi.',
                        'required': 'Wybierz rodzaj uwagi.'})
    text = serializers.CharField(trim_whitespace=True, error_messages={
        'blank': 'Napisz, o co chodzi.', 'required': 'Napisz, o co chodzi.',
        'null': 'Napisz, o co chodzi.'})
    # Hidden in the interface on purpose: the app fills it in, and the person writing the note
    # is not asked to name the screen they are already looking at.
    # No `max_length` on either of these, and `allow_null` on both, ON PURPOSE: a field whose
    # job is never to refuse a note must not refuse it by being too long or absent either. The
    # length bound lives in the regexes below, which DROP what does not fit. (Both failed
    # exactly that way the first time this suite ran.)
    location = serializers.CharField(required=False, allow_blank=True, allow_null=True,
                                     trim_whitespace=True)
    locale = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    app = serializers.ChoiceField(choices=[c[0] for c in APP_CHOICES], required=False,
                                  default='skoki')
    # Honeypot, as on the board: a real widget leaves this empty because no reader can see it.
    website = serializers.CharField(required=False, allow_blank=True)

    def validate_website(self, value):
        if (value or '').strip():
            raise serializers.ValidationError('Spam?')
        return ''

    def validate_text(self, value):
        text = (value or '').strip()
        if not text:
            raise serializers.ValidationError('Napisz, o co chodzi.')
        if len(text) > MAX_LEN:
            raise serializers.ValidationError(f'Najwyżej {MAX_LEN} znaków.')
        return text

    def validate_location(self, value):
        """Never refuses — see the module docstring. Anything that is not a path becomes ''."""
        location = (value or '').strip()
        return location if LOCATION_RE.match(location) else ''

    def validate_locale(self, value):
        locale = (value or '').strip()
        return locale if LOCALE_RE.match(locale) else ''
