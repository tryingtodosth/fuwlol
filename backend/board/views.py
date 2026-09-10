"""The board's two endpoints: the stream, and the moderator's hide switch.

Paging is by id rather than by page number, because the stream grows at the top: a
page-number cursor would shift under the reader every time somebody writes something.
`?before=` walks backwards into the archive, `?since=` is what polling asks, and both
answers carry the same `count`/`latest_id` for the whole visible stream so the client can
keep its cursor current even when a poll comes back empty.
"""
from django.db.models import Max
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import Message, hash_ip
from .serializers import MessageSerializer, MessageWriteSerializer
from .trust import can_moderate

DEFAULT_LIMIT = 50
MAX_LIMIT = 100


def _int(params, name):
    try:
        return int(params.get(name))
    except (TypeError, ValueError):
        return None


class BoardView(APIView):
    """`GET /api/board/` — the stream. `POST /api/board/` — write to it, no account needed."""
    permission_classes = [AllowAny]

    def get_throttles(self):
        if self.request.method != 'POST':
            return super().get_throttles()  # reading the board costs the ordinary anon budget
        # ScopedRateThrottle reads `throttle_scope` off the VIEW, not off the instance it is
        # handed, so the scope has to be set here — hence a method rather than an attribute.
        self.throttle_scope = 'board_user' if self.request.user.is_authenticated else 'board_anon'
        return [ScopedRateThrottle()]

    def get(self, request):
        params = request.query_params
        show_hidden = (params.get('include_hidden') in ('1', 'true', 'True')
                       and can_moderate(request.user))
        stream = Message.objects.all() if show_hidden else Message.objects.filter(is_hidden=False)

        limit = _int(params, 'limit') or DEFAULT_LIMIT
        limit = max(1, min(limit, MAX_LIMIT))
        before, since = _int(params, 'before'), _int(params, 'since')

        page = stream
        if since is not None:
            page = page.filter(id__gt=since)
        if before is not None:
            page = page.filter(id__lt=before)

        return Response({
            'count': stream.count(),
            'latest_id': stream.aggregate(top=Max('id'))['top'] or 0,
            'results': MessageSerializer(page[:limit], many=True,
                                         context={'request': request}).data,
        })

    def post(self, request):
        s = MessageWriteSerializer(data=request.data, context={'request': request})
        s.is_valid(raise_exception=True)
        data = s.validated_data
        user = request.user if request.user.is_authenticated else None
        msg = Message.objects.create(
            author=user,
            nick=data['nick'],
            body=data['body'],
            format=data.get('format') or 'text',
            ip_hash=hash_ip(request.META.get('REMOTE_ADDR', '')),
        )
        return Response(MessageSerializer(msg, context={'request': request}).data,
                        status=status.HTTP_201_CREATED)


class HideView(APIView):
    """`POST /api/board/<id>/hide/` and `/restore/`. Hiding keeps the row: a message put
    back comes back where it was, and `restore` clears who hid it rather than recording
    a second name in a field that only has room for one."""
    permission_classes = [AllowAny]
    hidden = True

    def post(self, request, pk):
        if not can_moderate(request.user):
            raise PermissionDenied('Nie możesz moderować czatu.')
        msg = get_object_or_404(Message, pk=pk)
        msg.is_hidden = self.hidden
        msg.hidden_by = request.user if self.hidden else None
        msg.save(update_fields=['is_hidden', 'hidden_by'])
        return Response(MessageSerializer(msg, context={'request': request}).data)
