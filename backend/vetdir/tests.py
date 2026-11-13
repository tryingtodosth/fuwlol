"""What the directory's endpoints, its mails and its sweep promise (VETDIR-S1). `test.md` lists this
suite. Mail is locmem; the throttle cache is cleared per test."""
import re
from datetime import date, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from . import rules
from . import mail as vd_mail
from .models import Listing, VisitRequest

API = '/api/vetdir/'
ORIGIN = 'https://medapp.net'
KEY = 'HTTP_X_VETDIR_KEY'


def card(**kw):
    c = {
        'name': 'Przychodnia Demo', 'register_type': 'przychodnia', 'address': 'ul. Testowa 1',
        'town': 'Warszawa', 'phone': '+48 22 000 00 00',
        'hours': [{'weekday': 0, 'open': '09:00', 'close': '17:00'},
                  {'weekday': 2, 'open': '12:00', 'close': '20:00'}],
        'species': ['dog', 'cat'], 'services': ['consultation', 'vaccination'],
        'languages': ['pl', 'uk'], 'out_of_hours': 'other_clinic', 'out_of_hours_phone': '+48 22 111 11 11',
        'accepts_requests': True,
    }
    c.update(kw)
    return c


def frag(body, name):
    m = re.search(r'https://medapp\.net(?:/[a-z]{2})?/vets/confirm#' + name + r'=(\S+)', body)
    return m and m.group(1)


class VetdirCase(TestCase):
    def setUp(self):
        cache.clear()

    # --- calls ---
    def post(self, path, body, origin=ORIGIN, key=None):
        extra = {}
        if origin:
            extra['HTTP_ORIGIN'] = origin
        if key:
            extra[KEY] = key
        return self.client.post(API + path, body, content_type='application/json', **extra)

    def put(self, path, body, key, origin=ORIGIN):
        return self.client.put(API + path, body, content_type='application/json', HTTP_ORIGIN=origin, **{KEY: key})

    def get(self, path, key=None, origin=ORIGIN):
        extra = {'HTTP_ORIGIN': origin} if origin else {}
        if key:
            extra[KEY] = key
        return self.client.get(API + path, **extra)

    def list_clinic(self, **kw):
        body = {'card': card(**kw), 'email': 'Klinika@Example.org', 'consent_version': rules.CONSENT_VERSION,
                'locale': 'pl'}
        r = self.post('listings/', body)
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def listed(self, **kw):
        out = self.list_clinic(**kw)
        token = frag(mail.outbox[-1].body, 'listing')
        self.assertEqual(self.post('listings/confirm/', {'token': token}).status_code, 200)
        return out['id'], out['key']

    def ask(self, lid, **kw):
        body = {'owner_name': 'Katarzyna Przykładowa', 'phone': '600 000 000', 'email': 'Owner@Example.org',
                'species': 'cat', 'animal_name': 'Kicia', 'day': rules.clinic_today().isoformat(),
                'part_of_day': 'evening', 'reason': 'Kontrola po zabiegu.', 'locale': 'pl'}
        body.update(kw)
        return self.post(f'listings/{lid}/requests/', body)

    def requested(self, lid, **kw):
        self.assertEqual(self.ask(lid, **kw).status_code, 202)
        token = frag(mail.outbox[-1].body, 'confirm')
        self.assertEqual(self.post('requests/confirm/', {'token': token}).status_code, 200)
        return VisitRequest.objects.order_by('-pk').first()


class MirroredConstantsTests(TestCase):
    """The literals MedApp's `src/lib/vetdir/api.ts` mirrors and its `vetdir-check` group A pins."""

    def test_the_vocabularies_and_limits(self):
        self.assertEqual(rules.CONSENT_VERSION, 'vetdir-2026-11-13')
        self.assertEqual(rules.REGISTER_TYPES, ('gabinet', 'przychodnia', 'lecznica', 'klinika'))
        self.assertEqual(rules.SPECIES, ('dog', 'cat', 'rabbit', 'rodent', 'bird', 'reptile', 'horse', 'farm', 'other'))
        self.assertEqual(rules.SERVICES, ('consultation', 'vaccination', 'microchipping', 'pet_passport', 'surgery',
                                          'dentistry', 'imaging', 'laboratory', 'hospitalisation', 'home_visits'))
        self.assertEqual(rules.LANGUAGES, ('pl', 'en', 'uk', 'de', 'ru', 'fr', 'es', 'it'))
        self.assertEqual(rules.OUT_OF_HOURS, ('none', 'open_24h', 'on_call_phone', 'other_clinic'))
        self.assertEqual(rules.PARTS_OF_DAY, ('morning', 'afternoon', 'evening', 'any'))
        self.assertEqual(rules.LISTING_STATUSES, ('pending', 'listed', 'unlisted'))
        self.assertEqual(rules.REQUEST_STATUSES, ('pending_email', 'requested', 'confirmed', 'declined', 'cancelled'))
        self.assertEqual(rules.REQUEST_TRANSITIONS, {
            'pending_email': {'requested': 'owner', 'cancelled': 'owner'},
            'requested': {'confirmed': 'clinic', 'declined': 'clinic', 'cancelled': 'owner'},
            'confirmed': {'cancelled': 'owner'},
        })
        self.assertEqual(rules.CARD_KEYS, ('name', 'register_type', 'address', 'town', 'phone', 'hours', 'species',
                                           'services', 'languages', 'out_of_hours', 'out_of_hours_phone',
                                           'accepts_requests'))
        self.assertEqual(rules.REQUEST_KEYS, ('owner_name', 'phone', 'email', 'species', 'animal_name', 'day',
                                              'part_of_day', 'reason', 'locale'))
        self.assertEqual(
            (rules.NAME_MAX, rules.ADDRESS_MAX, rules.TOWN_MAX, rules.PHONE_MAX, rules.EMAIL_MAX,
             rules.OWNER_NAME_MAX, rules.ANIMAL_NAME_MAX, rules.VISIT_REASON_MAX, rules.HOURS_MAX_ENTRIES,
             rules.REQUEST_HORIZON_DAYS, rules.LISTING_IDLE_DAYS, rules.REQUEST_KEEP_DAYS,
             rules.REQUEST_UNCONFIRMED_DAYS, rules.LISTING_CONFIRM_DAYS, rules.KEY_MAX, rules.TOKEN_MAX),
            (120, 200, 80, 40, 254, 80, 60, 300, 14, 60, 180, 30, 2, 7, 128, 200))

    def test_the_vocabulary_is_wums_where_it_is_shared(self):
        from wum.models import HOURS_MAX_ENTRIES, VISIT_REASON_MAX
        self.assertEqual((rules.VISIT_REASON_MAX, rules.HOURS_MAX_ENTRIES), (VISIT_REASON_MAX, HOURS_MAX_ENTRIES))


