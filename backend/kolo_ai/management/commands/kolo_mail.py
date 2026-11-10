"""A mailing to the Koło's list: one message per person, each with that person's unsubscribe link.

    manage.py kolo_mail FILE|-                    # dry run: who would get it, nothing is sent
    manage.py kolo_mail FILE|- --send             # send
    manage.py kolo_mail FILE|- --test ADDR        # one copy to ADDR, subject prefixed [TEST]
    manage.py kolo_mail FILE|- --send --extra ADDR [--extra ADDR …]

FILE is plain text: the first line is the subject, the rest the body. `-` reads standard input,
which is how a file from another machine reaches the container (`exec -T api … - < mail.txt`).
`[LINK_REZYGNACJI]` in the body becomes the person's link (for an `--extra` address, its whole line
becomes "reply WYPISZ"); without it, a line with the link is appended. Every copy also carries `List-Unsubscribe` (one-click, RFC 8058, and mailto).

Recipients: `rules.mailing_recipients()` — confirmed addresses (member, pending_approval,
invited) that have not unsubscribed. `--extra` adds addresses outside the register (e.g. the
opiekun); they have no row, so no link, and their copy says to reply WYPISZ instead. An extra
address that IS in the register is treated as a row: unsubscribed means skipped.
"""
import sys
import time
from email.utils import parseaddr

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.core.management.base import BaseCommand, CommandError

from kolo_ai import rules
from kolo_ai.models import Member

PLACEHOLDER = '[LINK_REZYGNACJI]'
NO_LINK = 'Nie chcesz więcej maili? Odpowiedz na tego maila słowem WYPISZ.'


def personal_body(body, member):
    if member is None:  # no row, no link: the line that would carry it says to reply instead
        if PLACEHOLDER in body:
            return '\n'.join(NO_LINK if PLACEHOLDER in line else line for line in body.split('\n'))
        return body.rstrip('\n') + '\n' + NO_LINK + '\n'
    url = rules.unsubscribe_url(member)
    if PLACEHOLDER in body:
        return body.replace(PLACEHOLDER, url)
    return body.rstrip('\n') + f'\nNie chcesz więcej maili? Kliknij: {url}\n'


def headers_for(member):
    mailto = f'<mailto:{settings.FUWLOL_CONTACT_EMAIL}?subject=WYPISZ>'
    if member is None:
        return {'List-Unsubscribe': mailto}
    return {'List-Unsubscribe': f'<{rules.one_click_url(member)}>, {mailto}',
            'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click'}


class Command(BaseCommand):
    help = 'Wyślij ogłoszenie do listy Koła AI (każdy dostaje własny link rezygnacji).'

    def add_arguments(self, p):
        p.add_argument('file', help='plik tekstowy (1. linia = temat) albo - dla stdin')
        p.add_argument('--send', action='store_true', help='naprawdę wyślij (bez tego: próba na sucho)')
        p.add_argument('--test', metavar='ADDR', help='jedna kopia na ten adres, z [TEST] w temacie')
        p.add_argument('--extra', metavar='ADDR', action='append', default=[], help='dodatkowy adres spoza ewidencji')
        p.add_argument('--pause', type=float, default=1.0, help='sekundy między wiadomościami')

    def handle(self, file, send, test, extra, pause, **_):
        text = sys.stdin.read() if file == '-' else open(file, encoding='utf-8').read()
        subject, _, body = text.partition('\n')
        subject, body = subject.strip(), body.lstrip('\n')
        if not subject or not body.strip():
            raise CommandError('Pierwsza linia to temat, dalej treść; jedno z nich jest puste.')

        if test:
            targets = [(test.strip().lower(), Member.objects.filter(email=test.strip().lower()).first())]
            subject = '[TEST] ' + subject
        else:
            rows = list(rules.mailing_recipients())
            known = {m.email for m in rows}
            targets = [(m.email, m) for m in rows]
            for a in (x.strip().lower() for x in extra):
                if a in known:
                    continue
                row = Member.objects.filter(email=a).first()
                if row is not None and row.mail_opt_out_at is not None:
                    self.stdout.write(f'SKIP {a} (wypisany)')
                    continue
                targets.append((a, row))
                known.add(a)

        self.stdout.write(f'RECIPIENTS {len(targets)}  SUBJECT {subject}')
        if not (send or test):
            for a, m in targets:
                self.stdout.write(f'WOULD {a}' + ('' if m else ' (spoza ewidencji, bez linku)'))
            self.stdout.write('Próba na sucho; dodaj --send, żeby wysłać.')
            return

        name, addr = parseaddr(settings.DEFAULT_FROM_EMAIL)
        sender = f'Koło AI <{addr or "no-reply@fuw.lol"}>'
        conn = get_connection()
        ok = fail = 0
        for a, m in targets:
            msg = EmailMessage(subject, personal_body(body, m), sender, [a], connection=conn,
                               reply_to=[settings.FUWLOL_CONTACT_EMAIL], headers=headers_for(m))
            try:
                msg.send()
                ok += 1
                self.stdout.write(f'SENT {a}')
            except Exception as e:  # one bad address must not stop the rest
                fail += 1
                self.stdout.write(f'FAIL {a} {e!r}')
            if pause:
                time.sleep(pause)
        self.stdout.write(f'DONE ok={ok} fail={fail}')
