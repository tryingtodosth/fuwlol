"""`manage.py vetdir_seed_examples [--clear]` — Amendment 1 of VETDIR-S1: example data, so the
directory's screens can be seen without a real clinic.

Five fictional listings under fixed ids (`EXAMPLE_IDS`, `example-0001` … `example-0005`) across the
register types, species and hours shapes (a lunch break, a closed weekday, a Saturday morning,
around the clock), one phone-only, the out-of-hours notes; and for `example-0001` a request in every
status. Every row carries `example = True`: the public card says `example: true` and the page draws
"an example, not a real clinic"; a request to an example listing is answered 202 and kept and
mailed nowhere; a seeded request is never mailed. The people are the demo clinic's
(`docs/vet/use-cases-research/capability-map.md` in the medapp repository), the clinics invented,
the addresses say they are examples, the e-mails are on `.example` and the phones in the
`+48 000 000 …` range no subscriber holds.

**Never run by a migration or at start-up**; whether a server carries it is the coordinator's call
(the medapp repository's `docs/work/VETDIR-S1.md`). Idempotent: a second run leaves the same rows
(the requests re-made with fresh days). `--clear` deletes exactly the rows it made — example
listings under these ids and their requests — and nothing else; a real listing under one of these
ids (it cannot happen by chance: real ids are random) stops the command.
"""
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from vetdir import rules
from vetdir.models import Listing, VisitRequest

EXAMPLE_IDS = ('example-0001', 'example-0002', 'example-0003', 'example-0004', 'example-0005')
_WEEK = [0, 1, 2, 3, 4]


def _win(days, open_, close):
    return [{'weekday': d, 'open': open_, 'close': close} for d in days]


EXAMPLES = [
    ('example-0001', 'recepcja@lipowa.example', {
        'name': 'Przychodnia Weterynaryjna „Lipowa” (PRZYKŁAD)', 'register_type': 'przychodnia',
        'address': 'ul. Przykładowa 2, 00-000 Przykładowo (adres przykładowy)', 'town': 'Warszawa',
        'phone': '+48 000 000 201',
        # A lunch break on weekdays and a Saturday morning.
        'hours': _win(_WEEK, '08:00', '12:00') + _win(_WEEK, '13:00', '18:00') + _win([5], '09:00', '13:00'),
        'species': ['dog', 'cat', 'rabbit', 'rodent'], 'services': ['consultation', 'vaccination', 'microchipping', 'pet_passport', 'dentistry'],
        'languages': ['pl', 'uk', 'en'], 'out_of_hours': 'on_call_phone', 'out_of_hours_phone': '+48 000 000 202',
        'accepts_requests': True}),
    ('example-0002', 'recepcja@kasztan.example', {
        'name': 'Gabinet Weterynaryjny „Pod Kasztanem” (PRZYKŁAD)', 'register_type': 'gabinet',
        'address': 'ul. Przykładowa 3, 00-000 Przykładowo (adres przykładowy)', 'town': 'Kraków',
        'phone': '+48 000 000 211',
        # Closed on Wednesdays.
        'hours': _win([0, 1, 3, 4], '10:00', '18:00'),
        'species': ['dog', 'cat'], 'services': ['consultation', 'vaccination'],
        'languages': ['pl'], 'out_of_hours': 'none', 'out_of_hours_phone': '',
        'accepts_requests': False}),
    ('example-0003', 'recepcja@stajnia.example', {
        'name': 'Lecznica dla Koni „Stajnia Testowa” (PRZYKŁAD)', 'register_type': 'lecznica',
        'address': 'ul. Przykładowa 4, 00-000 Przykładowo (adres przykładowy)', 'town': 'Poznań',
        'phone': '+48 000 000 221',
        'hours': _win([0, 1, 2, 3, 4, 5], '07:00', '15:00'),
        'species': ['horse', 'farm'], 'services': ['consultation', 'vaccination', 'imaging', 'home_visits'],
        'languages': ['pl', 'de'], 'out_of_hours': 'other_clinic', 'out_of_hours_phone': '+48 000 000 222',
        'accepts_requests': True}),
    ('example-0004', 'recepcja@calodobowa.example', {
        'name': 'Klinika Weterynaryjna „Całodobowa” (PRZYKŁAD)', 'register_type': 'klinika',
        'address': 'ul. Przykładowa 5, 00-000 Przykładowo (adres przykładowy)', 'town': 'Gdańsk',
        'phone': '+48 000 000 231',
        'hours': _win([0, 1, 2, 3, 4, 5, 6], '00:00', '23:59'),
        'species': ['dog', 'cat', 'rabbit', 'bird', 'reptile', 'other'],
        'services': ['consultation', 'surgery', 'imaging', 'laboratory', 'hospitalisation'],
        'languages': ['pl', 'en', 'uk', 'ru'], 'out_of_hours': 'open_24h', 'out_of_hours_phone': '',
        'accepts_requests': True}),
    ('example-0005', 'recepcja@ptasi.example', {
        'name': 'Gabinet „Ptasi Azyl” (PRZYKŁAD)', 'register_type': 'gabinet',
        'address': 'ul. Przykładowa 6, 00-000 Przykładowo (adres przykładowy)', 'town': 'Lublin',
        'phone': '+48 000 000 241',
        'hours': _win([1, 2, 3, 4], '14:00', '20:00'),
        'species': ['bird', 'reptile'], 'services': ['consultation'],
        'languages': ['pl'], 'out_of_hours': 'none', 'out_of_hours_phone': '',
        'accepts_requests': False}),
]

