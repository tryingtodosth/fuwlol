from django.contrib import admin

from .models import Feedback


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    """The queue. `status` is the only editable field: a note is somebody's own words and is
    never edited here — it is read, filed, and left as it arrived."""
    list_display = ['id', 'kind', 'excerpt', 'location', 'locale', 'status', 'created_at']
    list_filter = ['status', 'kind', 'app', 'locale', 'created_at']
    search_fields = ['text', 'location']
    list_editable = ['status']
    readonly_fields = ['app', 'kind', 'text', 'location', 'locale', 'ip_hash', 'author',
                       'created_at']
    actions = ['mark_triaged', 'mark_done', 'mark_spam']

    @admin.display(description='treść')
    def excerpt(self, obj):
        return obj.text[:80]

    def _set_status(self, queryset, value):
        # update() rather than save() in a loop: there is no signal, no derived column and no
        # audit row on this model, so the queue can be filed in one statement.
        return queryset.update(status=value)

    @admin.action(description='Oznacz jako przejrzane')
    def mark_triaged(self, request, queryset):
        self._set_status(queryset, 'triaged')

    @admin.action(description='Oznacz jako załatwione')
    def mark_done(self, request, queryset):
        self._set_status(queryset, 'done')

    @admin.action(description='Oznacz jako spam')
    def mark_spam(self, request, queryset):
        self._set_status(queryset, 'spam')
