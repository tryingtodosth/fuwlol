"""Add the Ochota-campus domains that migration 0002 predates: Chemia UW, WUM, and the
Biocentrum Ochota institutes.

0002 already ran everywhere, and a migration does not re-run — so growing
`trust.TRUSTED_DOMAINS_SEED` alone would only reach a database created after the change.
This re-runs the same idempotent seed, which is why it is safe to keep doing:
`get_or_create` touches nothing that already exists, so an owner who deactivated
`mimuw.edu.pl` or renamed an institution in the admin keeps those edits.

**Every future addition to the seed needs its own migration like this one.** There is no
signal that re-seeds on deploy, deliberately — a list that decides who may hide content
should change when somebody writes a migration, not when a process restarts.
"""
from django.db import migrations

from accounts.trust import TRUSTED_DOMAINS_SEED


def seed(apps, schema_editor):
    TrustedDomain = apps.get_model('accounts', 'TrustedDomain')
    for domain, institution, kind, match_subdomains, is_active in TRUSTED_DOMAINS_SEED:
        TrustedDomain.objects.get_or_create(domain=domain, defaults={
            'institution': institution, 'kind': kind,
            'match_subdomains': match_subdomains, 'is_active': is_active})


def unseed(apps, schema_editor):
    """Reverse only what THIS migration introduced, and only while it is untouched.

    A blanket delete would take out rows 0002 seeded and anything the owner added by hand.
    A row somebody has since edited (renamed, switched off) is left alone: that edit is a
    decision, and a reverse migration is not the place to discard one."""
    TrustedDomain = apps.get_model('accounts', 'TrustedDomain')
    for domain, institution, kind, match_subdomains, is_active in ADDED_HERE:
        TrustedDomain.objects.filter(
            domain=domain, institution=institution, kind=kind,
            match_subdomains=match_subdomains, is_active=is_active).delete()


# Frozen: what this migration adds, so the reverse stays correct when the seed grows again.
ADDED_HERE = [
    ('chem.uw.edu.pl', 'Wydział Chemii UW', 'uw', True, True),
    ('wum.edu.pl', 'Warszawski Uniwersytet Medyczny', 'other', True, True),
    ('icho.edu.pl', 'IChO PAN', 'pan', True, True),
    ('ibb.waw.pl', 'IBB PAN', 'pan', True, True),
    ('ibib.waw.pl', 'IBIB PAN', 'pan', True, True),
    ('nencki.edu.pl', 'Instytut Nenckiego PAN', 'pan', True, True),
    ('imdik.pan.pl', 'IMDiK PAN', 'pan', True, True),
    ('iimcb.gov.pl', 'MIBMiK', 'pan', True, True),
]


class Migration(migrations.Migration):
    dependencies = [('accounts', '0003_profile_reputation')]
    operations = [migrations.RunPython(seed, unseed)]