# (status, owner, phone, e-mail, species, animal, day offset, part, sentence)
REQUESTS = [
    ('pending_email', 'Katarzyna Przykładowa', '+48 000 000 101', 'k.przykladowa@owners.example', 'cat', 'Kicia', 3, 'evening', 'Kontrola po zabiegu.'),
    ('requested', 'Olena Demczenko', '+48 000 000 102', 'o.demczenko@owners.example', 'cat', 'Mruczek', 4, 'morning', 'Szczepienie przypominające.'),
    ('requested', 'Jan Testowy', '+48 000 000 103', 'j.testowy@owners.example', 'rabbit', 'Uszatek', 5, 'any', 'Nie je od wczoraj, prosimy o termin.'),
    ('confirmed', 'Schronisko dla Zwierząt „Przykładowe” (DEMO)', '+48 000 000 100', 'schronisko@owners.example', 'dog', 'Burek', 6, 'afternoon', 'Czipowanie przed adopcją.'),
    ('declined', 'Katarzyna Przykładowa', '+48 000 000 101', 'k.przykladowa@owners.example', 'dog', 'Luna', 2, 'morning', ''),
    ('cancelled', 'Olena Demczenko', '+48 000 000 102', 'o.demczenko@owners.example', 'rodent', 'Pestka', 7, 'evening', 'Pazurki.'),
]


class Command(BaseCommand):
    help = 'Create (or with --clear remove) the vetdir example listings and requests (Amendment 1).'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='remove exactly the example rows this command made')

    def handle(self, *args, **options):
        clash = Listing.objects.filter(public_id__in=EXAMPLE_IDS, example=False)
        if clash.exists():
            raise CommandError('A real listing holds an example id: ' + ', '.join(clash.values_list('public_id', flat=True)))
        if options['clear']:
            mine = Listing.objects.filter(public_id__in=EXAMPLE_IDS, example=True)
            n_req = VisitRequest.objects.filter(listing__in=mine, example=True).count()
            n = mine.count()
            mine.delete()
            self.stdout.write(f'Usunięto przykładowe wpisy: {n}, przykładowe prośby: {n_req}.')
            return
        now = timezone.now()
        with transaction.atomic():
            for public_id, email, data in EXAMPLES:
                card, problems = rules.clean_card(data)
                if problems:
                    raise CommandError(f'{public_id}: {problems}')
                Listing.objects.update_or_create(public_id=public_id, defaults={
                    # A key nobody holds: an example is changed only by this command.
                    'key_hash': rules.hash_key(rules.new_key()), 'email': email, 'locale': 'pl',
                    'source': 'medapp', 'consent_version': rules.CONSENT_VERSION, 'status': 'listed',
                    'card': card, 'created_at': now, 'confirmed_at': now, 'unlisted_at': None,
                    'seen_at': now, 'mailed_at': None, 'example': True,
                })
            first = Listing.objects.get(public_id=EXAMPLE_IDS[0])
            VisitRequest.objects.filter(listing=first, example=True).delete()
            today = rules.clinic_today(now)
            for i, (st, owner, phone, mail, species, animal, offset, part, reason) in enumerate(REQUESTS):
                day = today + timedelta(days=offset)
                start = None
                if st == 'confirmed':
                    start = timezone.make_aware(datetime.combine(day, datetime.min.time()).replace(hour=15), rules.CLINIC_TZ)
                VisitRequest.objects.create(
                    public_id=f'example-r{i + 1:03d}', listing=first, status=st, owner_name=owner, phone=phone,
                    email=mail, species=species, animal_name=animal, day=day, part_of_day=part, reason=reason,
                    locale='pl', created_at=now - timedelta(hours=6 - i),
                    email_confirmed_at=None if st == 'pending_email' else now - timedelta(hours=5 - i),
                    decided_at=now if st in ('confirmed', 'declined', 'cancelled') else None,
                    start=start, example=True)
        self.stdout.write(f'Przykładowe wpisy: {len(EXAMPLES)} ({", ".join(EXAMPLE_IDS)}); '
                          f'przykładowe prośby: {len(REQUESTS)} przy {EXAMPLE_IDS[0]}.')
