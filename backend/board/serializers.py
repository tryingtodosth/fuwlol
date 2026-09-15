"""Reading and writing one shoutbox message.

The write path is where the board's three refusals live — no pictures, at most five
links, at most 2048 characters — plus the nick rules, which differ for a guest and for
somebody logged in. A logged-in author is always their own username: letting them type
a nick would make impersonation a text field.
"""
import re

from django.contrib.auth.models import User
from rest_framework import serializers

from .models import DEFAULT_NICK, FORMAT_CHOICES, MAX_LEN, Message, Report
from .trust import can_moderate

# Anything that would put a picture in the stream. Markdown images, raw HTML, LaTeX
# graphics and inline data: URLs — links to a picture elsewhere are fine, embedding is not.
IMAGE_MARKERS = ('![', '<img', '\\includegraphics', 'data:image')
MAX_URLS = 5
URL_RE = re.compile(r'(?:https?://|www\.)\S+', re.IGNORECASE)
# letters, digits, underscore (\w), plus space, dot and hyphen — unicode, so Zdzisław works
NICK_RE = re.compile(r'^[\w .\-]{1,30}$', re.UNICODE)


class MessageSerializer(serializers.ModelSerializer):
    """What the board hands back. `can_hide` is per-caller, so the frontend can show the
    moderation links without a second request asking who it is."""
    is_guest = serializers.BooleanField(read_only=True)
    author_id = serializers.IntegerField(read_only=True)
    can_hide = serializers.SerializerMethodField()
    open_reports = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ['id', 'nick', 'is_guest', 'author_id', 'format', 'body',
                  'created_at', 'is_hidden', 'can_hide', 'open_reports']
        read_only_fields = fields

    def get_can_hide(self, obj) -> bool:
        request = self.context.get('request')
        return bool(request and can_moderate(request.user))

    def get_open_reports(self, obj):
        """The open-report count, but only for whoever may act on it — a guest reporter
        should not learn from the response how many other people flagged the same message."""
        request = self.context.get('request')
        if not (request and can_moderate(request.user)):
            return None
        return obj.reports.filter(resolved=False).count()


class ReportSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=[c[0] for c in Report.REASONS],
                                     error_messages={'invalid_choice': 'Wybierz powód zgłoszenia.'})
    note = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True, max_length=2000)


class MessageWriteSerializer(serializers.Serializer):
    nick = serializers.CharField(required=False, allow_blank=True, max_length=30,
                                 error_messages={'max_length': 'Nick: najwyżej 30 znaków.'})
    body = serializers.CharField(trim_whitespace=True, error_messages={
        'blank': 'Napisz coś.', 'required': 'Napisz coś.', 'null': 'Napisz coś.'})
    format = serializers.ChoiceField(choices=[c[0] for c in FORMAT_CHOICES],
                                     required=False, default='text')
    # Honeypot: a real form leaves this empty because the field is invisible to a reader.
    website = serializers.CharField(required=False, allow_blank=True)

    def validate_website(self, value):
        if (value or '').strip():
            raise serializers.ValidationError('Spam?')
        return ''

    def validate_body(self, value):
        body = (value or '').strip()
        if not body:
            raise serializers.ValidationError('Napisz coś.')
        if len(body) > MAX_LEN:
            raise serializers.ValidationError(f'Najwyżej {MAX_LEN} znaków.')
        low = body.lower()
        if any(marker in low for marker in IMAGE_MARKERS):
            raise serializers.ValidationError('Obrazki nie są tu dozwolone — linki tak.')
        if len(URL_RE.findall(body)) > MAX_URLS:
            raise serializers.ValidationError('Za dużo linków.')
        return body

    def validate(self, data):
        """The nick, which is the one field whose rules depend on who is asking."""
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            data['nick'] = user.username  # never what was submitted
            return data
        nick = (data.get('nick') or '').strip() or DEFAULT_NICK
        if not NICK_RE.match(nick):
            raise serializers.ValidationError(
                {'nick': ['Nick: litery, cyfry, spacje oraz . _ - (do 30 znaków).']})
        if User.objects.filter(username__iexact=nick).exists():
            raise serializers.ValidationError(
                {'nick': ['Ten nick należy do zarejestrowanego użytkownika']})
        data['nick'] = nick
        return data
