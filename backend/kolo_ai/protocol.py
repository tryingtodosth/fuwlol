"""The protocol of a closed remote vote (§ 10a ust. 8): the resolution text, the result, and
who took part. Markdown, so the Sekretarz can paste it into the Koło's document generator."""
from django.utils import timezone

from . import rules


def protocol_markdown(poll):
    r = rules.tally(poll)
    tz = timezone.get_current_timezone()
    fmt = '%d.%m.%Y, %H:%M'
    L = [f'# Protokół głosowania zdalnego{" (PRÓBA — bez skutków prawnych)" if poll.trial else ""}', '',
         f'**Organ:** {poll.get_organ_display()}  ',
         f'**W sprawie:** {poll.title}  ',
         f'**Tryb:** głosowanie {poll.get_mode_display()}, § 10a regulaminu Koła AI  ',
         f'**Czas głosowania:** od {poll.opens_at.astimezone(tz).strftime(fmt)} do {poll.closes_at.astimezone(tz).strftime(fmt)}  ',
         f'**Zawiadomienie:** {poll.announced_at.astimezone(tz).strftime(fmt) if poll.announced_at else "—"}  ',
         f'**Wymagana większość:** {poll.get_majority_display()}', '',
         '## Projekt uchwały', '', poll.body, '',
         '## Wynik', '',
         f'Uprawnionych: {r["eligible"]}. Wzięło udział: {r["voters"]}. '
         f'Kworum (co najmniej połowa uprawnionych, § 10a ust. 5): {"jest" if r["quorum"] else "brak"}.', '',
         '| Odpowiedź | Głosy |', '|---|---|']
    L += [f'| {o} | {n} |' for o, n in zip(poll.options, r['counts'])]
    L += ['', f'**Rozstrzygnięcie:** {r["note"]}.', '',
          f'## Lista uprawnionych, którzy oddali głos ({r["voters"]})', '']
    L += [f'{i}. {m.name}' for i, m in enumerate(rules.voters(poll), 1)] or ['(nikt)']
    if poll.mode == poll.JAWNE:
        from .models import Vote
        L += ['', '## Głosy imienne (głosowanie jawne)', '']
        L += [f'- {v.member.name}: {poll.options[v.option]}'
              for v in Vote.objects.filter(poll=poll).select_related('member').order_by('member__name')]
    else:
        L += ['', 'Głosowanie tajne: system nie przechowuje powiązania głosu z osobą (§ 10a ust. 6).']
    L += ['', f'Sporządził(a): …………………… (Sekretarz)        Prezes: ……………………', '']
    return '\n'.join(L)