class NothingAboutTheSenderTests(TestCase):
    def test_the_field_sets_are_pinned(self):
        self.assertEqual({f.name for f in Listing._meta.get_fields()},
                         {'id', 'public_id', 'key_hash', 'email', 'locale', 'source', 'consent_version', 'status',
                          'card', 'created_at', 'confirmed_at', 'unlisted_at', 'seen_at', 'mailed_at', 'requests',
                          'example'})
        self.assertEqual({f.name for f in VisitRequest._meta.get_fields()},
                         {'id', 'public_id', 'listing', 'status', 'owner_name', 'phone', 'email', 'species',
                          'animal_name', 'day', 'part_of_day', 'reason', 'locale', 'created_at',
                          'email_confirmed_at', 'decided_at', 'start', 'blanked_at', 'example'})


class ListingTests(VetdirCase):
    def test_a_listing_is_pending_returns_its_key_once_and_mails_the_clinic(self):
        out = self.list_clinic()
        self.assertEqual(out['status'], 'pending')
        self.assertEqual(out['mail'], 'sent')
        self.assertTrue(rules.ID_RE.fullmatch(out['id']))
        self.assertEqual(len(out['key']), 43)
        row = Listing.objects.get()
        self.assertEqual(row.key_hash, rules.hash_key(out['key']))
        self.assertNotIn(out['key'], str(row.__dict__))
        self.assertEqual(row.email, 'klinika@example.org')
        self.assertEqual(row.card, card())
        m = mail.outbox[0]
        self.assertEqual(m.to, ['klinika@example.org'])
        self.assertEqual(m.from_email, 'medapp.net <info@medapp.net>')
        self.assertEqual(m.extra_headers['Auto-Submitted'], 'auto-generated')
        self.assertIn('https://medapp.net/pl/vets/confirm#listing=', m.body)
        self.assertIn(f'https://medapp.net/pl/vets/{out["id"]}', m.body)
        self.assertNotIn(out['key'], m.body)

    def test_pending_is_not_public_and_confirming_lists_it(self):
        out = self.list_clinic()
        self.assertEqual(self.get(f'listings/{out["id"]}/').status_code, 404)
        token = frag(mail.outbox[-1].body, 'listing')
        r = self.post('listings/confirm/', {'token': token})
        self.assertEqual((r.status_code, r.json()['id']), (200, out['id']))
        self.assertEqual(self.post('listings/confirm/', {'token': token}).status_code, 200)  # again: 200
        r = self.get(f'listings/{out["id"]}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.json()), {'id', 'card', 'example'})
        self.assertIs(r.json()['example'], False)
        self.assertNotIn('klinika@example.org', r.content.decode())
        self.assertNotIn(Listing.objects.get().key_hash, r.content.decode())

    def test_the_confirmation_link_expires_and_a_forged_one_is_unknown(self):
        self.list_clinic()
        token = frag(mail.outbox[-1].body, 'listing')
        with mock.patch('django.core.signing.time.time', return_value=timezone.now().timestamp() + 8 * 86400):
            self.assertEqual(self.post('listings/confirm/', {'token': token}).status_code, 410)
        self.assertEqual(self.post('listings/confirm/', {'token': token + 'x'}).status_code, 404)
        self.assertEqual(self.post('listings/confirm/', {'token': ''}).status_code, 400)
        self.assertEqual(self.post('listings/confirm/', {'token': 'x' * 201}).status_code, 400)

    def test_a_card_is_cleaned_key_by_key_and_unknown_keys_are_dropped(self):
        self.list_clinic(about='Najlepsza klinika w mieście!', price_list='50 zł', photo='x.jpg',
                         species=['cat', 'dog'], languages=['uk', 'pl'])
        stored = Listing.objects.get().card
        self.assertEqual(tuple(stored), rules.CARD_KEYS)
        self.assertEqual(stored['species'], ['dog', 'cat'])  # the vocabulary's order
        self.assertEqual(stored['languages'], ['pl', 'uk'])

    def test_every_refusal_of_a_card_names_its_field(self):
        cases = [
            ({'name': ''}, 'name'), ({'name': 'x' * 121}, 'name'), ({'register_type': 'shop'}, 'register_type'),
            ({'address': ''}, 'address'), ({'town': 'x' * 81}, 'town'), ({'phone': 'call me'}, 'phone'),
            ({'phone': '12345'}, 'phone'), ({'hours': [{'weekday': 7, 'open': '09:00', 'close': '10:00'}]}, 'hours'),
            ({'hours': [{'weekday': 1, 'open': '10:00', 'close': '09:00'}]}, 'hours'),
            ({'hours': [{'weekday': 1, 'open': '09:00', 'close': '12:00'},
                        {'weekday': 1, 'open': '11:00', 'close': '13:00'}]}, 'hours'),
            ({'hours': [{'weekday': 1, 'open': '09:00', 'close': '10:00'}] * 15}, 'hours'),
            ({'species': []}, 'species'), ({'species': ['dragon']}, 'species'), ({'species': ['dog', 'dog']}, 'species'),
            ({'services': ['cheap_neutering']}, 'services'), ({'languages': []}, 'languages'),
            ({'out_of_hours': 'call_112'}, 'out_of_hours'), ({'out_of_hours_phone': 'abc'}, 'out_of_hours_phone'),
            ({'accepts_requests': 'yes'}, 'accepts_requests'), ({'name': 'a\x07b'}, 'name'),
        ]
        for change, field in cases:
            cache.clear()  # a refusal spends the allowance too; this test is about the refusals
            body = {'card': card(**change), 'email': 'k@example.org', 'consent_version': rules.CONSENT_VERSION}
            r = self.post('listings/', body)
            self.assertEqual(r.status_code, 400, (change, r.content))
            self.assertIn(field, r.json(), change)
        for body, field in (({'card': card(), 'email': 'nope', 'consent_version': rules.CONSENT_VERSION}, 'email'),
                            ({'card': card(), 'email': 'k@example.org', 'consent_version': 'old'}, 'consent_version'),
                            ({'card': 'text', 'email': 'k@example.org', 'consent_version': rules.CONSENT_VERSION}, 'card')):
            r = self.post('listings/', body)
            self.assertEqual(r.status_code, 400)
            self.assertIn(field, r.json())
        self.assertFalse(Listing.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_only_a_known_origin_may_list_and_the_honeypot_keeps_nothing(self):
        body = {'card': card(), 'email': 'k@example.org', 'consent_version': rules.CONSENT_VERSION}
        for origin in ('https://evil.example', None):
            r = self.post('listings/', body, origin=origin)
            self.assertEqual(r.status_code, 403)
            self.assertNotIn('Access-Control-Allow-Origin', r)
        r = self.post('listings/', dict(body, website='http://spam.example'))
        self.assertEqual(r.status_code, 201)
        self.assertEqual(set(r.json()), {'ok', 'id', 'key', 'status', 'mail'})
        self.assertFalse(Listing.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_the_key_reads_updates_and_unlists_and_a_wrong_key_is_the_same_404(self):
        lid, key = self.listed()
        r = self.get(f'listings/{lid}/', key=key)
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()['status'], r.json()['public']), ('listed', True))
        self.assertNotIn('email', r.json())
        for wrong in ('x' * 43, key + 'x', 'k' * 200):
            self.assertEqual(self.get(f'listings/{lid}/', key=wrong).status_code, 404)
            self.assertEqual(self.put(f'listings/{lid}/', {'card': card()}, wrong).status_code, 404)
            self.assertEqual(self.post(f'listings/{lid}/unlist/', {}, key=wrong).status_code, 404)
        self.assertEqual(self.get('listings/AAAAAAAAAAAA/', key=key).status_code, 404)
        r = self.put(f'listings/{lid}/', {'card': card(name='Lecznica Nowa', register_type='lecznica')}, key)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.get(f'listings/{lid}/').json()['card']['name'], 'Lecznica Nowa')
        self.assertEqual(self.put(f'listings/{lid}/', {'card': card(name='')}, key).status_code, 400)
        cache.clear()  # ten wrong-key writes above spent the hour's allowance
        r = self.post(f'listings/{lid}/unlist/', {}, key=key)
        self.assertEqual((r.status_code, r.json()['status'], r.json()['public']), (200, 'unlisted', False))
        self.assertEqual(self.get(f'listings/{lid}/').status_code, 404)
        self.assertEqual(self.post(f'listings/{lid}/unlist/', {}, key=key).status_code, 200)  # twice: 200
        self.assertEqual(self.put(f'listings/{lid}/', {'card': card()}, key).status_code, 409)

    def test_the_key_is_compared_in_constant_time(self):
        lid, key = self.listed()
        with mock.patch('vetdir.rules.hmac.compare_digest', wraps=__import__('hmac').compare_digest) as cmp:
            self.get(f'listings/{lid}/', key=key)
        self.assertTrue(cmp.called)

    def test_an_older_link_does_not_relist_an_unlisted_page(self):
        out = self.list_clinic()
        token = frag(mail.outbox[-1].body, 'listing')
        self.post(f'listings/{out["id"]}/unlist/', {}, key=out['key'])
        self.assertEqual(self.post('listings/confirm/', {'token': token}).status_code, 404)
        self.assertEqual(Listing.objects.get().status, 'unlisted')

    def test_a_put_while_pending_mails_the_link_again_after_the_cooldown(self):
        out = self.list_clinic()
        r = self.put(f'listings/{out["id"]}/', {'card': card()}, out['key'])
        self.assertEqual(r.json()['mail'], 'cooldown')
        self.assertEqual(len(mail.outbox), 1)
        Listing.objects.update(mailed_at=timezone.now() - timedelta(hours=1))
        r = self.put(f'listings/{out["id"]}/', {'card': card()}, out['key'])
        self.assertEqual(r.json()['mail'], 'sent')
        self.assertEqual(len(mail.outbox), 2)

    def test_an_idle_listing_stops_being_public_and_the_key_brings_it_back(self):
        lid, key = self.listed()
        Listing.objects.update(seen_at=timezone.now() - timedelta(days=rules.LISTING_IDLE_DAYS + 1))
        self.assertEqual(self.get(f'listings/{lid}/').status_code, 404)
        self.assertEqual(self.ask(lid).status_code, 404)
        self.assertEqual(self.get(f'listings/{lid}/', key=key).json()['public'], True)  # the call refreshes it
        self.assertEqual(self.get(f'listings/{lid}/').status_code, 200)

    def test_an_smtp_failure_still_hands_the_key_back(self):
        with mock.patch.object(vd_mail, '_send', side_effect=OSError('smtp down')):
            r = self.post('listings/', {'card': card(), 'email': 'k@example.org',
                                        'consent_version': rules.CONSENT_VERSION})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['mail'], 'unavailable')
        self.assertIsNone(Listing.objects.get().mailed_at)

    def test_english_links_are_unprefixed_and_follow_the_site_map(self):
        self.post('listings/', {'card': card(), 'email': 'k@example.org', 'consent_version': rules.CONSENT_VERSION,
                                'locale': 'en'})
        self.assertIn('https://medapp.net/vets/confirm#listing=', mail.outbox[-1].body)
        with self.settings(FUWLOL_VETDIR_SITES={'medapp': 'http://127.0.0.1:5300'}):
            self.post('listings/', {'card': card(), 'email': 'k2@example.org',
                                    'consent_version': rules.CONSENT_VERSION, 'locale': 'uk'})
        self.assertIn('http://127.0.0.1:5300/uk/vets/confirm#listing=', mail.outbox[-1].body)


