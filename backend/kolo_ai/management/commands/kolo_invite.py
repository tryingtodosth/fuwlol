"""Invite a person to the Koło from the shell — the way the FIRST manager gets in, since the
panel needs a manager to send invitations.

    manage.py kolo_invite adres@student.uw.edu.pl --name "Imię Nazwisko" --manager [--print-link]

--manager sets `can_manage` (approves members, runs votes, posts status). --print-link prints the
link instead of mailing it (for a box without SMTP, or to hand it over in person)."""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from kolo_ai import rules
from kolo_ai.models import LoginLink, Member, MemberAction


class Command(BaseCommand):
    help = 'Zaproś osobę do Koła AI (pierwszy zarządzający wchodzi tędy).'

    def add_arguments(self, p):
        p.add_argument('email')
        p.add_argument('--name', required=True)
        p.add_argument('--affiliation', choices=[a for a, _ in Member.AFFILIATIONS], default=Member.STUDENT)
        p.add_argument('--role', choices=[r for r, _ in Member.ROLES], default=Member.CZLONEK)
        p.add_argument('--manager', action='store_true')
        p.add_argument('--zarzad', action='store_true')
        p.add_argument('--funkcja', default='')
        p.add_argument('--print-link', action='store_true')

    def handle(self, email, name, affiliation, role, manager, zarzad, funkcja, print_link, **_):
        e = rules.normalize_email(email)
        if e is None:
            raise CommandError('Niepoprawny adres.')
        with transaction.atomic():
            m = Member.objects.filter(email=e).first() or Member(email=e)
            if m.pk and m.status not in (Member.PENDING_EMAIL, Member.INVITED):
                m.can_manage, m.zarzad, m.funkcja = manager or m.can_manage, zarzad or m.zarzad, funkcja or m.funkcja
                m.save(update_fields=['can_manage', 'zarzad', 'funkcja'])
                self.stdout.write(f'{e} już jest w Kole ({m.get_status_display()}); zaktualizowano uprawnienia.')
                return
            m.name, m.affiliation, m.role, m.status = name, affiliation, role, Member.INVITED
            m.can_manage, m.zarzad, m.funkcja = manager, zarzad, funkcja
            m.save()
            MemberAction.objects.create(member=m, action='invite', to_status=Member.INVITED, reason='manage.py kolo_invite')
            problem = rules.admission_problem(m, role)
            if problem:
                raise CommandError(problem)
            link = rules.make_link(m, LoginLink.INVITE_VALID_FOR)
            if print_link:
                self.stdout.write(link)
            else:
                rules.mail(e, 'zaproszenie', f'Dzień dobry,\n\nzaproszenie do Koła AI. Kliknij, żeby je przyjąć:\n\n{link}\n\nLink działa 7 dni.')
                self.stdout.write(f'Wysłano zaproszenie na {e}.')
