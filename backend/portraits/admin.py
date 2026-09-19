"""The staff side of the gallery.

Everything here is read-mostly on purpose: `status` moves through `portraits/rules.py`
so that a transition always writes a `PortraitAction`, and an admin that let somebody set
`status` directly would be a second, unaudited path to the same field. The two actions
below therefore call the rule module rather than `queryset.update()`.

`PortraitAction` is registered read-only — an audit log that staff can edit is an audit
log that proves nothing.
"""
from django.contrib import admin

from . import rules
from .models import Portrait, PortraitAction, PortraitVote


@admin.register(Portrait)
class PortraitAdmin(admin.ModelAdmin):
    list_display = ['id', 'person', 'status', 'uploaded_by_username', 'votes_count', 'created_at']
    list_filter = ['status', 'person__image_consent']
    search_fields = ['person__name', 'person__surname', 'caption', 'source_note', 'uploaded_by_username']
    readonly_fields = ['sha256', 'original_name', 'uploaded_by_username', 'created_at']
    actions = ['publish', 'hide']

    @admin.display(description='Głosy')
    def votes_count(self, obj):
        return obj.votes.count()

    def _run(self, request, qs, decision):
        done = 0
        for portrait in qs:
            try:
                rules.moderate(portrait, request.user, decision, 'panel administracyjny')
            except Exception as e:  # already in that state / no consent — say which one
                self.message_user(request, f'#{portrait.pk}: {e}', level='warning')
            else:
                done += 1
        self.message_user(request, f'Zmieniono {done} zdjęć.')

    @admin.action(description='Opublikuj')
    def publish(self, request, qs):
        self._run(request, qs, 'publish')

    @admin.action(description='Ukryj')
    def hide(self, request, qs):
        self._run(request, qs, 'hide')


@admin.register(PortraitVote)
class PortraitVoteAdmin(admin.ModelAdmin):
    list_display = ['portrait', 'user', 'created_at']
    readonly_fields = ['created_at']


@admin.register(PortraitAction)
class PortraitActionAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'action', 'actor', 'portrait', 'previous_status']
    list_filter = ['action']
    readonly_fields = ['portrait', 'actor', 'action', 'reason', 'previous_status', 'created_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
