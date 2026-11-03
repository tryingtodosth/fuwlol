"""The Django admin is where a superuser sets what the API deliberately cannot: who manages
(`can_manage`), who sits on the Zarząd and with which `funkcja`. Votes and ballots are
read-only here, and a Ballot is not even listed — the admin must not become the place where
somebody browses secret ballots next to the participation list."""
from django.contrib import admin

from .models import Comment, Member, MemberAction, Poll, PublishKey, StatusEntry


class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'status', 'role', 'affiliation', 'funkcja', 'zarzad', 'can_manage']
    list_filter = ['status', 'role', 'affiliation', 'zarzad', 'can_manage']
    search_fields = ['name', 'email']
    readonly_fields = ['status', 'role', 'created_at', 'email_confirmed_at', 'approved_at', 'left_at', 'agreed_text_version']

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MemberAction)
class MemberActionAdmin(ReadOnly):
    list_display = ['at', 'member', 'action', 'from_status', 'to_status', 'actor']


@admin.register(Poll)
class PollAdmin(ReadOnly):
    list_display = ['title', 'organ', 'mode', 'status', 'opens_at', 'closes_at', 'trial']


@admin.register(Comment)
class CommentAdmin(ReadOnly):
    list_display = ['poll', 'member', 'created_at', 'hidden_at']


@admin.register(StatusEntry)
class StatusEntryAdmin(admin.ModelAdmin):
    list_display = ['published_at', 'title', 'status', 'source']


@admin.register(PublishKey)
class PublishKeyAdmin(ReadOnly):
    list_display = ['name', 'created_at', 'revoked_at']
