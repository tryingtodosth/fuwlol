"""The directory's mails, `newsletter/mail.py`'s way: plain text in en / pl / uk (anything else gets
English), from medapp.net's own mailbox (settings.FUWLOL_VETDIR_MAIL, by default the newsletter's),
`Auto-Submitted`, the Message-ID on the sender's domain. Every link points at the copy the row came
from (settings.FUWLOL_VETDIR_SITES, by `source`), its `/vets/confirm` page, with the token in the
FRAGMENT — never sent to a server, so in no access log and no Referer — and that page acts only on
a press, so a mail scanner that opens links confirms and cancels nothing.

Four mails and no more: to the clinic, the link that makes its card public; to the owner, the link
that sends the request, then one mail when the clinic confirmed (with the time staff set and the
clinic's phone) or declined (with the phone). The cancel link is in every owner mail that has
something left to cancel. No mail goes to the clinic per request in S1: the vet app shows them when
it is opened (`docs/work/VETDIR-S1.md`).
"""
from email.utils import make_msgid, parseaddr

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.utils import timezone

from . import rules

_PREFIXED = {'pl', 'uk'}

PART = {
    'en': {'morning': 'in the morning', 'afternoon': 'in the afternoon', 'evening': 'in the evening',
           'any': 'at any time of day'},
    'pl': {'morning': 'rano', 'afternoon': 'po południu', 'evening': 'wieczorem', 'any': 'o dowolnej porze'},
    'uk': {'morning': 'зранку', 'afternoon': 'після обіду', 'evening': 'увечері', 'any': 'у будь-який час'},
}

