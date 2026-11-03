"""`/api/kolo/…` — Koło AI: joining, members, remote votes (§ 10a), the status feed.

Authentication is `auth.KoloAuthentication` only — never the archive's token or session, so
an archive account opens nothing here and a Koło session opens nothing in the archive.

Who may do what:
- anybody: read the status feed and the public info; ask to join; ask for a login link;
- a member (any status, own session): read their own row; log out;
- a member in the register with a vote (`czlonek`): Walne votes — read, deliberate, vote,
  object (§ 10a ust. 7); a Zarząd member also the Zarząd's votes;
- a manager (`Member.can_manage`): the queue, invitations, decisions, drafting and announcing
  votes, hiding comments, the protocol, the status feed;
- a `PublishKey`: post and withdraw status entries.

No oracle (root CLAUDE.md rule 5): join and login answer the same 202 whether or not the address
is known; a poll the caller may not see is the same 404 as one that does not exist.
"""
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import rules
from .auth import KoloAuthentication, member_of, publish_key_of, session_of
from .models import Comment, FounderDetails, LoginLink, Member, Objection, Poll, Setting, StatusEntry, Vote

JOIN_REPLY = ('Oczekujesz na zatwierdzenie. Wysłaliśmy link na podany adres — kliknij go, żeby potwierdzić, '
              'że adres jest Twój. Bez potwierdzenia zgłoszenie nie trafi do Zarządu.')
LOGIN_REPLY = 'Jeśli ten adres jest w Kole, wysłaliśmy na niego link do logowania (ważny 24 godziny).'
MAIL_DOWN = {'detail': 'Nie udało się wysłać wiadomości. Spróbuj ponownie później.'}


class KoloView(APIView):
    authentication_classes = [KoloAuthentication]
    permission_classes = [AllowAny]


def _needs_member(request):
    m = member_of(request)
    if m is None:
        return None, Response({'detail': 'Zaloguj się linkiem z maila.'}, status=status.HTTP_401_UNAUTHORIZED)
    return m, None


def _needs_manager(request):
    m = member_of(request)
    if m is None or not m.can_manage:
        return None, Response({'detail': 'Tylko dla osób prowadzących ewidencję i głosowania.'}, status=status.HTTP_403_FORBIDDEN)
    return m, None


def member_row(m, full=False):
    row = {'id': m.pk, 'name': m.name, 'status': m.status, 'status_label': m.get_status_display(),
           'role': m.role, 'affiliation': m.affiliation, 'funkcja': m.funkcja, 'zarzad': m.zarzad,
           'can_manage': m.can_manage}
    if full:
        row.update({'email': m.email, 'created_at': m.created_at, 'email_confirmed_at': m.email_confirmed_at,
                    'approved_at': m.approved_at, 'left_at': m.left_at,
                    'uw_email': rules.is_uw_email(m.email),
                    'problem_czlonek': rules.admission_problem(m, Member.CZLONEK)})
    return row


def status_row(s):
    return {'id': s.pk, 'title': s.title, 'body': s.body, 'published_at': s.published_at, 'status': s.status}


def poll_row(p, member, detail=False):
    ph = rules.phase(p)
    row = {'id': p.pk, 'organ': p.organ, 'organ_label': p.get_organ_display(), 'kind': p.kind, 'title': p.title,
           'mode': p.mode, 'majority': p.majority, 'majority_label': p.get_majority_display(), 'trial': p.trial,
           'status': p.status, 'phase': ph, 'opens_at': p.opens_at, 'closes_at': p.closes_at,
           'announced_at': p.announced_at, 'options': p.options}
    if not detail:
        return row
    row['body'] = p.body
    row['has_voted'] = member is not None and rules.has_voted(p, member)
    row['can_vote'] = member is not None and rules.vote_block_reason(p, member, 0) is None
    row['eligible_count'] = rules.eligible(p).count() if ph in ('open', 'closed') else None
    row['objections'] = Objection.objects.filter(poll=p).count()
    row['objected'] = member is not None and Objection.objects.filter(poll=p, member=member).exists()
    row['my_vote'] = None
    if member is not None and p.mode == Poll.JAWNE:
        v = Vote.objects.filter(poll=p, member=member).first()
        row['my_vote'] = v.option if v else None
    row['result'] = rules.tally(p)
    row['named_votes'] = None
    if row['result'] is not None and p.mode == Poll.JAWNE:
        row['named_votes'] = [{'name': v.member.name, 'option': v.option}
                              for v in Vote.objects.filter(poll=p).select_related('member').order_by('member__name')]
    return row