class RequestTests(VetdirCase):
    def test_a_request_is_pending_until_the_owners_link_and_the_clinic_never_sees_it_before(self):
        lid, key = self.listed()
        r = self.ask(lid)
        self.assertEqual((r.status_code, r.json()), (202, {'ok': True}))
        req = VisitRequest.objects.get()
        self.assertEqual(req.status, 'pending_email')
        self.assertEqual(req.email, 'owner@example.org')
        self.assertEqual(self.get(f'listings/{lid}/requests/', key=key).json(), {'requests': []})
        m = mail.outbox[-1]
        self.assertEqual(m.to, ['owner@example.org'])
        self.assertIn('Przychodnia Demo', m.subject)
        self.assertIn('nie rezerwacja', m.body)
        self.assertIn('+48 22 000 00 00', m.body)  # the clinic's phone, for an emergency
        self.assertIn('#cancel=', m.body)
        token = frag(m.body, 'confirm')
        self.assertEqual(self.post('requests/confirm/', {'token': token}).json()['status'], 'requested')
        self.assertEqual(self.post('requests/confirm/', {'token': token}).status_code, 200)  # again: 200
        rows = self.get(f'listings/{lid}/requests/', key=key).json()['requests']
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0]), {'id', 'status', 'owner_name', 'phone', 'email', 'species', 'animal_name',
                                        'day', 'part_of_day', 'reason', 'locale', 'sent_on', 'start', 'example'})
        self.assertEqual((rows[0]['status'], rows[0]['animal_name'], rows[0]['part_of_day']),
                         ('requested', 'Kicia', 'evening'))

    def test_the_202_is_the_same_for_a_new_request_a_repeat_and_the_honeypot(self):
        lid, _ = self.listed()
        answers = [self.ask(lid), self.ask(lid), self.ask(lid, website='http://spam.example')]
        self.assertEqual({(r.status_code, r.content) for r in answers}, {(202, b'{"ok":true}')})
        self.assertEqual(VisitRequest.objects.count(), 1)
        self.assertEqual(len([m for m in mail.outbox if m.to == ['owner@example.org']]), 1)
        VisitRequest.objects.update(created_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(self.ask(lid).status_code, 202)
        self.assertEqual(VisitRequest.objects.count(), 2)

    def test_unknown_keys_are_dropped_and_only_the_decided_fields_are_kept(self):
        lid, _ = self.listed()
        self.ask(lid, pesel='90010112345', diagnosis='bad', health='heart', address='ul. Domowa 1')
        req = VisitRequest.objects.get()
        for v in ('90010112345', 'heart', 'ul. Domowa 1'):
            self.assertNotIn(v, str(req.__dict__))

    def test_every_refusal_of_a_request_names_its_field(self):
        lid, _ = self.listed()
        today = rules.clinic_today()
        cases = [
            ({'owner_name': ''}, 'owner_name'), ({'owner_name': 'x' * 81}, 'owner_name'), ({'phone': '12'}, 'phone'),
            ({'email': 'nope'}, 'email'), ({'species': 'horse'}, 'species'), ({'species': 'dragon'}, 'species'),
            ({'animal_name': ''}, 'animal_name'), ({'day': 'tomorrow'}, 'day'),
            ({'day': (today - timedelta(days=1)).isoformat()}, 'day'),
            ({'day': (today + timedelta(days=61)).isoformat()}, 'day'), ({'day': '2026-02-30'}, 'day'),
            ({'part_of_day': 'night'}, 'part_of_day'), ({'reason': 'x' * 301}, 'reason'),
        ]
        for change, field in cases:
            cache.clear()
            r = self.ask(lid, **change)
            self.assertEqual(r.status_code, 400, change)
            self.assertIn(field, r.json(), change)
        self.assertEqual(self.ask(lid, day=(today + timedelta(days=60)).isoformat(), reason='').status_code, 202)

    def test_a_listing_that_is_not_public_or_takes_no_requests_refuses(self):
        out = self.list_clinic()
        self.assertEqual(self.ask(out['id']).status_code, 404)  # pending
        lid, key = self.listed(accepts_requests=False)
        self.assertEqual(self.ask(lid).status_code, 404)
        self.assertEqual(self.ask('AAAAAAAAAAAA').status_code, 404)
        self.assertEqual(self.ask('../../x').status_code, 404)
        self.assertEqual(self.post(f'listings/{lid}/requests/', {}, origin='https://evil.example').status_code, 403)
        self.assertFalse(VisitRequest.objects.exists())

    def test_the_clinic_confirms_with_a_start_and_the_owner_gets_one_mail(self):
        lid, key = self.listed()
        req = self.requested(lid)
        start = (timezone.now() + timedelta(days=1)).replace(microsecond=0)
        n = len(mail.outbox)
        r = self.post(f'listings/{lid}/requests/{req.public_id}/', {'status': 'confirmed', 'start': start.isoformat()}, key=key)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()['request']['status'], r.json()['mail']), ('confirmed', 'sent'))
        self.assertEqual(len(mail.outbox), n + 1)
        m = mail.outbox[-1]
        self.assertIn('potwierdza', m.subject)
        self.assertIn(timezone.localtime(start, rules.CLINIC_TZ).strftime('%Y-%m-%d %H:%M'), m.body)
        self.assertIn('+48 22 000 00 00', m.body)
        self.assertIn('#cancel=', m.body)
        # A retried send after a lost answer: 200, the same, no second mail.
        r = self.post(f'listings/{lid}/requests/{req.public_id}/', {'status': 'confirmed', 'start': start.isoformat()}, key=key)
        self.assertEqual((r.status_code, r.json()['mail']), (200, None))
        self.assertEqual(len(mail.outbox), n + 1)
        # Nothing but cancel leaves confirmed, and the clinic cannot cancel or decline it.
        r = self.post(f'listings/{lid}/requests/{req.public_id}/', {'status': 'declined'}, key=key)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['status'], ['confirmed'])

    def test_confirm_needs_a_sane_start(self):
        lid, key = self.listed()
        req = self.requested(lid)
        for start in (None, 'soon', '2026-11-20T10:00', (timezone.now() - timedelta(days=3)).isoformat(),
                      (timezone.now() + timedelta(days=121)).isoformat()):
            r = self.post(f'listings/{lid}/requests/{req.public_id}/', {'status': 'confirmed', 'start': start}, key=key)
            self.assertEqual(r.status_code, 400, start)
            self.assertIn('start', r.json())
        self.assertEqual(VisitRequest.objects.get().status, 'requested')

    def test_the_clinic_declines_and_the_owner_gets_the_phone(self):
        lid, key = self.listed()
        req = self.requested(lid)
        r = self.post(f'listings/{lid}/requests/{req.public_id}/', {'status': 'declined'}, key=key)
        self.assertEqual(r.json()['request']['status'], 'declined')
        m = mail.outbox[-1]
        self.assertIn('nie może', m.subject)
        self.assertIn('+48 22 000 00 00', m.body)
        self.assertNotIn('#cancel=', m.body)  # nothing left to cancel
        # Terminal: neither side moves it again.
        self.assertEqual(self.post(f'listings/{lid}/requests/{req.public_id}/',
                                   {'status': 'confirmed', 'start': timezone.now().isoformat()}, key=key).status_code, 400)
        cancel = frag(mail.outbox[-2].body, 'cancel')
        self.assertEqual(self.post('requests/cancel/', {'token': cancel}).status_code, 400)
        self.assertEqual(VisitRequest.objects.get().status, 'declined')

    def test_the_owner_cancels_from_every_cancellable_state(self):
        lid, key = self.listed()
        # pending_email → cancelled
        self.ask(lid)
        cancel = frag(mail.outbox[-1].body, 'cancel')
        self.assertEqual(self.post('requests/cancel/', {'token': cancel}).json()['status'], 'cancelled')
        self.assertEqual(self.post('requests/cancel/', {'token': cancel}).status_code, 200)  # twice: 200
        confirm = frag(mail.outbox[-1].body, 'confirm')
        self.assertEqual(self.post('requests/confirm/', {'token': confirm}).status_code, 404)  # cancelled stays
        # requested → cancelled
        req = self.requested(lid, email='b@example.org')
        cancel = frag(mail.outbox[-1].body, 'cancel')  # the confirm-your-request mail carries it
        self.assertEqual(cancel, VisitRequest.objects.get(pk=req.pk).cancel_token())
        self.assertEqual(self.post('requests/cancel/', {'token': cancel}).status_code, 200)
        self.assertEqual(self.post(f'listings/{lid}/requests/{req.public_id}/', {'status': 'declined'}, key=key).status_code, 400)
        # confirmed → cancelled
        req = self.requested(lid, email='c@example.org')
        self.post(f'listings/{lid}/requests/{req.public_id}/',
                  {'status': 'confirmed', 'start': (timezone.now() + timedelta(days=2)).isoformat()}, key=key)
        self.assertEqual(self.post('requests/cancel/', {'token': req.cancel_token()}).status_code, 200)
        statuses = [r['status'] for r in self.get(f'listings/{lid}/requests/', key=key).json()['requests']]
        self.assertEqual(statuses, ['cancelled', 'cancelled'])  # the pending_email one never shows

    def test_the_clinic_cannot_act_on_a_pending_email_request_or_skip_a_step(self):
        lid, key = self.listed()
        self.ask(lid)
        req = VisitRequest.objects.get()
        r = self.post(f'listings/{lid}/requests/{req.public_id}/', {'status': 'declined'}, key=key)
        self.assertEqual(r.status_code, 404)
        req = self.requested(lid, email='z@example.org')
        for to in ('requested', 'pending_email', 'cancelled', 'bogus', None):
            r = self.post(f'listings/{lid}/requests/{req.public_id}/', {'status': to}, key=key)
            self.assertEqual(r.status_code, 400, to)

    def test_another_clinics_key_reaches_nothing(self):
        lid, key = self.listed()
        other_id, other_key = self.listed(name='Gabinet Drugi')
        req = self.requested(lid)
        self.assertEqual(self.get(f'listings/{lid}/requests/', key=other_key).status_code, 404)
        self.assertEqual(self.post(f'listings/{other_id}/requests/{req.public_id}/', {'status': 'declined'},
                                   key=other_key).status_code, 404)
        self.assertEqual(self.get(f'listings/{lid}/requests/').status_code, 404)  # no key at all

    def test_the_request_confirmation_link_expires_with_the_unconfirmed_window(self):
        lid, _ = self.listed()
        self.ask(lid)
        token = frag(mail.outbox[-1].body, 'confirm')
        with mock.patch('django.core.signing.time.time', return_value=timezone.now().timestamp() + 3 * 86400):
            self.assertEqual(self.post('requests/confirm/', {'token': token}).status_code, 410)
        self.assertEqual(self.post('requests/confirm/', {'token': token[:-2]}).status_code, 404)

    def test_an_smtp_failure_on_a_request_is_503_and_keeps_nothing_personal(self):
        lid, _ = self.listed()
        with mock.patch.object(vd_mail, '_send', side_effect=OSError('smtp down')):
            r = self.ask(lid)
        self.assertEqual(r.status_code, 503)
        req = VisitRequest.objects.get()
        self.assertIsNotNone(req.blanked_at)
        self.assertEqual((req.owner_name, req.email, req.phone), ('', '', ''))

    def test_a_decision_mail_failure_keeps_the_decision_and_says_so(self):
        lid, key = self.listed()
        req = self.requested(lid)
        with mock.patch.object(vd_mail, '_send', side_effect=OSError('smtp down')):
            r = self.post(f'listings/{lid}/requests/{req.public_id}/', {'status': 'declined'}, key=key)
        self.assertEqual((r.status_code, r.json()['mail']), (200, 'unavailable'))
        self.assertEqual(VisitRequest.objects.get().status, 'declined')

    def test_the_mails_follow_the_owners_language(self):
        lid, key = self.listed()
        self.ask(lid, locale='uk')
        self.assertIn('https://medapp.net/uk/vets/confirm#confirm=', mail.outbox[-1].body)
        self.assertIn('зателефонуйте', mail.outbox[-1].body)
        self.ask(lid, locale='en', email='e@example.org')
        self.assertIn('https://medapp.net/vets/confirm#confirm=', mail.outbox[-1].body)
        self.assertIn('not a booking', mail.outbox[-1].body)


