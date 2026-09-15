from rest_framework.permissions import BasePermission

from .visibility import is_head_admin

NOT_HEAD_ADMIN = 'Ta czynność jest zarezerwowana dla administracji (head-admin).'


class IsHeadAdmin(BasePermission):
    """Gate for every escalation-review endpoint. Checked twice per request on a detail
    view — `has_permission` (view-level) AND `has_object_permission` (object-level, called
    explicitly via `check_object_permissions`) — so a guessable/sequential escalation id is
    never enough on its own; the role is re-derived from `request.user` fresh every time,
    never cached, never taken from anything the client sent."""
    message = NOT_HEAD_ADMIN

    def has_permission(self, request, view):
        return is_head_admin(request.user)

    def has_object_permission(self, request, view, obj):
        return is_head_admin(request.user)
