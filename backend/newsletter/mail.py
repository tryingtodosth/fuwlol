"""The one mail the newsletter sends from fuw.lol: the confirmation of a sign-up (models.py).

It goes out from the medapp.net mailbox (OVH, settings.FUWLOL_NEWSLETTER_MAIL), not from fuw.lol's
own relay: the person signed up on medapp.net and the mail must say so in its From line. The
links point at the copy the sign-up came from (settings.FUWLOL_NEWSLETTER_SITES, by `source`),
its `/newsletter` page, with the token in the fragment — a fragment is never sent to a server, so
the token is in no access log and no Referer. The page asks for a press before it calls
`confirm/`, so a mail scanner that opens links confirms nothing.

Plain text, in the person's interface language (en / pl / uk; anything else gets English).
"""
from django.conf import settings
from django.core.mail import EmailMessage, get_connection

from .models import CONFIRM_DAYS, PENDING_DAYS

# The locales MedApp prefixes in its URLs on medapp.net (English is at the bare path).
_PREFIXED = {'pl', 'uk'}

TEXT = {
    'en': {
        'confirm_subject': 'Confirm your medapp.net newsletter sign-up',
        'already_subject': 'Your medapp.net newsletter sign-up',
        'hello': ('Somebody, hopefully you, asked to receive the medapp.net newsletter at this '
                  'address: occasional e-mails about the app for veterinary clinics (news, calls '
                  'for clinics and reviewers).'),
        'confirm': ('To confirm, open this link within {days} days and press the button on the '
                    'page:\n{url}'),
        'not_you': ('If it was not you, ignore this e-mail: an address that is not confirmed is '
                    'deleted within {pending} days and gets nothing more.'),
        'already': 'This address is already on the list, so nothing has changed.',
        'kept': 'The address is kept on fuw.lol only for this newsletter.',
        'unsub': 'To unsubscribe at any time:\n{url}',
    },
    'pl': {
        'confirm_subject': 'Potwierdź zapis na newsletter medapp.net',
        'already_subject': 'Twój zapis na newsletter medapp.net',
        'hello': ('Ktoś, mamy nadzieję, że Ty, poprosił o newsletter medapp.net na ten adres: '
                  'wiadomości od czasu do czasu o aplikacji dla przychodni weterynaryjnych '
                  '(nowości, zaproszenia dla przychodni i recenzentów).'),
        'confirm': ('Aby potwierdzić, otwórz ten link w ciągu {days} dni i naciśnij przycisk na '
                    'stronie:\n{url}'),
        'not_you': ('Jeśli to nie Ty, zignoruj tę wiadomość: niepotwierdzony adres usuwamy w ciągu '
                    '{pending} dni i nic więcej na niego nie wyślemy.'),
        'already': 'Ten adres jest już na liście, więc nic się nie zmieniło.',
        'kept': 'Adres jest przechowywany na fuw.lol wyłącznie na potrzeby tego newslettera.',
        'unsub': 'Aby wypisać się w dowolnej chwili:\n{url}',
    },
    'uk': {
        'confirm_subject': 'Підтвердьте підписку на розсилку medapp.net',
        'already_subject': 'Ваша підписка на розсилку medapp.net',
        'hello': ('Хтось, сподіваємося, що ви, попросив надсилати розсилку medapp.net на цю адресу: '
                  'час від часу листи про застосунок для ветеринарних клінік (новини, запрошення '
                  'для клінік і рецензентів).'),
        'confirm': ('Щоб підтвердити, відкрийте це посилання протягом {days} днів і натисніть кнопку '
                    'на сторінці:\n{url}'),
        'not_you': ('Якщо це були не ви, проігноруйте цей лист: непідтверджену адресу буде видалено '
                    'протягом {pending} днів, і на неї більше нічого не надійде.'),
        'already': 'Ця адреса вже є у списку, тож нічого не змінилося.',
        'kept': 'Адреса зберігається на fuw.lol лише для цієї розсилки.',
        'unsub': 'Щоб відписатися будь-коли:\n{url}',
    },
}


def _lang(row):
    return row.locale if row.locale in TEXT else 'en'


def page_url(row, fragment):
    """The copy's `/newsletter` page in the row's language, with `fragment` after the `#`."""
    site = settings.FUWLOL_NEWSLETTER_SITES.get(row.source, '').rstrip('/')
    prefix = f'/{row.locale}' if row.locale in _PREFIXED else ''
    return f'{site}{prefix}/newsletter#{fragment}'


def unsubscribe_url(row):
    return page_url(row, 'unsubscribe=' + row.unsubscribe_token())


def _send(row, subject, paragraphs):
    cfg = settings.FUWLOL_NEWSLETTER_MAIL
    sign = f'—\nmedapp.net · {cfg["reply_to"]}' if cfg['reply_to'] else '—\nmedapp.net'
    msg = EmailMessage(
        subject=subject,
        body='\n\n'.join(paragraphs + [sign]) + '\n',
        from_email=cfg['from'],
        to=[row.email],
        reply_to=[cfg['reply_to']] if cfg['reply_to'] else None,
        headers={'Auto-Submitted': 'auto-generated',
                 'List-Unsubscribe': f'<{unsubscribe_url(row)}>'},
        # The project's EMAIL_BACKEND (console in DEBUG, locmem under tests, SMTP in production)
        # with the medapp.net mailbox's server and login; the other two backends ignore them.
        connection=get_connection(host=cfg['host'], port=cfg['port'], username=cfg['user'],
                                  password=cfg['password'], use_ssl=cfg['use_ssl'],
                                  use_tls=not cfg['use_ssl'], timeout=20),
    )
    msg.send(fail_silently=False)


def send_confirmation(row):
    t = TEXT[_lang(row)]
    url = page_url(row, 'confirm=' + row.confirm_token())
    _send(row, t['confirm_subject'], [
        t['hello'], t['confirm'].format(days=CONFIRM_DAYS, url=url),
        t['not_you'].format(pending=PENDING_DAYS), t['kept'],
    ])


def send_already(row):
    t = TEXT[_lang(row)]
    _send(row, t['already_subject'], [
        t['hello'], t['already'], t['kept'], t['unsub'].format(url=unsubscribe_url(row)),
    ])
