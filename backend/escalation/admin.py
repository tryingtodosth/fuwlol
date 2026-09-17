"""Head-admin only, in every direction: module, view, change, delete, add. No exception
for `is_staff` — that is the entire point of this app. The state transition itself never
happens through a plain field edit (status/decided_by/decided_at stay read-only); it only
ever happens through the two actions below, which call `services.decide_escalation` so the
audit log, the reputation-safe idempotency check, and the security logger all still fire."""
from django.contrib import admin

from .models import Escalation
from .services import decide_escalation


def _is_head_admin(request):
    return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


@admin.register(Escalation)
class EscalationAdmin(admin.ModelAdmin):
    list_display = ['id', 'content_type', 'object_id', 'status', 'requested_by', 'decided_by', 'created_at']
    list_filter = ['status', 'content_type']
    readonly_fields = ['content_type', 'object_id', 'requested_by', 'reason', 'evidence_ref',
                       'status', 'decided_by', 'decided_at', 'created_at']
    fields = readonly_fields + ['decision_note']
    actions = ['approve', 'decline']

    def has_module_permission(self, request):
        return _is_head_admin(request)

    def has_view_permission(self, request, obj=None):
        return _is_head_admin(request)

    def has_change_permission(self, request, obj=None):
        return _is_head_admin(request)

    def has_delete_permission(self, request, obj=None):
        return False  # the audit trail is append-only — no exceptions, not even for superusers

    def has_add_permission(self, request):
        return False  # created only via create_escalation(), never by hand

    def _decide(self, request, queryset, decision):
        done, failed = 0, 0
        for esc in queryset.filter(status='pending'):
            try:
                decide_escalation(esc, request.user, decision, esc.decision_note)
                done += 1
            except Exception as e:
                failed += 1
                self.message_user(request, f'#{esc.pk}: {e}', level='ERROR')
        if done:
            self.message_user(request, f'{done} zgłoszeń rozstrzygniętych.')
        if not done and not failed:
            self.message_user(request, 'Nic do rozstrzygnięcia — zaznaczone wiersze nie czekają na decyzję.',
                              level='WARNING')

    @admin.action(description='Zatwierdź — przygotuj pakiet zgłoszenia do NASK')
    def approve(self, request, queryset):
        self._decide(request, queryset, 'approve')

    @admin.action(description='Odrzuć — nie zgłaszaj do NASK, odblokuj zwykłą moderację')
    def decline(self, request, queryset):
        self._decide(request, queryset, 'decline')
