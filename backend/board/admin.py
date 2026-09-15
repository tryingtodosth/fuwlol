from django.contrib import admin

from . import moderation as rules
from .models import Message, Report


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'nick', 'excerpt', 'is_hidden', 'open_reports', 'created_at']
    list_filter = ['is_hidden', 'format', 'created_at']
    search_fields = ['nick', 'body']
    readonly_fields = ['ip_hash', 'created_at']
    actions = ['hide', 'unhide']

    @admin.display(description='treść')
    def excerpt(self, obj):
        return obj.body[:60]

    @admin.display(description='zgłoszenia')
    def open_reports(self, obj):
        return obj.reports.filter(resolved=False).count()

    @admin.action(description='Ukryj wybrane wiadomości')
    def hide(self, request, queryset):
        for msg in queryset:
            msg.is_hidden, msg.hidden_by = True, request.user
            msg.save(update_fields=['is_hidden', 'hidden_by'])
            rules.settle_reports(msg, request.user, upheld=True)

    @admin.action(description='Przywróć wybrane wiadomości')
    def unhide(self, request, queryset):
        for msg in queryset:
            msg.is_hidden, msg.hidden_by = False, None
            msg.save(update_fields=['is_hidden', 'hidden_by'])
            rules.settle_reports(msg, request.user, upheld=False)


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['id', 'message', 'reason', 'reporter', 'resolved', 'upheld', 'created_at']
    list_filter = ['reason', 'resolved', 'upheld']
    readonly_fields = ['message', 'reporter', 'ip_hash', 'created_at']
