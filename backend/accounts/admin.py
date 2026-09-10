from django.contrib import admin

from .models import EmailVerification, Profile, TrustedDomain


@admin.register(TrustedDomain)
class TrustedDomainAdmin(admin.ModelAdmin):
    list_display = ['domain', 'institution', 'kind', 'match_subdomains', 'is_active', 'verified_count']
    list_editable = ['is_active']
    list_filter = ['kind', 'is_active']
    search_fields = ['domain', 'institution']

    @admin.display(description='potwierdzonych kont')
    def verified_count(self, obj):
        return obj.profiles.filter(verified_at__isnull=False).count()


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'affiliation_email', 'affiliation_domain', 'verified_at']
    list_filter = ['affiliation_domain']
    search_fields = ['user__username', 'affiliation_email']
    raw_id_fields = ['user']


@admin.register(EmailVerification)
class EmailVerificationAdmin(admin.ModelAdmin):
    list_display = ['email', 'user', 'created_at', 'used_at']
    search_fields = ['email', 'user__username']
    readonly_fields = ['token', 'created_at']
    raw_id_fields = ['user']
