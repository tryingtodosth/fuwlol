import csv

from django.contrib import admin
from django.http import HttpResponse
from django.utils import timezone

from .mail import unsubscribe_url
from .models import Subscriber


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    """The list. The only mail sent from here is the confirmation (mail.py); an issue is sent by
    whoever exports the active rows, and every issue carries the row's own unsubscribe link."""
    list_display = ['email', 'status', 'locale', 'source', 'consent_version', 'subscribed_at',
                    'confirmed_at', 'unsubscribed_at']
    list_filter = ['status', 'source', 'locale', 'consent_version']
    search_fields = ['email']
    readonly_fields = ['email', 'locale', 'source', 'consent_version', 'status', 'subscribed_at',
                       'confirmed_at', 'unsubscribed_at', 'mailed_at']
    actions = ['export_active', 'unsubscribe']

    @admin.action(description='Eksportuj potwierdzone adresy z linkiem do wypisania (CSV)')
    def export_active(self, request, queryset):
        resp = HttpResponse(content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = 'attachment; filename="newsletter-medapp.csv"'
        w = csv.writer(resp)
        w.writerow(['email', 'locale', 'confirmed_at', 'unsubscribe_url'])
        for s in queryset.filter(status='active'):
            w.writerow([s.email, s.locale, s.confirmed_at.date().isoformat() if s.confirmed_at else '',
                        unsubscribe_url(s)])
        return resp

    @admin.action(description='Wypisz (na prośbę osoby)')
    def unsubscribe(self, request, queryset):
        queryset.exclude(status='unsubscribed').update(status='unsubscribed', unsubscribed_at=timezone.now())
