import logging

from django import forms
from django.contrib import admin
from django.utils import timezone

from . import rules
from .models import Practice, PracticeNote, Publication, Template, Visit, WumProfile

security_log = logging.getLogger('security')


@admin.register(WumProfile)
class WumProfileAdmin(admin.ModelAdmin):
    """Read-only evidence. An account that must go is DEACTIVATED on the User (DRF refuses the
    tokens of an inactive user), never deleted: its publications are the record of what was
    agreed to."""
    list_display = ['user', 'first_name', 'surname', 'contact_email', 'created_at', 'agreed_text_version']
    search_fields = ['user__username', 'first_name', 'surname', 'contact_email']
    readonly_fields = ['user', 'first_name', 'surname', 'contact_email', 'contact_phone',
                       'agreed_text_version', 'created_at']
    raw_id_fields = ['user']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class TemplateAdminForm(forms.ModelForm):
    class Meta:
        model = Template
        fields = ['slug', 'title', 'locale', 'summary', 'document', 'status']
        widgets = {'document': forms.Textarea(attrs={'rows': 30, 'cols': 100, 'style': 'font-family: monospace'})}

    def clean_document(self):
        # The same function as the API's serializer: two write paths, one rule.
        document = self.cleaned_data['document']
        problems = rules.template_problems(document)
        if problems:
            raise forms.ValidationError(problems)
        return document


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    """The authoring surface: paste the app's exported example here, give it a title, publish."""
    form = TemplateAdminForm
    list_display = ['slug', 'title', 'locale', 'status', 'updated_at']
    list_filter = ['status', 'locale']
    list_editable = ['status']
    search_fields = ['slug', 'title', 'summary']
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ['document_version', 'created_by', 'created_at', 'updated_at']

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    """Read-only. The one staff action is a takedown, which is a withdrawal with a different
    author: the row stays, the status says who did it, and the `security` log has a line."""
    list_display = ['public_id', 'status', 'account', 'payload_version', 'consent_text_version',
                    'created_at', 'withdrawn_at']
    list_filter = ['status', 'payload_version', 'created_at']
    search_fields = ['public_id', 'account__username']
    date_hierarchy = 'created_at'
    readonly_fields = ['public_id', 'account', 'payload', 'payload_version', 'consent_text_version',
                       'status', 'created_at', 'withdrawn_at', 'superseded_by']
    actions = ['withdraw_selected']

    @admin.action(description='Wycofaj zaznaczone publikacje (zdjęcie przez administrację)')
    def withdraw_selected(self, request, queryset):
        now = timezone.now()
        for row in queryset.filter(status='published'):
            row.status = 'withdrawn'
            row.withdrawn_at = now
            row.save(update_fields=['status', 'withdrawn_at'])
            security_log.info('wum.publication.takedown id=%s by=%s', row.public_id, request.user.username)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# --- the practice round -----------------------------------------------------------------------

class PracticeAdminForm(forms.ModelForm):
    class Meta:
        model = Practice
        fields = ['display_name', 'profession', 'about', 'listed', 'slot_minutes', 'hours']

    def clean_hours(self):
        problems = rules.hours_problems(self.cleaned_data['hours'])
        if problems:
            raise forms.ValidationError(problems)
        return self.cleaned_data['hours']

    def clean_slot_minutes(self):
        problems = rules.slot_minutes_problems(self.cleaned_data['slot_minutes'])
        if problems:
            raise forms.ValidationError(problems)
        return self.cleaned_data['slot_minutes']


@admin.register(Practice)
class PracticeAdmin(admin.ModelAdmin):
    """The one staff action is to unlist a practice (`listed`); the row and its diary stay."""
    form = PracticeAdminForm
    list_display = ['display_name', 'profession', 'owner', 'listed', 'slot_minutes', 'updated_at']
    list_filter = ['profession', 'listed']
    search_fields = ['display_name', 'owner__username']
    readonly_fields = ['public_id', 'owner', 'created_at', 'updated_at']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    """Read-only evidence of what was asked and decided."""
    list_display = ['start', 'practice', 'patient', 'status', 'created_by', 'decided_at']
    list_filter = ['status', 'created_by', 'practice']
    search_fields = ['practice__display_name', 'patient__username', 'public_id']
    date_hierarchy = 'start'
    readonly_fields = ['public_id', 'practice', 'patient', 'start', 'end', 'status', 'reason', 'note',
                       'created_by', 'created_at', 'updated_at', 'decided_at']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PracticeNote)
class PracticeNoteAdmin(admin.ModelAdmin):
    """Read-only, like the publication: a note is the practice's record and the model refuses
    edits anyway (`PracticeNote.save`)."""
    list_display = ['created_at', 'practice', 'patient', 'shared_with_patient', 'amends']
    list_filter = ['shared_with_patient', 'practice']
    search_fields = ['practice__display_name', 'patient__username', 'public_id']
    readonly_fields = ['public_id', 'practice', 'patient', 'visit', 'body', 'shared_with_patient', 'shared_at',
                       'amends', 'created_at']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
