r"""The four portrait endpoints. None of them decides anything — `portraits/rules.py` does.

    GET  /api/people/<slug>/portraits/   the gallery (anybody)
    POST /api/people/<slug>/portraits/   upload one (logged in, consent granted)
    POST /api/portraits/<id>/vote/       toggle or move your one vote (logged in)
    POST /api/portraits/<id>/moderate/   publish / reject / hide / restore (trusted)
    GET  /api/portraits/queue/           everything pending, across every person (trusted)

Three of the five arrive with an id or a slug in the URL, which is exactly the shape for
which "visibility is a queryset filter" does nothing at all. So each one says which of the
two it is using, every time:

* the gallery and the queue are FILTERED (`rules.visible_q`) — a stranger asking for a
  person with no consent gets an empty gallery, not a refusal, because for them there is
  nothing there;
* the vote is filtered as well, so a photograph the caller may not see answers 404 rather
  than confirming its existence with a 403;
* the moderation call is NOT filtered and is an object-level check instead. A trusted user
  has to be able to reach a rejected portrait by id to undo a mistaken rejection, and
  `rules.moderate` re-checks the tier, the consent and the current state before it moves
  anything.

The two list endpoints take `sort`, `offset` and `limit` (plus `status`/`mine` on the
gallery and `person` on the queue) and answer with a `count` / `offset` / `limit` / `next`
envelope. The query string is parsed by `rules.read_*`, not here: both endpoints ask the
same questions about paging, and two copies of "what is a valid limit" is one copy too
many. `current` is computed OUTSIDE all of it — the profile photograph is the winner of
the whole gallery, not of whichever page or filter the reader happens to be looking at.

Throttles use `FixedScopeThrottle` from `archive/views.py` rather than a copy: DRF's own
`ScopedRateThrottle` reads the scope off the *view*, so an instance handed a scope by hand
silently allows everything — which is a bug this project has already shipped once.
"""
from django.shortcuts import get_object_or_404
from rest_framework import status as http
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from archive.models import Person
from archive.moderation import IsTrusted
from archive.views import FixedScopeThrottle

from . import rules
from .models import Portrait
from .serializers import (PortraitUploadSerializer, current_block, page_block,
                          portrait_item, queue_item)


def _person(slug):
    """404 for a person who is not listed — an opt-out takes the whole entry away, and
    "this person does not exist here" is the honest answer as well as the safe one."""
    return get_object_or_404(Person.objects.filter(is_listed=True), slug=slug)


def _page(request, qs):
    """`(rows, count, offset, limit)` — the count is taken before the slice, so it is the
    size of the whole answer and not of the page. One extra COUNT query per list, which is
    what makes "Pokaż więcej (k)" able to say a number instead of a shrug."""
    offset, limit = rules.read_paging(request.query_params)
    return list(qs[offset:offset + limit]), qs.count(), offset, limit