TEXT = {
    'en': {
        'listing_subject': 'Confirm the public page of {name}',
        'listing_hello': ('This address was given as the e-mail of {name} when its vet app asked for a '
                          'public page in the clinic directory of medapp.net.'),
        'listing_confirm': ('To publish the page, open this link within {days} days and press the button '
                            'on the page:\n{url}'),
        'listing_then': 'Once published, the page is here:\n{page}',
        'listing_not_you': ('If it was not you, ignore this e-mail: nothing is public until the link is '
                            'pressed, and an unconfirmed page is deleted within {pending} days.'),
        'listing_what': ('The page shows what the clinic entered and nothing else; nobody checks it. '
                         'Requests from pet owners are held on a tester service with nobody on call.'),
        'req_subject': 'Confirm your visit request to {clinic}',
        'req_hello': 'You asked {clinic} for a visit for {animal} on {day}, {part}.',
        'req_not_booking': 'This is a request, not a booking: the clinic will answer by e-mail.',
        'req_confirm': ('To send it to the clinic, open this link within {days} days and press the button '
                        'on the page:\n{url}'),
        'req_not_you': ('If it was not you, ignore this e-mail: an unconfirmed request never reaches the '
                        'clinic and its details are erased within {days} days.'),
        'emergency': 'In an emergency, do not wait for an e-mail: phone the clinic, {phone}.',
        'cancel': 'To cancel the request at any time:\n{url}',
        'ok_subject': '{clinic} confirmed your visit',
        'ok_body': '{clinic} confirmed the visit for {animal}: {when} (the clinic\'s time).',
        'ok_phone': 'To change anything, phone the clinic: {phone}.',
        'no_subject': '{clinic} could not take your request',
        'no_body': ('{clinic} could not take your request for {animal} on {day}. Please phone the '
                    'clinic: {phone}.'),
        'tester': ('Requests are held on a tester service at fuw.lol, run by volunteers with nobody on '
                   'call, and erased within {keep} days.'),
    },
    'pl': {
        'listing_subject': 'Potwierdź publiczną stronę: {name}',
        'listing_hello': ('Ten adres podano jako e-mail zakładu {name}, gdy jego aplikacja weterynaryjna '
                          'poprosiła o publiczną stronę w katalogu przychodni medapp.net.'),
        'listing_confirm': ('Aby opublikować stronę, otwórz ten link w ciągu {days} dni i naciśnij przycisk '
                            'na stronie:\n{url}'),
        'listing_then': 'Po publikacji strona będzie tutaj:\n{page}',
        'listing_not_you': ('Jeśli to nie Ty, zignoruj tę wiadomość: nic nie jest publiczne, dopóki link '
                            'nie zostanie naciśnięty, a niepotwierdzoną stronę usuwamy w ciągu {pending} dni.'),
        'listing_what': ('Strona pokazuje to, co wpisał zakład, i nic więcej; nikt tego nie sprawdza. '
                         'Zgłoszenia od opiekunów zwierząt są przechowywane w usłudze testowej, bez dyżuru.'),
        'req_subject': 'Potwierdź prośbę o wizytę: {clinic}',
        'req_hello': 'Poprosiłeś(-aś) {clinic} o wizytę dla: {animal}, dnia {day}, {part}.',
        'req_not_booking': 'To jest prośba, nie rezerwacja: przychodnia odpowie e-mailem.',
        'req_confirm': ('Aby wysłać ją do przychodni, otwórz ten link w ciągu {days} dni i naciśnij przycisk '
                        'na stronie:\n{url}'),
        'req_not_you': ('Jeśli to nie Ty, zignoruj tę wiadomość: niepotwierdzona prośba nie trafia do '
                        'przychodni, a jej dane usuwamy w ciągu {days} dni.'),
        'emergency': 'W nagłym wypadku nie czekaj na e-mail: zadzwoń do przychodni, {phone}.',
        'cancel': 'Aby w dowolnej chwili odwołać prośbę:\n{url}',
        'ok_subject': '{clinic} potwierdza wizytę',
        'ok_body': '{clinic} potwierdza wizytę dla: {animal}: {when} (czas przychodni).',
        'ok_phone': 'Aby coś zmienić, zadzwoń do przychodni: {phone}.',
        'no_subject': '{clinic} nie może przyjąć prośby',
        'no_body': ('{clinic} nie może przyjąć prośby dla: {animal}, dnia {day}. Zadzwoń, proszę, do '
                    'przychodni: {phone}.'),
        'tester': ('Zgłoszenia są przechowywane w usłudze testowej na fuw.lol, prowadzonej przez '
                   'wolontariuszy, bez dyżuru, i usuwane w ciągu {keep} dni.'),
    },
    'uk': {
        'listing_subject': 'Підтвердьте публічну сторінку: {name}',
        'listing_hello': ('Цю адресу вказано як e-mail закладу {name}, коли його ветеринарний застосунок '
                          'попросив публічну сторінку в каталозі клінік medapp.net.'),
        'listing_confirm': ('Щоб опублікувати сторінку, відкрийте це посилання протягом {days} днів і '
                            'натисніть кнопку на сторінці:\n{url}'),
        'listing_then': 'Після публікації сторінка буде тут:\n{page}',
        'listing_not_you': ('Якщо це були не ви, проігноруйте цей лист: нічого не стає публічним, доки не '
                            'натиснуто посилання, а непідтверджену сторінку буде видалено протягом {pending} днів.'),
        'listing_what': ('Сторінка показує те, що ввів заклад, і нічого більше; ніхто цього не перевіряє. '
                         'Запити від власників тварин зберігаються в тестовому сервісі без чергування.'),
        'req_subject': 'Підтвердьте запит на візит: {clinic}',
        'req_hello': 'Ви попросили {clinic} про візит для: {animal}, {day}, {part}.',
        'req_not_booking': 'Це запит, а не бронювання: клініка відповість електронним листом.',
        'req_confirm': ('Щоб надіслати його клініці, відкрийте це посилання протягом {days} днів і '
                        'натисніть кнопку на сторінці:\n{url}'),
        'req_not_you': ('Якщо це були не ви, проігноруйте цей лист: непідтверджений запит не потрапляє до '
                        'клініки, а його дані буде стерто протягом {days} днів.'),
        'emergency': 'У невідкладному випадку не чекайте листа: зателефонуйте до клініки, {phone}.',
        'cancel': 'Щоб будь-коли скасувати запит:\n{url}',
        'ok_subject': '{clinic} підтверджує візит',
        'ok_body': '{clinic} підтверджує візит для: {animal}: {when} (час клініки).',
        'ok_phone': 'Щоб щось змінити, зателефонуйте до клініки: {phone}.',
        'no_subject': '{clinic} не може прийняти запит',
        'no_body': ('{clinic} не може прийняти запит для: {animal}, {day}. Будь ласка, зателефонуйте до '
                    'клініки: {phone}.'),
        'tester': ('Запити зберігаються в тестовому сервісі на fuw.lol, який ведуть волонтери, без '
                   'чергування, і стираються протягом {keep} днів.'),
    },
}


