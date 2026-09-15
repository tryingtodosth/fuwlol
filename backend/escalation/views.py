"""Every view here is head-admin-only, checked twice (permission_classes AND an explicit
check_object_permissions call on the detail/decide/file views) — see permissions.py for why.
None of this is reachable through the DEFAULT_PERMISSION_CLASSES = AllowAny the rest of the
project defaults to; every class below sets its own explicitly, on purpose."""
import json
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Escalation
from .permissions import IsHeadAdmin
from .services import create_escalation, decide_escalation, visible_escalations_for


def _row(esc):
    return {
        'id': esc.pk, 'kind': esc.content_type.model, 'object_id': esc.object_id,
        'requested_by': esc.requested_by.username if esc.requested_by_id else None,
        'reason': esc.reason, 'status': esc.status,
        'decided_by': esc.decided_by.username if esc.decided_by_id else None,
        'decision_note': esc.decision_note, 'evidence_ref': esc.evidence_ref,
        'created_at': esc.created_at, 'decided_at': esc.decided_at,
    }


class EscalationListView(APIView):
    """GET /api/moderation/escalations/?status=pending|approved|declined (default: pending)."""
    permission_classes = [IsHeadAdmin]

    def get(self, request):
        qs = visible_escalations_for(request.user)
        wanted = request.query_params.get('status', 'pending')
        if wanted in ('pending', 'approved', 'declined'):
            qs = qs.filter(status=wanted)
        return Response([_row(e) for e in qs])


class EscalationDetailView(APIView):
    """GET /api/moderation/escalations/<id>/ — the escalation's metadata plus the FROZEN
    evidence manifest (never the live target: what head-admin reviews must be exactly what
    was captured, not whatever the content looks like by the time they get to it)."""
    permission_classes = [IsHeadAdmin]

    def get(self, request, pk):
        esc = get_object_or_404(visible_escalations_for(request.user), pk=pk)
        self.check_object_permissions(request, esc)
        manifest_path = Path(settings.EVIDENCE_ROOT) / str(esc.pk) / 'manifest.json'
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, ValueError):
            manifest = None
        d = _row(esc)
        d['evidence'] = manifest
        return Response(d)


class EscalationDecideView(APIView):
    """POST /api/moderation/escalations/<id>/decide/ {decision: approve|decline, note?}."""
    permission_classes = [IsHeadAdmin]

    def post(self, request, pk):
        esc = get_object_or_404(visible_escalations_for(request.user), pk=pk)
        self.check_object_permissions(request, esc)
        decision = request.data.get('decision') if hasattr(request.data, 'get') else None
        note = request.data.get('note') if hasattr(request.data, 'get') else ''
        esc = decide_escalation(esc, request.user, decision, note)
        return Response(_row(esc))


class EscalationEvidenceFileView(APIView):
    """GET /api/moderation/escalations/<id>/evidence/<filename> — streams one captured
    file. `filename` must be an exact match against what is actually on disk; no path
    arithmetic is done on the client-supplied value, so there is nothing to traverse."""
    permission_classes = [IsHeadAdmin]

    def get(self, request, pk, filename):
        esc = get_object_or_404(visible_escalations_for(request.user), pk=pk)
        self.check_object_permissions(request, esc)
        evidence_dir = Path(settings.EVIDENCE_ROOT) / str(esc.pk)
        real_names = {p.name for p in evidence_dir.iterdir()} if evidence_dir.is_dir() else set()
        if filename not in real_names:
            raise Http404
        return FileResponse(open(evidence_dir / filename, 'rb'), as_attachment=True, filename=filename)


def escalate_and_respond(request, target):
    """Shared by the per-app escalate endpoints (archive PostViewSet.escalate,
    CommentModerationView's 'escalate' verb, board's EscalateMessageView). Each of those
    already gates on its own trusted/staff permission class, and applies its own
    'escalate'-scoped throttle, before this ever runs."""
    reason = request.data.get('reason') if hasattr(request.data, 'get') else ''
    esc = create_escalation(target, request.user, reason)
    return Response({'ok': True, 'escalation_id': esc.pk}, status=status.HTTP_201_CREATED)
