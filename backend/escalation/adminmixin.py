"""The Django admin is a second read path to every model, with its own permission system
(`view_post`, `view_message`, …) that knows nothing about escalation. Without this mixin a
staff moderator with admin access reads the title, body and files of a pending-NASK item at
/admin/ — exactly the leak the escalation app exists to close. Every ModelAdmin whose rows
can be escalated (or hang off something that can — attachments, actions, reports) mixes
this in. Head-admin (is_superuser) still sees everything, as in the API."""
from django.contrib.contenttypes.models import ContentType

from .models import Escalation
from .visibility import ACTIVE_STATUSES, is_head_admin


def _active_ids(model_cls):
    ct = ContentType.objects.get_for_model(model_cls)
    return Escalation.objects.filter(content_type=ct, status__in=ACTIVE_STATUSES).values_list('object_id', flat=True)


class HideEscalatedMixin:
    # (lookup, model) pairs: each excludes rows whose `lookup` is an escalated `model`.
    # The default hides the row itself; e.g. ModerationActionAdmin adds ('post', Post).
    escalation_guards = ()

    def _guards(self):
        return list(self.escalation_guards) or [('pk', self.model)]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if is_head_admin(request.user):
            return qs
        for lookup, model in self._guards():
            qs = qs.exclude(**{f'{lookup}__in': _active_ids(model)})
        return qs

    def _obj_escalated(self, obj):
        for lookup, model in self._guards():
            value = obj.pk if lookup == 'pk' else getattr(obj, f'{lookup}_id', None)
            if value is not None and value in set(_active_ids(model)):
                return True
        return False

    def has_view_permission(self, request, obj=None):
        if obj is not None and not is_head_admin(request.user) and self._obj_escalated(obj):
            return False
        return super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if obj is not None and not is_head_admin(request.user) and self._obj_escalated(obj):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and not is_head_admin(request.user) and self._obj_escalated(obj):
            return False
        return super().has_delete_permission(request, obj)
