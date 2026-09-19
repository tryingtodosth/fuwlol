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

from .models import Escalation, EvidenceAuditLog
from .permissions import IsHeadAdmin
from .services import (confirm_nask_report_and_purge, create_escalation, decide_escalation,
                       visible_escalations_for)
from .shred import ShredIncomplete


def _row(esc):
    return {
        'id': esc.pk, 'kind': esc.content_type.model, 'object_id': esc.object_id,
        'requested_by': esc.requested_by.username if esc.requested_by_id else None,
        'reason': esc.reason, 'status': esc.status,
        'decided_by': esc.decided_by.username if esc.decided_by_id else None,
        'decision_note': esc.decision_note, 'evidence_ref': esc.evidence_ref,
        'created_at': esc.created_at, 'decided_at': esc.decided_at,
        'reported_to_nask_at': esc.reported_to_nask_at,
        'nask_case_reference': esc.nask_case_reference, 'purged_at': esc.purged_at,
    }


class EscalationListView(APIView):
    """GET /api/moderation/escalations/?status=pending|approved|declined|purged (default: pending).

    This is the critical-quarantine triage list the task calls for, and it is the ONLY
    listing anywhere in the project that shows these rows: `visible_escalations_for`
    returns an empty queryset to anybody who is not head-admin, and the targets themselves
    are gone from `Post.objects` entirely (archive/models.py PostManager)."""
    permission_classes = [IsHeadAdmin]

    def get(self, request):
        qs = visible_escalations_for(request.user)
        wanted = request.query_params.get('status', 'pending')
        if wanted in ('pending', 'approved', 'declined', 'purged'):
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


class EscalationNaskPackageView(APIView):
    """GET /api/moderation/escalations/<id>/nask-package/

    Everything a head-admin needs to file the report with Dyżurnet.pl, in both shapes:
    `package` for a machine, `text` to paste into their form. Any preview links inside it
    are R2 presigned GETs that die after five minutes (config/r2.PREVIEW_TTL_SECONDS) —
    they are bearer capabilities, so they are minutes rather than hours and are never
    logged.

    Reading this changes nothing. The destructive step is a separate, explicit POST, so
    that "I looked at it" and "destroy it" can never be the same click."""
    permission_classes = [IsHeadAdmin]

    def get(self, request, pk):
        from .nask import build_package, render_text
        esc = get_object_or_404(visible_escalations_for(request.user), pk=pk)
        self.check_object_permissions(request, esc)
        package = build_package(esc)
        return Response({'package': package, 'text': render_text(package),
                         'escalation': _row(esc)})


class EscalationPurgeView(APIView):
    """POST /api/moderation/escalations/<id>/purge/
       {confirmed_dispatch: true, case_reference?: str, note?: str}

    The one irreversible action in this project. It refuses unless the escalation is
    already `approved` (reviewed and confirmed criminal) AND the caller states in the
    request body that the package has been forwarded — the endpoint being reachable is not
    itself taken as that statement.

    A partial shred answers 409 with the list of copies that survived: the report is on
    record, the bytes are not all gone, and the fix is to call this again once whatever
    failed is reachable. It is not a 500, because nothing is broken — the world is in a
    state the caller has to know about."""
    permission_classes = [IsHeadAdmin]

    def post(self, request, pk):
        esc = get_object_or_404(visible_escalations_for(request.user), pk=pk)
        self.check_object_permissions(request, esc)
        data = request.data if hasattr(request.data, 'get') else {}
        try:
            esc = confirm_nask_report_and_purge(
                esc, request.user,
                confirmed_dispatch=bool(data.get('confirmed_dispatch')),
                case_reference=data.get('case_reference') or '',
                note=data.get('note') or '')
        except ShredIncomplete as exc:
            return Response(
                {'detail': 'Zgłoszenie zapisano, ale nie wszystkie kopie udało się usunąć. '
                           'Uruchom akcję ponownie po usunięciu przyczyny.',
                 'failures': exc.failures},
                status=status.HTTP_409_CONFLICT)
        return Response(_row(esc))


class EvidenceAuditLogView(APIView):
    """GET /api/moderation/evidence-audit/?post=<id>

    The register of what was destroyed, when, by whom and under which Dyżurnet reference —
    the only thing that outlives a purge. Head-admin only: it holds uploader addresses."""
    permission_classes = [IsHeadAdmin]

    def get(self, request):
        qs = EvidenceAuditLog.objects.select_related('reported_by')
        post_id = request.query_params.get('post')
        if post_id and str(post_id).isdigit():
            qs = qs.filter(original_post_id=int(post_id))
        return Response([{
            'id': r.pk, 'escalation_id': r.escalation_id, 'target_kind': r.target_kind,
            'original_post_id': r.original_post_id, 'file_sha256': r.file_sha256,
            'storage_location': r.storage_location, 'original_name': r.original_name,
            'size_bytes': r.size_bytes, 'uploader_ip': r.uploader_ip,
            'uploader_user_agent': r.uploader_user_agent, 'uploaded_at': r.uploaded_at,
            'reported_to_nask_at': r.reported_to_nask_at,
            'reported_by': r.reported_by_username or (r.reported_by.username if r.reported_by_id else ''),
            'nask_case_reference': r.nask_case_reference, 'created_at': r.created_at,
        } for r in qs])
