from django.contrib import admin

from .models import Message


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'nick', 'excerpt', 'is_hidden', 'created_at']
    list_filter = ['is_hidden', 'format', 'created_at']
    search_fields = ['nick', 'body']
    readonly_fields = ['ip_hash', 'created_at']
    actions = ['hide', 'unhide']

    @admin.display(description='treść')
    def excerpt(self, obj):
        return obj.body[:60]

    @admin.action(description='Ukryj wybrane wiadomości')
    def hide(self, request, queryset):
        queryset.update(is_hidden=True, hidden_by=request.user)

    @admin.action(description='Przywróć wybrane wiadomości')
    def unhide(self, request, queryset):
        queryset.update(is_hidden=False, hidden_by=None)
