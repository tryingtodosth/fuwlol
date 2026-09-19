"""The package a head-admin forwards to Dyżurnet.pl, assembled from frozen evidence.

Dyżurnet.pl (NASK) takes reports through its own form at dyzurnet.pl and by e-mail to
dyzurnet@nask.pl. It has no API, and this project would not call one if it had: nothing
here may contact a national authority on its own, because "the system reported it" is not
a thing a person can be accountable for. So this module's entire output is text and
metadata for a human to read, check, and send under their own name.

What goes in is what an analyst can act on without the file itself, and it is deliberately
the same list every time:

* where it was (the public URL, and the catalogue number a later question can quote back),
* when it was published and when it was captured, both in UTC,
* who put it there as far as this service can answer — the address and the user-agent,
  which is what an ISP subscriber query is keyed on,
* the sha256 of every binary, which identifies the file in any collection they hold
  without anybody sending it again,
* the frozen package hash, so what was forwarded can be shown to be what was captured.

Everything is read from the evidence manifest written at escalation time, never from the
live rows: by the time a head-admin gets here the post may have been edited and an
attachment replaced, and what is being reported is what was there.
"""
import json
from pathlib import Path

from django.conf import settings
from django.utils import timezone

DYZURNET_FORM = 'https://dyzurnet.pl/zglos-nielegalne-tresci/'
DYZURNET_EMAIL = 'dyzurnet@nask.pl'


def manifest_for(escalation) -> dict:
    path = Path(settings.EVIDENCE_ROOT) / str(escalation.pk) / 'manifest.json'
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _target_url(manifest) -> str:
    base = getattr(settings, 'FUWLOL_SITE_URL', '').rstrip('/')
    kind, pk = manifest.get('kind'), manifest.get('pk')
    if kind == 'Post':
        return f'{base}/wpis/{pk}'
    if kind == 'Comment':
        return f'{base}/wpis/{manifest.get("post_id")}#komentarz-{pk}'
    if kind == 'Message':
        return f'{base}/tablica#wiadomosc-{pk}'
    return base


def build_package(escalation, *, preview_ttl=None) -> dict:
    """The machine-readable half. `files` carries one entry per captured binary with its
    sha256; `preview_urls` are five-minute R2 links, present only for a head-admin's own
    inspection and never written to a log or an e-mail."""
    from config import r2

    manifest = manifest_for(escalation)
    files = []
    for f in manifest.get('files', []):
        entry = {'original_name': f.get('name', ''), 'sha256': f.get('sha256', ''),
                 'stored_as': f.get('stored_as', '')}
        key = f.get('storage_key', '')
        if key:
            entry['storage_key'] = key
            if r2.is_configured():
                try:
                    entry['preview_url'] = r2.presign_get(
                        key, ttl=preview_ttl or r2.PREVIEW_TTL_SECONDS, filename=f.get('name', ''))
                except Exception:  # a preview link is a convenience; its absence must not
                    entry['preview_url'] = ''  # block assembling the report itself
        files.append(entry)
    return {
        'escalation_id': escalation.pk,
        'service': {'name': 'fuw.lol', 'url': getattr(settings, 'FUWLOL_SITE_URL', ''),
                    'contact': getattr(settings, 'FUWLOL_CONTACT_EMAIL', ''),
                    'role': 'usługa hostingowa w rozumieniu art. 6 DSA'},
        'target': {'kind': manifest.get('kind', ''), 'id': manifest.get('pk'),
                   'url': _target_url(manifest), 'catalog_no': manifest.get('catalog_no', ''),
                   'title': manifest.get('title', ''),
                   'published_at': manifest.get('created_at', '')},
        'uploader': {'username': (manifest.get('submitted_by') or manifest.get('author') or {}).get('username', '')
                     if isinstance(manifest.get('submitted_by') or manifest.get('author'), dict) else '',
                     'ip': manifest.get('submitter_ip', ''),
                     'user_agent': manifest.get('submitter_user_agent', '')},
        'captured_at': manifest.get('captured_at', ''),
        'evidence_package_sha256': escalation.evidence_ref,
        'reported_reason': escalation.reason,
        'files': files,
        'where_to_send': {'form': DYZURNET_FORM, 'email': DYZURNET_EMAIL},
        'assembled_at': timezone.now().isoformat(),
    }


def render_text(package: dict) -> str:
    """The same package as something a person pastes into the Dyżurnet form. Polish,
    because that is the language of the authority receiving it."""
    t, u = package['target'], package['uploader']
    lines = [
        'ZGŁOSZENIE NIELEGALNYCH TREŚCI — fuw.lol',
        '',
        f'Usługa: {package["service"]["name"]} ({package["service"]["url"]})',
        f'Rola: {package["service"]["role"]}',
        f'Kontakt: {package["service"]["contact"]}',
        '',
        f'Adres treści: {t["url"]}',
        f'Rodzaj obiektu: {t["kind"]} (id {t["id"]}{", " + t["catalog_no"] if t.get("catalog_no") else ""})',
        f'Tytuł: {t.get("title") or "—"}',
        f'Opublikowano (UTC): {t.get("published_at") or "—"}',
        f'Zabezpieczono (UTC): {package.get("captured_at") or "—"}',
        '',
        'DANE ZGŁASZAJĄCEGO UŻYTKOWNIKA (art. 18 DSA):',
        f'  Konto: {u.get("username") or "—"}',
        f'  Adres IP przy zamieszczeniu: {u.get("ip") or "— (nie zarejestrowano / minął okres retencji)"}',
        f'  User-Agent: {u.get("user_agent") or "—"}',
        '',
        f'Powód zgłoszenia (moderator): {package.get("reported_reason") or "—"}',
        '',
        f'Suma kontrolna pakietu dowodowego (sha256): {package.get("evidence_package_sha256") or "—"}',
        '',
        'PLIKI:',
    ]
    if package['files']:
        for i, f in enumerate(package['files'], 1):
            lines.append(f'  {i}. {f.get("original_name") or "—"}')
            lines.append(f'     sha256: {f.get("sha256") or "—"}')
    else:
        lines.append('  (brak plików binarnych — treść tekstowa)')
    lines += [
        '',
        'UWAGA: po potwierdzeniu przekazania tego zgłoszenia wszystkie kopie plików',
        'zostaną u nas trwale usunięte (art. 202 § 4b k.k. — nie wolno nam ich',
        'przechowywać). Pozostaną wyłącznie sumy kontrolne, adres IP, user-agent i daty,',
        'zapisane w rejestrze dowodowym. Jeżeli potrzebują Państwo samych plików,',
        'prosimy o kontakt PRZED potwierdzeniem przekazania.',
    ]
    return '\n'.join(lines)