class SweepTests(VetdirCase):
    def test_unconfirmed_requests_are_blanked_after_two_days(self):
        lid, _ = self.listed()
        self.ask(lid)
        VisitRequest.objects.update(created_at=timezone.now() - timedelta(days=rules.REQUEST_UNCONFIRMED_DAYS, hours=1))
        self.assertEqual(rules.sweep(), (1, 0))
        req = VisitRequest.objects.get()
        self.assertEqual([getattr(req, f) for f in rules.PERSONAL_REQUEST_FIELDS], [''] * 5)
        self.assertIsNotNone(req.blanked_at)
        self.assertEqual((req.species, req.status), ('cat', 'pending_email'))  # the row stays, empty

    def test_terminal_requests_are_blanked_thirty_days_after_the_decision(self):
        lid, key = self.listed()
        req = self.requested(lid)
        self.post(f'listings/{lid}/requests/{req.public_id}/', {'status': 'declined'}, key=key)
        VisitRequest.objects.update(decided_at=timezone.now() - timedelta(days=29))
        self.assertEqual(rules.sweep()[0], 0)
        VisitRequest.objects.update(decided_at=timezone.now() - timedelta(days=31))
        self.assertEqual(rules.sweep()[0], 1)
        self.assertEqual(self.get(f'listings/{lid}/requests/', key=key).json()['requests'], [])

    def test_open_requests_are_blanked_thirty_days_after_the_wished_day_or_the_start(self):
        lid, key = self.listed()
        req = self.requested(lid)
        old = rules.clinic_today() - timedelta(days=31)
        VisitRequest.objects.update(day=old)
        self.assertEqual(rules.sweep()[0], 1)
        req2 = self.requested(lid, email='b@example.org')
        start = timezone.now() + timedelta(days=1)
        self.post(f'listings/{lid}/requests/{req2.public_id}/', {'status': 'confirmed', 'start': start.isoformat()}, key=key)
        VisitRequest.objects.filter(pk=req2.pk).update(day=old)  # an old wish, a future start: kept
        self.assertEqual(rules.sweep()[0], 0)

    def test_the_sweep_runs_at_the_next_write(self):
        lid, _ = self.listed()
        self.ask(lid)
        VisitRequest.objects.update(created_at=timezone.now() - timedelta(days=3))
        self.ask(lid, email='other@example.org')
        self.assertIsNotNone(VisitRequest.objects.get(email='').blanked_at)

    def test_a_listing_never_confirmed_is_deleted_after_thirty_days(self):
        self.list_clinic()
        Listing.objects.update(created_at=timezone.now() - timedelta(days=31))
        self.assertEqual(rules.sweep(), (0, 1))
        self.assertFalse(Listing.objects.exists())

    def test_the_management_command_runs_the_same_sweep(self):
        from io import StringIO
        from django.core.management import call_command
        lid, _ = self.listed()
        self.ask(lid)
        VisitRequest.objects.update(created_at=timezone.now() - timedelta(days=3))
        out = StringIO()
        call_command('vetdir_sweep', stdout=out)
        self.assertIn('1', out.getvalue())
        self.assertIsNotNone(VisitRequest.objects.get().blanked_at)


