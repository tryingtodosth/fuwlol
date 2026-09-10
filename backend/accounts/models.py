"""fuw.lol — accounts.

Two tiers of privilege live here, named the same way everywhere in the code:

* ``trusted`` — somebody who has CONFIRMED an e-mail address at one of the institutions
  around the Faculty (FUW, UW, the PAN physics institutes — `TrustedDomain`). They get
  the moderation board: hide, restore, and the nuclear option.
* ``staff`` — Django's `is_staff`, the real administration/moderation. Only they can look
  at nuked content or restore it.

`accounts.trust.is_trusted(user)` is the one place that answers "is this person trusted";
nothing else should re-derive it from these fields.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

KIND_CHOICES = [('fuw', 'Wydział Fizyki UW'), ('uw', 'Uniwersytet Warszawski'),
                ('pan', 'Instytuty PAN i pokrewne'), ('other', 'Inne')]


class TrustedDomain(models.Model):
    """An e-mail domain whose owners we take on trust. Seeded by migration 0002 from
    `accounts.trust.TRUSTED_DOMAINS_SEED`; curated afterwards in the admin (`is_active`
    is the switch — a deactivated domain stops granting trust to everybody on it, at once)."""
    domain = models.CharField(max_length=120, unique=True, help_text='małymi literami, bez @')
    institution = models.CharField(max_length=160)
    kind = models.CharField(max_length=8, choices=KIND_CHOICES, default='other')
    # fuw.edu.pl → also okwf.fuw.edu.pl, igf.fuw.edu.pl, …  Off for uw.edu.pl on purpose:
    # matching its subdomains would admit every unit of the university.
    match_subdomains = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['institution', 'domain']

    def __str__(self):
        return f'{self.domain} ({self.institution})'

    def save(self, *args, **kwargs):
        self.domain = self.domain.strip().lower().lstrip('.')
        super().save(*args, **kwargs)


class Profile(models.Model):
    """One per user, created by the post_save signal below (and get_or_create'd defensively
    in `trust.is_trusted`, since users registered before this app existed have no row)."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name='profile', on_delete=models.CASCADE)
    affiliation_email = models.EmailField(blank=True)
    affiliation_domain = models.ForeignKey(TrustedDomain, null=True, blank=True, on_delete=models.SET_NULL,
                                           related_name='profiles')
    verified_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.user.username


def new_token():
    return secrets.token_urlsafe(32)


class EmailVerification(models.Model):
    """A confirmation link sent to an institutional address. Valid 24 h, single use;
    requesting a new one deletes the user's older unused ones."""
    VALID_FOR = timedelta(hours=24)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='email_verifications', on_delete=models.CASCADE)
    email = models.EmailField()
    token = models.CharField(max_length=64, unique=True, default=new_token)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.email} ({self.user.username})'

    @property
    def is_valid(self):
        return self.used_at is None and self.created_at > timezone.now() - self.VALID_FOR


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def _ensure_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)