class PersonPortraitsView(APIView):
    """The gallery under one person, and the form that adds to it."""
    permission_classes = [AllowAny]

    def get_throttles(self):
        # 10 uploads an hour per address. A portrait is 25 MB of decoded pixels and a
        # moderator's attention; the global per-user rate would allow neither in quantity.
        if self.request.method == 'POST':
            return [FixedScopeThrottle('portrait_upload')]
        return super().get_throttles()

    def get(self, request, slug):
        person = _person(slug)
        params = request.query_params
        sort = rules.read_choice(params, 'sort', tuple(rules.SORT_ORDERS), 'votes')
        mine = rules.read_flag(params, 'mine')
        # `mine` alone widens the status to 'all' — see rules.gallery_queryset. An explicit
        # `status` always wins, so a client that asks for both gets exactly what it asked.
        default_status = 'all' if mine and not params.get('status') else rules.DEFAULT_STATUS
        status = rules.read_choice(params, 'status', rules.STATUS_FILTERS, default_status)
        items, count, offset, limit = _page(
            request, rules.gallery_queryset(request.user, person, sort=sort, status=status, mine=mine))
        my_votes = rules.my_vote_ids(request.user, items)
        moderator = rules.can_moderate(request.user)
        block = rules.upload_block_reason(request.user, person)
        return Response({
            # The raw consent value, so the page can say "not yet" differently from "no".
            'consent': person.image_consent,
            'can_upload': block == '',
            'upload_block_reason': block,
            # Deliberately outside the filter and the page: the profile photograph is the
            # winner of the gallery, and a reader looking at page three of "najnowsze" has
            # not changed who that is.
            'current': current_block(rules.current_portrait(person), request),
            'sort': sort,
            'status': status,
            'mine': mine,
            **page_block(request, count, offset, limit),
            'items': [portrait_item(p, request, my_votes=my_votes, moderator=moderator) for p in items],
        })

    def post(self, request, slug):
        """403 with the reason when this caller may not upload here — including when they
        are not logged in. DRF's own 401 would be technically tidier and would throw away
        the one thing the reader needs: WHY. Every refusal on this endpoint says which of
        the four walls they hit."""
        person = _person(slug)
        block = rules.upload_block_reason(request.user, person)
        if block:
            raise PermissionDenied(block)
        s = PortraitUploadSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        portrait = rules.create_portrait(
            person, request.user, s.validated_data['file'],
            caption=s.validated_data.get('caption', ''),
            source_note=s.validated_data.get('source_note', ''),
            rights_confirmed=s.validated_data['rights_confirmed'])
        return Response(portrait_item(portrait, request, moderator=rules.can_moderate(request.user)),
                        status=http.HTTP_201_CREATED)


class PortraitVoteView(APIView):
    """POST — one vote per person, toggled or moved. Answers with the new count, whether
    it is now mine, and WHO IS WINNING, because a vote is the one action on this page that
    can change the photograph at the top of it and the caller should not have to guess or
    re-fetch to find out."""
    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        return [FixedScopeThrottle('portrait_vote')]

    def post(self, request, pk):
        portrait = get_object_or_404(
            Portrait.objects.filter(rules.visible_q(request.user)).select_related('person'), pk=pk)
        votes, mine = rules.cast_vote(request.user, portrait)
        current = rules.current_portrait(portrait.person)
        return Response({'votes': votes, 'my_vote': mine,
                         'current_id': current.pk if current is not None else None})


class PortraitModerateView(APIView):
    """POST {decision, note?} — publish | reject | hide | restore. 409 when the portrait is
    already in that state (two moderators, one queue), 400 for a decision that is not one
    of the four, 403 when the tier or the consent says no."""
    permission_classes = [IsTrusted]

    def post(self, request, pk):
        # Deliberately unscoped: a rejected portrait is outside a moderator's `visible_q`,
        # and undoing a rejection is precisely the case where they need to reach it by id.
        # `rules.moderate` is the authority check that replaces the missing filter.
        portrait = get_object_or_404(Portrait.objects.select_related('person'), pk=pk)
        data = request.data if hasattr(request.data, 'get') else {}
        portrait = rules.moderate(portrait, request.user, data.get('decision'), data.get('note') or '')
        return Response(portrait_item(portrait, request, moderator=True))


class PortraitQueueView(APIView):
    """GET — photographs waiting for a decision, with the person each one is of. Oldest
    first unless asked otherwise, optionally narrowed to one person, and paged with the
    same envelope as the gallery."""
    permission_classes = [IsTrusted]

    def get(self, request):
        params = request.query_params
        sort = rules.read_choice(params, 'sort', ('new', 'old'), 'old')
        person_slug = (params.get('person') or '').strip()
        items, count, offset, limit = _page(
            request, rules.queue_queryset(request.user, sort=sort, person_slug=person_slug))
        my_votes = rules.my_vote_ids(request.user, items)
        return Response({
            'sort': sort,
            'person': person_slug,
            **page_block(request, count, offset, limit),
            'items': [queue_item(p, request, my_votes=my_votes) for p in items],
        })