class TransportTests(VetdirCase):
    def test_cors_for_a_known_origin_only_without_credentials(self):
        lid, _ = self.listed()
        r = self.get(f'listings/{lid}/')
        self.assertEqual(r['Access-Control-Allow-Origin'], ORIGIN)
        self.assertNotIn('Access-Control-Allow-Credentials', r)
        self.assertIn('Origin', r['Vary'])
        r = self.get(f'listings/{lid}/', origin='https://evil.example')
        self.assertEqual(r.status_code, 200)  # a public read, but no CORS for that origin
        self.assertNotIn('Access-Control-Allow-Origin', r)

    def test_every_preflight_is_answered_and_not_throttled(self):
        for path in ('listings/', 'listings/confirm/', 'listings/AAAAAAAAAAAA/', 'listings/AAAAAAAAAAAA/unlist/',
                     'listings/AAAAAAAAAAAA/requests/', 'listings/AAAAAAAAAAAA/requests/BBBBBBBBBBBB/',
                     'requests/confirm/', 'requests/cancel/'):
            for _ in range(25):
                r = self.client.options(API + path, HTTP_ORIGIN=ORIGIN, HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST')
            self.assertEqual(r.status_code, 200, path)
            self.assertEqual(r['Access-Control-Allow-Origin'], ORIGIN)
            self.assertIn('X-Vetdir-Key', r['Access-Control-Allow-Headers'])
            self.assertIn('PUT', r['Access-Control-Allow-Methods'])

    def test_a_session_cookie_is_not_a_csrf_403(self):
        user = get_user_model().objects.create_user('someone', password='pw-12345678')
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(user)
        r = client.post(API + 'listings/', {'card': card(), 'email': 'k@example.org',
                                            'consent_version': rules.CONSENT_VERSION},
                        content_type='application/json', HTTP_ORIGIN=ORIGIN)
        self.assertEqual(r.status_code, 201)

    def test_the_listing_scope_throttles_and_answers_429(self):
        body = {'card': card(), 'email': 'k@example.org', 'consent_version': rules.CONSENT_VERSION}
        codes = [self.post('listings/', dict(body, email=f'k{i}@example.org')).status_code for i in range(11)]
        self.assertEqual(codes[:10], [201] * 10)
        self.assertEqual(codes[10], 429)

    def test_the_request_scope_throttles_and_answers_429(self):
        lid, _ = self.listed()
        codes = [self.ask(lid, email=f'o{i}@example.org').status_code for i in range(21)]
        self.assertEqual(codes[:20], [202] * 20)
        self.assertEqual(codes[20], 429)

    def test_no_method_but_the_decided_ones(self):
        lid, key = self.listed()
        self.assertEqual(self.client.delete(API + f'listings/{lid}/', HTTP_ORIGIN=ORIGIN, **{KEY: key}).status_code, 405)
        self.assertEqual(self.get('listings/').status_code, 405)
        self.assertEqual(self.get('requests/confirm/').status_code, 405)

    def test_the_admin_lists_and_unlists_and_has_no_request_admin(self):
        from django.contrib import admin as dj_admin
        self.assertNotIn(VisitRequest, dj_admin.site._registry)
        lid, _ = self.listed()
        su = get_user_model().objects.create_superuser('head', 'h@example.org', 'pw-12345678')
        self.client.force_login(su)
        r = self.client.get('/admin/vetdir/listing/?q=Demo')
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, Listing.objects.get().key_hash)
        r = self.client.post('/admin/vetdir/listing/', {'action': 'unlist', '_selected_action': [Listing.objects.get().pk]})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Listing.objects.get().status, 'unlisted')
        self.assertEqual(self.client.get(f'/admin/vetdir/listing/{Listing.objects.get().pk}/delete/').status_code, 403)


