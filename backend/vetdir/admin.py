"""The directory in the admin: list and unlist, nothing else (VETDIR-S1 contract 1). The owners'
requests have no admin at all — no list, no export: they are the clinic's to read, through its key,
and they are blanked by `rules.sweep`. A listing is never deleted here (root rule 6); unlisting is
the takedown."""
from django.contrib import admin
from django.utils import timezone

from . import rules
from .models import Listing


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ['public_id', 'clinic_name', 'town', 'status', 'is_public', 'created_at',
                    'confirmed_at', 'seen_at']
    list_filter = ['status', 'source']
    search_fields = ['public_id', 'card__name', 'card__town']
    readonly_fields = ['public_id', 'email', 'locale', 'source', 'consent_version', 'status', 'card',
                       'created_at', 'confirmed_at', 'unlisted_at', 'seen_at', 'mailed_at']
    exclude = ['key_hash']
    actions = ['unlist']

    @admin.display(description='nazwa')
    def clinic_name(self, obj):
        return obj.card.get('name', '')

    @admin.display(description='miejscowość')
    def town(self, obj):
        return obj.card.get('town', '')

    @admin.display(boolean=True, description='publiczna')
    def is_public(self, obj):
        return rules.is_public(obj)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description='Wycofaj z katalogu (na prośbę lub z urzędu)')
    def unlist(self, request, queryset):
        queryset.exclude(status='unlisted').update(status='unlisted', unlisted_at=timezone.now())