def _lang(locale):
    return locale if locale in TEXT else 'en'


def site_url(source, locale, path):
    """The copy's page `path` in the row's language (English, like medapp.net's base, unprefixed)."""
    site = settings.FUWLOL_VETDIR_SITES.get(source, '').rstrip('/')
    prefix = f'/{locale}' if locale in _PREFIXED else ''
    return f'{site}{prefix}{path}'


def confirm_url(source, locale, fragment):
    return site_url(source, locale, '/vets/confirm') + '#' + fragment


def cancel_url(req):
    return confirm_url(req.listing.source, req.locale, 'cancel=' + req.cancel_token())


class ExampleMail(Exception):
    """Raised instead of mailing a fictional address (Amendment 1); never reached by the views,
    which check `example` first — this is the second look."""


def _send(to, subject, paragraphs):
    if to.endswith('.example'):
        raise ExampleMail(to)
    cfg = settings.FUWLOL_VETDIR_MAIL
    sign = f'—\nmedapp.net · {cfg["reply_to"]}' if cfg['reply_to'] else '—\nmedapp.net'
    domain = parseaddr(cfg['from'])[1].rpartition('@')[2] or 'medapp.net'
    msg = EmailMessage(
        subject=subject,
        body='\n\n'.join(paragraphs + [sign]) + '\n',
        from_email=cfg['from'],
        to=[to],
        reply_to=[cfg['reply_to']] if cfg['reply_to'] else None,
        headers={'Auto-Submitted': 'auto-generated', 'Message-ID': make_msgid(domain=domain)},
        connection=get_connection(host=cfg['host'], port=cfg['port'], username=cfg['user'],
                                  password=cfg['password'], use_ssl=cfg['use_ssl'],
                                  use_tls=not cfg['use_ssl'], timeout=20),
    )
    msg.send(fail_silently=False)


def send_listing_confirmation(listing):
    t = TEXT[_lang(listing.locale)]
    name = listing.card.get('name', '')
    url = confirm_url(listing.source, listing.locale, 'listing=' + listing.confirm_token())
    page = site_url(listing.source, listing.locale, f'/vets/{listing.public_id}')
    _send(listing.email, t['listing_subject'].format(name=name), [
        t['listing_hello'].format(name=name),
        t['listing_confirm'].format(days=rules.LISTING_CONFIRM_DAYS, url=url),
        t['listing_then'].format(page=page),
        t['listing_not_you'].format(pending=rules.LISTING_PENDING_DAYS),
        t['listing_what'],
    ])


def _owner_facts(req):
    lang = _lang(req.locale)
    card = req.listing.card
    return lang, TEXT[lang], {
        'clinic': card.get('name', ''), 'phone': card.get('phone', ''), 'animal': req.animal_name,
        'day': req.day.isoformat(), 'part': PART[lang].get(req.part_of_day, req.part_of_day),
    }


def send_request_confirmation(req):
    lang, t, f = _owner_facts(req)
    url = confirm_url(req.listing.source, req.locale, 'confirm=' + req.confirm_token())
    _send(req.email, t['req_subject'].format(**f), [
        t['req_hello'].format(**f),
        t['req_not_booking'],
        t['req_confirm'].format(days=rules.REQUEST_UNCONFIRMED_DAYS, url=url),
        t['req_not_you'].format(days=rules.REQUEST_UNCONFIRMED_DAYS),
        t['emergency'].format(**f),
        t['cancel'].format(url=cancel_url(req)),
        t['tester'].format(keep=rules.REQUEST_KEEP_DAYS),
    ])


def send_confirmed(req):
    lang, t, f = _owner_facts(req)
    when = timezone.localtime(req.start, rules.CLINIC_TZ).strftime('%Y-%m-%d %H:%M')
    _send(req.email, t['ok_subject'].format(**f), [
        t['ok_body'].format(when=when, **f),
        t['ok_phone'].format(**f),
        t['cancel'].format(url=cancel_url(req)),
        t['tester'].format(keep=rules.REQUEST_KEEP_DAYS),
    ])


def send_declined(req):
    lang, t, f = _owner_facts(req)
    _send(req.email, t['no_subject'].format(**f), [
        t['no_body'].format(**f),
        t['tester'].format(keep=rules.REQUEST_KEEP_DAYS),
    ])