# --- public ---------------------------------------------------------------------------------

class InfoView(KoloView):
    def get(self, request):
        return Response({'members': rules.voting_members().count(), 'auto_admit': rules.auto_admit(),
                         'consent_version': rules.CONSENT_VERSION,
                         'texts': {k: rules.setting(k) for k in rules.SETTINGS}})


class StatusListView(KoloView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'kolo_status'

    def get_throttles(self):
        return super().get_throttles() if self.request.method == 'POST' else []

    def get(self, request):
        return Response([status_row(s) for s in StatusEntry.objects.filter(status=StatusEntry.PUBLISHED)[:100]])

    def post(self, request):
        key, manager = publish_key_of(request), member_of(request)
        if key is None and (manager is None or not manager.can_manage):
            return Response({'detail': 'Brak uprawnień do publikowania statusu.'}, status=status.HTTP_403_FORBIDDEN)
        title = (request.data.get('title') or '').strip()
        body = (request.data.get('body') or '').strip()
        if not title or len(title) > 200 or len(body) > 10000:
            return Response({'title': ['Tytuł: 1–200 znaków; treść do 10 000 znaków.']}, status=status.HTTP_400_BAD_REQUEST)
        source = f'klucz: {key.name}' if key else f'zarząd: {manager.name}'
        s = StatusEntry.objects.create(title=title, body=body, source=source)
        return Response(status_row(s), status=status.HTTP_201_CREATED)


class StatusWithdrawView(KoloView):
    def post(self, request, pk):
        manager = member_of(request)
        if publish_key_of(request) is None and (manager is None or not manager.can_manage):
            return Response({'detail': 'Brak uprawnień.'}, status=status.HTTP_403_FORBIDDEN)
        s = get_object_or_404(StatusEntry, pk=pk)
        s.status = StatusEntry.WITHDRAWN
        s.save(update_fields=['status'])
        return Response(status_row(s))


class JoinView(KoloView):
    """POST {email, name, affiliation, agreed_text_version} → 202, always the same words."""
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'kolo_join'

    def post(self, request):
        email = rules.normalize_email(request.data.get('email'))
        name = (request.data.get('name') or '').strip()
        affiliation = request.data.get('affiliation')
        errors = {}
        if email is None:
            errors['email'] = ['Podaj poprawny adres e-mail.']
        elif problem := rules.dead_domain_problem(email):
            errors['email'] = [problem]
        if not 3 <= len(name) <= 120:
            errors['name'] = ['Podaj imię i nazwisko (jak w ewidencji członków).']
        if affiliation not in dict(Member.AFFILIATIONS):
            errors['affiliation'] = ['Wybierz: student, doktorant albo żadne z nich.']
        if request.data.get('agreed_text_version') != rules.CONSENT_VERSION:
            errors['agreed_text_version'] = ['Zaznacz zgodę na przetwarzanie danych.']
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            m = Member.objects.filter(email=email).first()
            if m is None:
                m = Member.objects.create(email=email, name=name, affiliation=affiliation,
                                          agreed_text_version=rules.CONSENT_VERSION)
                link = rules.make_link(m)
                body = (f'Dzień dobry,\n\nktoś (zapewne Ty) zgłosił ten adres do Koła AI jako: {name}.\n'
                        f'Kliknij, żeby potwierdzić adres; potem zgłoszenie czeka na zatwierdzenie:\n\n{link}\n\n'
                        f'Link działa 24 godziny. Jeśli to nie Ty — zignoruj tę wiadomość; adres zostanie usunięty '
                        f'na prośbę wysłaną na kontakt poniżej.')
            else:  # known address: a login link instead, with the same answer on screen
                link = rules.make_link(m)
                body = (f'Dzień dobry,\n\nten adres jest już w Kole AI (status: {m.get_status_display()}). '
                        f'Link do logowania:\n\n{link}\n\nLink działa 24 godziny.')
            try:
                rules.mail(email, 'potwierdź adres', body)
            except Exception:
                transaction.set_rollback(True)
                return Response(MAIL_DOWN, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({'detail': JOIN_REPLY}, status=status.HTTP_202_ACCEPTED)


class LoginRequestView(KoloView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'kolo_login'

    def post(self, request):
        email = rules.normalize_email(request.data.get('email'))
        if email is None:
            return Response({'email': ['Podaj poprawny adres e-mail.']}, status=status.HTTP_400_BAD_REQUEST)
        if problem := rules.dead_domain_problem(email):
            return Response({'email': [problem]}, status=status.HTTP_400_BAD_REQUEST)
        m = Member.objects.filter(email=email).first()
        if m is not None:
            link = rules.make_link(m)
            try:
                rules.mail(email, 'logowanie', f'Link do logowania w Kole AI:\n\n{link}\n\nDziała 24 godziny i tylko raz.')
            except Exception:
                return Response(MAIL_DOWN, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({'detail': LOGIN_REPLY}, status=status.HTTP_202_ACCEPTED)


class LinkView(KoloView):
    """POST {token} → {session, member}. The token is the secret; nobody needs to be logged in."""
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'kolo_login'

    def post(self, request):
        m = rules.open_link((request.data.get('token') or '').strip())
        if m is None:
            return Response({'detail': 'Link wygasł albo został już użyty. Poproś o nowy.'}, status=status.HTTP_400_BAD_REQUEST)
        m.refresh_from_db()
        return Response({'session': rules.new_session(m), 'member': member_row(m)})


class MeView(KoloView):
    def get(self, request):
        m, err = _needs_member(request)
        return err or Response(member_row(m))


class LogoutView(KoloView):
    def post(self, request):
        s = session_of(request)
        if s is not None:
            s.revoked_at = timezone.now()
            s.save(update_fields=['revoked_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- managers: the register ----------------------------------------------------------------

class MemberListView(KoloView):
    def get(self, request):
        _, err = _needs_manager(request)
        if err:
            return err
        qs = Member.objects.all()
        if request.query_params.get('status'):
            qs = qs.filter(status=request.query_params['status'])
        return Response([member_row(m, full=True) for m in qs])


class MemberDecideView(KoloView):
    """POST {decision: admit|reject|leave, role, reason}. A refusal needs the Zarząd's
    resolution with reasons (§ 5 ust. 5) — the reason field is required for it."""

    def post(self, request, pk):
        actor, err = _needs_manager(request)
        if err:
            return err
        m = get_object_or_404(Member, pk=pk)
        decision, reason = request.data.get('decision'), (request.data.get('reason') or '').strip()
        with transaction.atomic():
            m = Member.objects.select_for_update().get(pk=m.pk)
            if decision == 'admit':
                role = request.data.get('role')
                if role not in dict(Member.ROLES):
                    return Response({'role': ['Wybierz rolę.']}, status=status.HTTP_400_BAD_REQUEST)
                if m.status not in (Member.PENDING_APPROVAL, Member.MEMBER):
                    return Response({'detail': 'Wpisać można osobę z potwierdzonym adresem, która czeka na zatwierdzenie.'},
                                    status=status.HTTP_409_CONFLICT)
                problem = rules.admission_problem(m, role)
                if problem:
                    return Response({'detail': problem}, status=status.HTTP_400_BAD_REQUEST)
                rules.admit(m, role, actor, reason)
            elif decision == 'reject':
                if m.status != Member.PENDING_APPROVAL:
                    return Response({'detail': 'Odmówić można tylko zgłoszeniu, które czeka na zatwierdzenie.'},
                                    status=status.HTTP_409_CONFLICT)
                if not reason:
                    return Response({'reason': ['Odmowa wymaga uchwały Zarządu z uzasadnieniem (§ 5 ust. 5) — wpisz je.']},
                                    status=status.HTTP_400_BAD_REQUEST)
                rules.reject(m, actor, reason)
            elif decision == 'leave':
                if m.status != Member.MEMBER or not reason:
                    return Response({'detail': 'Ustanie członkostwa: tylko dla osoby w ewidencji, z podaniem przyczyny (§ 6).'},
                                    status=status.HTTP_400_BAD_REQUEST)
                rules.leave(m, actor, reason)
            else:
                return Response({'decision': ['admit, reject albo leave.']}, status=status.HTTP_400_BAD_REQUEST)
        return Response(member_row(m, full=True))


class InviteView(KoloView):
    """POST {email, name, affiliation, role} → 201. The invitation is the approval: opening
    the link enters the person in the register (unless a rule moved in the meantime)."""

    def post(self, request):
        actor, err = _needs_manager(request)
        if err:
            return err
        email = rules.normalize_email(request.data.get('email'))
        name = (request.data.get('name') or '').strip()
        affiliation, role = request.data.get('affiliation', Member.STUDENT), request.data.get('role', Member.CZLONEK)
        if email is None or not 3 <= len(name) <= 120 or affiliation not in dict(Member.AFFILIATIONS) or role not in dict(Member.ROLES):
            return Response({'detail': 'Podaj adres, imię i nazwisko, status uczelniany i rolę.'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            m = Member.objects.select_for_update().filter(email=email).first()
            if m is not None and m.status not in (Member.PENDING_EMAIL, Member.INVITED):
                return Response({'detail': f'Ten adres jest już w Kole (status: {m.get_status_display()}).'},
                                status=status.HTTP_409_CONFLICT)
            if m is None:
                m = Member(email=email)
            m.name, m.affiliation, m.role = name, affiliation, role
            m.status = Member.INVITED
            m.save()
            rules.MemberAction.objects.create(member=m, actor=actor, action='invite', to_status=Member.INVITED)
            problem = rules.admission_problem(m, role)
            if problem:
                transaction.set_rollback(True)
                return Response({'detail': problem}, status=status.HTTP_400_BAD_REQUEST)
            link = rules.make_link(m, LoginLink.INVITE_VALID_FOR)
            try:
                rules.mail(email, 'zaproszenie', (
                    f'Dzień dobry,\n\n{actor.name} zaprasza Cię do Koła AI przy Wydziale Fizyki UW '
                    f'({"członek z prawem głosu" if role == Member.CZLONEK else "sympatyk"}).\n'
                    f'Kliknij, żeby przyjąć zaproszenie i potwierdzić adres:\n\n{link}\n\n'
                    f'Link działa 7 dni. Jeśli nie chcesz — zignoruj tę wiadomość.'))
            except Exception:
                transaction.set_rollback(True)
                return Response(MAIL_DOWN, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(member_row(m, full=True), status=status.HTTP_201_CREATED)


# --- polls ------------------------------------------------------------------------------------

def _poll_or_404(member, pk):
    p = Poll.objects.filter(pk=pk).first()
    if p is None or not rules.can_see(member, p):
        raise NotFound('Nie znaleziono.')
    return p


def _parse_poll(data, poll=None):
    """Validated fields for a draft, or (None, errors)."""
    errors, out = {}, {}
    for f, choices in (('organ', Poll.ORGANS), ('kind', Poll.KINDS), ('mode', Poll.MODES), ('majority', Poll.MAJORITIES)):
        v = data.get(f, getattr(poll, f) if poll else None)
        if v not in dict(choices):
            errors[f] = ['Niepoprawna wartość.']
        out[f] = v
    out['title'] = (data.get('title', poll.title if poll else '') or '').strip()
    out['body'] = (data.get('body', poll.body if poll else '') or '').strip()
    if not out['title'] or len(out['title']) > 200:
        errors['title'] = ['Tytuł: 1–200 znaków.']
    if not out['body']:
        errors['body'] = ['Wpisz projekt uchwały.']
    out['trial'] = bool(data.get('trial', poll.trial if poll else False))
    for f in ('opens_at', 'closes_at'):
        raw = data.get(f)
        v = parse_datetime(raw) if isinstance(raw, str) else (getattr(poll, f) if poll else None)
        if v is None:
            errors[f] = ['Podaj datę i godzinę.']
        elif timezone.is_naive(v):
            v = timezone.make_aware(v)
        out[f] = v
    if out.get('kind') == Poll.WYBORY:
        cands = data.get('candidates')
        if cands is None and poll is not None:
            out['options'] = poll.options
        elif not isinstance(cands, list) or not [c for c in cands if isinstance(c, str) and c.strip()]:
            errors['candidates'] = ['Podaj co najmniej jednego kandydata.']
        else:
            out['options'] = rules.default_options(Poll.WYBORY, [c for c in cands if isinstance(c, str)])
        out['majority'] = 'bezwzgledna'  # § 12 ust. 4, whatever was sent
    elif 'kind' not in errors:
        out['options'] = rules.default_options(Poll.UCHWALA)
    if not errors and out['closes_at'] <= out['opens_at']:
        errors['closes_at'] = ['Koniec musi być po początku.']
    return (None, errors) if errors else (out, None)


class PollListView(KoloView):
    def get(self, request):
        m = member_of(request)
        return Response([poll_row(p, m) for p in rules.visible_polls(m)])

    def post(self, request):
        actor, err = _needs_manager(request)
        if err:
            return err
        fields, errors = _parse_poll(request.data)
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        p = Poll.objects.create(created_by=actor, **fields)
        return Response(poll_row(p, actor, detail=True), status=status.HTTP_201_CREATED)


class PollDetailView(KoloView):
    def get(self, request, pk):
        m = member_of(request)
        return Response(poll_row(_poll_or_404(m, pk), m, detail=True))

    def patch(self, request, pk):
        actor, err = _needs_manager(request)
        if err:
            return err
        p = get_object_or_404(Poll, pk=pk)
        if p.status != Poll.DRAFT:
            return Response({'detail': 'Zmieniać można tylko projekt, przed zawiadomieniem.'}, status=status.HTTP_409_CONFLICT)
        fields, errors = _parse_poll(request.data, p)
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        for k, v in fields.items():
            setattr(p, k, v)
        p.save()
        return Response(poll_row(p, actor, detail=True))


class PollAnnounceView(KoloView):
    def post(self, request, pk):
        actor, err = _needs_manager(request)
        if err:
            return err
        with transaction.atomic():
            p = Poll.objects.select_for_update().get(pk=get_object_or_404(Poll, pk=pk).pk)
            problem = rules.announce_problem(p)
            if problem:
                return Response({'detail': problem}, status=status.HTTP_400_BAD_REQUEST)
            p.status, p.announced_at = Poll.ANNOUNCED, timezone.now()
            p.save(update_fields=['status', 'announced_at'])
        failed = rules.notify_announced(p)
        row = poll_row(p, actor, detail=True)
        row['mail_failed'] = failed
        return Response(row)


class PollCancelView(KoloView):
    def post(self, request, pk):
        actor, err = _needs_manager(request)
        if err:
            return err
        p = get_object_or_404(Poll, pk=pk)
        if rules.phase(p) not in ('draft', 'announced'):
            return Response({'detail': 'Odwołać można głosowanie, które się jeszcze nie zaczęło.'}, status=status.HTTP_409_CONFLICT)
        p.status = Poll.CANCELLED
        p.save(update_fields=['status'])
        return Response(poll_row(p, actor, detail=True))


class VoteView(KoloView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'kolo_vote'

    def post(self, request, pk):
        m, err = _needs_member(request)
        if err:
            return err
        p = _poll_or_404(m, pk)
        reason = rules.cast(p, m, request.data.get('option'))
        if reason:
            return Response({'detail': reason}, status=status.HTTP_400_BAD_REQUEST)
        return Response(poll_row(p, m, detail=True), status=status.HTTP_201_CREATED)


class ObjectView(KoloView):
    def post(self, request, pk):
        m, err = _needs_member(request)
        if err:
            return err
        p = _poll_or_404(m, pk)
        reason = rules.object_to(p, m)
        if reason:
            return Response({'detail': reason}, status=status.HTTP_400_BAD_REQUEST)
        p.refresh_from_db()
        return Response(poll_row(p, m, detail=True))


def comment_row(c):
    return {'id': c.pk, 'name': c.member.name, 'body': c.body, 'created_at': c.created_at}


class CommentListView(KoloView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'kolo_comment'

    def get_throttles(self):
        return super().get_throttles() if self.request.method == 'POST' else []

    def get(self, request, pk):
        m, err = _needs_member(request)
        if err:
            return err
        p = _poll_or_404(m, pk)
        return Response([comment_row(c) for c in rules.visible_comments(p)])

    def post(self, request, pk):
        m, err = _needs_member(request)
        if err:
            return err
        p = _poll_or_404(m, pk)
        if not rules.can_comment(m, p):
            return Response({'detail': 'Obrady są zamknięte.'}, status=status.HTTP_400_BAD_REQUEST)
        body = (request.data.get('body') or '').strip()
        if not body or len(body) > 4000:
            return Response({'body': ['Wpis: 1–4000 znaków.']}, status=status.HTTP_400_BAD_REQUEST)
        c = Comment.objects.create(poll=p, member=m, body=body)
        return Response(comment_row(c), status=status.HTTP_201_CREATED)


class CommentHideView(KoloView):
    def post(self, request, pk):
        _, err = _needs_manager(request)
        if err:
            return err
        c = get_object_or_404(Comment, pk=pk)
        c.hidden_at = c.hidden_at or timezone.now()
        c.save(update_fields=['hidden_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProtocolView(KoloView):
    """GET → {markdown}: the protocol of a closed vote (§ 10a ust. 8), for the Sekretarz."""

    def get(self, request, pk):
        _, err = _needs_manager(request)
        if err:
            return err
        p = get_object_or_404(Poll, pk=pk)
        if rules.phase(p) != 'closed':
            return Response({'detail': 'Protokół powstaje po zakończeniu głosowania.'}, status=status.HTTP_409_CONFLICT)
        from .protocol import protocol_markdown
        return Response({'markdown': protocol_markdown(p)})


# --- the list of founders (BOK template) ------------------------------------------------------

FOUNDER_FIELDS = ('phone', 'kierunek', 'etap', 'nr_albumu')


def founder_row(m):
    f = getattr(m, 'founder', None)
    return {'id': m.pk, 'name': m.name, 'email': m.email, 'affiliation': m.affiliation, 'status': m.status,
            **{k: getattr(f, k, '') for k in FOUNDER_FIELDS}, 'updated_at': f.updated_at if f else None}


class MyFounderView(KoloView):
    """GET → my founder data (or blanks); PUT {phone, kierunek, etap, nr_albumu, agreed_text_version}."""
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'kolo_comment'

    def get_throttles(self):
        return super().get_throttles() if self.request.method == 'PUT' else []

    def get(self, request):
        m, err = _needs_member(request)
        if err:
            return err
        row = founder_row(m)
        row['problem'] = rules.founder_problem(m)
        return Response(row)

    def put(self, request):
        m, err = _needs_member(request)
        if err:
            return err
        problem = rules.founder_problem(m)
        if problem:
            return Response({'detail': problem}, status=status.HTTP_400_BAD_REQUEST)
        d = {k: (str(request.data.get(k) or '')).strip() for k in FOUNDER_FIELDS}
        errors = {}
        import re
        if not re.fullmatch(r'\+?[0-9 ()-]{9,20}', d['phone']):
            errors['phone'] = ['Podaj numer telefonu (9–20 cyfr, może być +48).']
        if not 2 <= len(d['kierunek']) <= 120:
            errors['kierunek'] = ['Podaj kierunek albo nazwę szkoły doktorskiej.']
        if not 1 <= len(d['etap']) <= 40:
            errors['etap'] = ['Podaj rok studiów albo etap kształcenia (np. „2. rok I st.”).']
        if not re.fullmatch(r'[0-9]{4,10}', d['nr_albumu']):
            errors['nr_albumu'] = ['Numer albumu to same cyfry.']
        if request.data.get('agreed_text_version') != rules.FOUNDER_CONSENT_VERSION:
            errors['agreed_text_version'] = ['Zaznacz zgodę na umieszczenie danych na liście założycieli.']
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        FounderDetails.objects.update_or_create(member=m, defaults={**d, 'agreed_text_version': rules.FOUNDER_CONSENT_VERSION})
        m.refresh_from_db()
        return Response(founder_row(m))

    def delete(self, request):
        m, err = _needs_member(request)
        if err:
            return err
        FounderDetails.objects.filter(member=m).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class FounderListView(KoloView):
    """GET → every person who filed founder data, by surname — for the printed list (managers)."""

    def get(self, request):
        _, err = _needs_manager(request)
        if err:
            return err
        people = (Member.objects.filter(founder__isnull=False, status__in=[Member.PENDING_APPROVAL, Member.MEMBER])
                  .select_related('founder'))
        rows = sorted((founder_row(m) for m in people), key=lambda r: (r['name'].split()[-1].lower(), r['name'].lower()))
        return Response(rows)


class SettingView(KoloView):
    """PUT {value} → a manager edits one of `rules.SETTINGS` (plain text, ≤ 1000 chars)."""

    def put(self, request, key):
        actor, err = _needs_manager(request)
        if err:
            return err
        if key not in rules.SETTINGS:
            raise NotFound('Nie znaleziono.')
        value = (request.data.get('value') or '').strip()
        if not value or len(value) > 1000:
            return Response({'value': ['Tekst: 1–1000 znaków.']}, status=status.HTTP_400_BAD_REQUEST)
        Setting.objects.update_or_create(key=key, defaults={'value': value, 'updated_by': actor.name})
        return Response({'key': key, 'value': value})
