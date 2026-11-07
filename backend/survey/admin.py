"""The reading surface for the study team: list, filter, open one sheet — nothing else.

Read-only by construction: every field is in `readonly_fields`, there is no add and no change,
because a sheet is a person's own words given under a promise and is never edited here.
Deletion is the one write, and it belongs to the head admin alone (`is_superuser`): it is how
the table is emptied once the study's analysis is done and exported (`LEGAL.md` §9b). A single
person's request to withdraw is `manage.py survey_withdraw`, not this page: the two hashes that
would identify their row are deliberately not shown here, only whether each exists.
"""
import json

from django.contrib import admin
from django.utils.html import format_html

from .models import SurveyResponse


@admin.register(SurveyResponse)
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = ['id', 'survey', 'version', 'consent_version', 'status', 'locale', 'duration_s',
                    'received_on', 'has_contact', 'has_key']
    list_filter = ['survey', 'version', 'consent_version', 'status', 'received_on']
    # The raw `answers` column is shown through `pretty_answers` instead, and the two hashes
    # through `has_contact` / `has_key`; `fields` keeps the raw ones off the page.
    fields = ['survey', 'version', 'consent_version', 'status', 'withdrawn_on', 'locale',
              'duration_s', 'received_on', 'has_contact', 'has_key', 'pretty_answers']
    readonly_fields = fields
    # No `search_fields`: nothing in a sheet is meant to be found by its words.

    @admin.display(description='odpowiedzi')
    def pretty_answers(self, obj):
        # format_html escapes the JSON, so a string answer holding `<script>` is shown as text.
        return format_html('<pre style="white-space: pre-wrap; margin: 0">{}</pre>',
                           json.dumps(obj.answers, ensure_ascii=False, indent=2, sort_keys=True))

    @admin.display(description='zostawił(a) e-mail', boolean=True)
    def has_contact(self, obj):
        return bool(obj.contact_hash)

    @admin.display(description='ma klucz', boolean=True)
    def has_key(self, obj):
        return bool(obj.key_hash)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # Viewing stays Django's default (`has_view_permission`); saving is refused for everybody,
        # so the change form is a read-only page.
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
