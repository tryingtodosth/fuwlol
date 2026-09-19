"""The staff side of the claims flow.

Read-mostly on purpose. A claim is evidence of consent, and the Django admin is the one
place in this project where a row can be edited without going through the rules module —
so the fields that make the row evidence (who, from where, when, which text, which token)
are read-only here, and deleting a claim is switched off entirely. The decision itself
belongs on /moderacja/zgody, where the plausibility signals are; what this page is for is
looking a row up and reading what happened to it.
"""
from django.contrib import admin

from .models import ConsentHide, PersonClaim


class ConsentHideInline(admin.TabularInline):
    """Which posts this claim took off the page, and what each had been. The record that
    makes a precaution reversible — never edited by hand."""
    model = ConsentHide
    extra = 0
    readonly_fields = ['post', 'previous_status', 'created_at']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PersonClaim)
class PersonClaimAdmin(admin.ModelAdmin):
    list_display = ['person', 'email', 'wish', 'status', 'created_at', 'verified_at',
                    'applied_at', 'decided_by']
    list_filter = ['status', 'wish']
    search_fields = ['email', 'person__name', 'person__surname', 'person__slug', 'note']
    date_hierarchy = 'created_at'
    inlines = [ConsentHideInline]
    readonly_fields = ['person', 'email', 'wish', 'note', 'token', 'consent_text_version',
                       'requester_ip', 'requester_user_agent', 'user', 'created_at',
                       'verified_at', 'applied_at', 'previous_consent', 'previous_listed',
                       'manage_token', 'manage_token_expires_at']
    fieldsets = [
        ('Wniosek', {'fields': ['person', 'email', 'wish', 'note', 'status']}),
        ('Dowód zgody', {'fields': ['consent_text_version', 'created_at', 'verified_at', 'applied_at',
                                    'requester_ip', 'requester_user_agent', 'user']}),
        ('Decyzja', {'fields': ['decided_by', 'decided_at', 'decision_note']}),
        ('Stan sprzed wniosku', {'fields': ['previous_consent', 'previous_listed']}),
        ('Linki', {'fields': ['token', 'manage_token', 'manage_token_expires_at']}),
    ]

    def has_delete_permission(self, request, obj=None):
        """Never. An approved claim is this archive's evidence that somebody agreed — and
        a rejected one is the record that somebody asked and was told no, which is just as
        much a part of the trust model. A wrong decision is corrected by a new row."""
        return False


@admin.register(ConsentHide)
class ConsentHideAdmin(admin.ModelAdmin):
    list_display = ['post', 'claim', 'previous_status', 'created_at']
    list_filter = ['previous_status']
    readonly_fields = ['claim', 'post', 'previous_status', 'created_at']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
