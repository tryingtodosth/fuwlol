r"""What a portrait looks like over the wire, and what an upload has to say for itself.

Output is plain dicts built by functions rather than `ModelSerializer`s, for the same
reason `archive.serializers.board_post_payload` is: every field shown here is a decision
about what a caller may know (`votes` is an annotation, `my_vote` is about the caller,
`can_moderate` is about their tier), and a declarative serializer would hide those behind
`fields = [...]` where the next person adds one without noticing what they are exposing.

Input IS a serializer, because the interesting work there is refusal: a file that is not
an image, a missing rights declaration, a caption longer than the column. It deliberately
does NOT touch `status` or `person` — those are decided by `portraits/rules.py`, and a
writable serializer field is how a request would get to choose its own moderation state.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from archive.validators import kind_for, validate_upload

from .rules import NOT_AN_IMAGE, RIGHTS_REQUIRED, can_moderate


class PortraitUploadSerializer(serializers.Serializer):
    """multipart {file, caption?, source_note?, rights_confirmed}.

    `rights_confirmed` is required and must be true. It is not a checkbox we keep for
    tidiness: it is the uploader's own statement that they may publish this file, and the
    only reason we are allowed to look at the bytes at all. Its absence is a malformed
    request (400), which is a different thing from "this person said no" (403) — see
    `rules.upload_block_reason`.
    """
    file = serializers.FileField()
    caption = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    source_note = serializers.CharField(max_length=300, required=False, allow_blank=True, default='')
    rights_confirmed = serializers.BooleanField(
        error_messages={'required': RIGHTS_REQUIRED, 'invalid': RIGHTS_REQUIRED})

    def validate_rights_confirmed(self, value):
        if not value:
            raise serializers.ValidationError(RIGHTS_REQUIRED)
        return value

    def validate_file(self, f):
        """Judged by the bytes, never by the browser. `kind_for` reads the extension and
        `validate_upload` makes Pillow decode the file — a .png full of something else
        fails the second check even though it passed the first, and a real PDF renamed to
        .png fails it too. Both run here so the refusal is a 400 with a Polish sentence
        rather than a 500 from the storage layer."""
        if kind_for(getattr(f, 'name', '') or '') != 'image':
            raise serializers.ValidationError(NOT_AN_IMAGE)
        try:
            validate_upload(f)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(getattr(e, 'messages', None) or [str(e)]))
        return f


def _url(portrait, request):
    """Absolute, like `AttachmentSerializer.get_url`: the SPA is served from another
    origin, so a relative /media path resolves against the wrong host. '' rather than a
    broken URL when the file is gone from storage."""
    if not portrait.file:
        return ''
    return request.build_absolute_uri(portrait.file.url) if request is not None else portrait.file.url


def portrait_item(portrait, request, *, my_votes=frozenset(), moderator=None):
    """One thumbnail's worth of JSON.

    `votes` comes from the `vote_count` annotation when the caller used
    `rules.with_votes` (which every list path does) and falls back to a real COUNT
    otherwise — never to a stored counter. `moderator` is passed in rather than re-derived
    per item so that a gallery of thirty photographs asks "is this caller trusted" once.
    """
    if moderator is None:
        moderator = can_moderate(getattr(request, 'user', None))
    votes = getattr(portrait, 'vote_count', None)
    if votes is None:
        votes = portrait.votes.count()
    return {
        'id': portrait.pk,
        'url': _url(portrait, request),
        'caption': portrait.caption,
        'source_note': portrait.source_note,
        'uploaded_by': portrait.uploaded_by_username or (
            portrait.uploaded_by.username if portrait.uploaded_by_id else ''),
        'status': portrait.status,
        'votes': votes,
        'my_vote': portrait.pk in my_votes,
        'created_at': portrait.created_at,
        'can_moderate': moderator,
    }


def next_url(request, offset, limit, count):
    """The absolute URL of the page after this one, or None when this was the last.

    Built by rewriting `offset` on the request's OWN query string, so whatever the caller
    filtered or sorted by travels with the link and the next page is the next page of the
    same question. A `next` that quietly dropped `?status=pending` would hand back a second
    page of something else.
    """
    if offset + limit >= count:
        return None
    params = request.query_params.copy()
    params['offset'] = str(offset + limit)
    params['limit'] = str(limit)
    return request.build_absolute_uri(f'{request.path}?{params.urlencode()}')


def page_block(request, count, offset, limit):
    """The three numbers and the link that every paginated answer in this app carries.
    Deliberately not DRF's own pagination envelope: the gallery's response is an object
    with `current` and `consent` beside the rows, and a paginator that owns the whole
    response body cannot express that."""
    return {'count': count, 'offset': offset, 'limit': limit,
            'next': next_url(request, offset, limit, count)}


def current_block(portrait, request):
    """The winner, as the person page needs it: just enough to draw the 130 px photo."""
    if portrait is None:
        return None
    return {'id': portrait.pk, 'url': _url(portrait, request), 'caption': portrait.caption}


def queue_item(portrait, request, *, my_votes=frozenset(), moderator=True):
    """A queue row is an ordinary item plus the person it is about — the queue spans every
    person, and "publish this photograph" is not a decision anybody can make without
    knowing whose face it is."""
    item = portrait_item(portrait, request, my_votes=my_votes, moderator=moderator)
    item['person'] = {'slug': portrait.person.slug, 'full_name': portrait.person.full_name}
    return item
