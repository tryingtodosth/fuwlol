"""Seed the curated domain list and give every pre-existing user a Profile row.

Only rows that do not exist yet are created, so the owner's later edits in the admin
(deactivating a domain, renaming an institution) survive a re-run."""
from django.db import migrations

from accounts.trust import TRUSTED_DOMAINS_SEED


def seed(apps, schema_editor):
    TrustedDomain = apps.get_model('accounts', 'TrustedDomain')
    Profile = apps.get_model('accounts', 'Profile')
    User = apps.get_model('auth', 'User')
    for domain, institution, kind, match_subdomains, is_active in TRUSTED_DOMAINS_SEED:
        TrustedDomain.objects.get_or_create(domain=domain, defaults={
            'institution': institution, 'kind': kind,
            'match_subdomains': match_subdomains, 'is_active': is_active})
    # Users registered before this app existed: the post_save signal never ran for them.
    for user in User.objects.filter(profile__isnull=True):
        Profile.objects.get_or_create(user=user)


class Migration(migrations.Migration):
    dependencies = [('accounts', '0001_initial')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