class ExampleSeedTests(VetdirCase):
    """Amendment 1: `manage.py vetdir_seed_examples` — fictional, marked, mailed nobody, cleared exactly."""

    def seed(self, *args):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('vetdir_seed_examples', *args, stdout=out)
        return out.getvalue()

    def test_the_seed_makes_five_marked_listings_and_requests_in_every_status_and_mails_nobody(self):
        from .management.commands.vetdir_seed_examples import EXAMPLE_IDS
        self.seed()
        self.assertEqual(sorted(Listing.objects.values_list('public_id', flat=True)), list(EXAMPLE_IDS))
        self.assertTrue(all(Listing.objects.values_list('example', flat=True)))
        self.assertTrue(all(VisitRequest.objects.values_list('example', flat=True)))
        self.assertEqual(set(VisitRequest.objects.values_list('status', flat=True)), set(rules.REQUEST_STATUSES))
        self.assertEqual(mail.outbox, [])
        for row in Listing.objects.all():
            self.assertTrue(row.email.endswith('.example'))
            self.assertIn('PRZYKŁAD', row.card['name'])
            self.assertTrue(row.card['phone'].startswith('+48 000 000'))
        cards = [r.card for r in Listing.objects.all()]
        self.assertEqual({c['register_type'] for c in cards}, set(rules.REGISTER_TYPES))
        self.assertEqual(sum(not c['accepts_requests'] for c in cards) >= 1, True)  # a phone-only one
        hours = Listing.objects.get(public_id='example-0001').card['hours']
        self.assertEqual(len([w for w in hours if w['weekday'] == 0]), 2)  # the lunch break
        self.assertTrue(any(w['weekday'] == 5 for w in hours))  # a Saturday morning
        self.assertFalse(any(w['weekday'] == 2 for w in Listing.objects.get(public_id='example-0002').card['hours']))

    def test_the_seed_is_idempotent_and_clear_removes_exactly_what_it_made(self):
        lid, key = self.listed()  # a real listing beside the examples
        self.requested(lid)
        self.seed()
        counts = (Listing.objects.count(), VisitRequest.objects.count())
        self.seed()
        self.assertEqual((Listing.objects.count(), VisitRequest.objects.count()), counts)
        self.seed('--clear')
        self.assertEqual(list(Listing.objects.values_list('public_id', flat=True)), [lid])
        self.assertEqual(VisitRequest.objects.count(), 1)
        self.assertEqual(VisitRequest.objects.get().example, False)
        self.seed('--clear')  # twice: nothing to remove, nothing else touched
        self.assertEqual(Listing.objects.count(), 1)

    def test_the_public_card_carries_the_flag_and_a_request_to_an_example_keeps_and_mails_nothing(self):
        self.seed()
        r = self.get('listings/example-0001/')
        self.assertEqual((r.status_code, r.json()['example']), (200, True))
        n = VisitRequest.objects.count()
        r = self.ask('example-0001', email='someone@example.org', species='cat')
        self.assertEqual((r.status_code, r.json()), (202, {'ok': True}))
        self.assertEqual(VisitRequest.objects.count(), n)
        self.assertEqual(mail.outbox, [])
        self.assertEqual(self.ask('example-0002', species='cat').status_code, 404)  # phone-only

    def test_a_seeded_request_is_never_mailed_even_on_a_decision(self):
        self.seed()
        row = Listing.objects.get(public_id='example-0001')
        key = 'k' * 43
        Listing.objects.filter(pk=row.pk).update(key_hash=rules.hash_key(key))
        req = VisitRequest.objects.filter(listing=row, status='requested').first()
        r = self.post(f'listings/example-0001/requests/{req.public_id}/', {'status': 'declined'}, key=key)
        self.assertEqual((r.status_code, r.json()['mail'], r.json()['request']['example']), (200, None, True))
        self.assertEqual(mail.outbox, [])
        with self.assertRaises(vd_mail.ExampleMail):
            vd_mail.send_declined(req)

    def test_a_real_listing_under_an_example_id_stops_the_command(self):
        from django.core.management.base import CommandError
        self.listed()
        Listing.objects.update(public_id='example-0003')
        with self.assertRaises(CommandError):
            self.seed()
        with self.assertRaises(CommandError):
            self.seed('--clear')
