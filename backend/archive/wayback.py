"""The time machine's bridge to the Internet Archive. The Wayback Machine resolves
`/web/<YYYYMMDD>if_/<url>` to its nearest capture by redirect, so the frontend can
embed that URL directly; this endpoint only finds out WHICH capture that was (for the
"snapshot from …" caption) by following the redirect with a HEAD request, and caches
the answer for a day so the Archive is not asked twice for the same date."""
import re
import urllib.error
import urllib.request

from django.core.cache import cache
from rest_framework.response import Response
from rest_framework.views import APIView

SITE = 'http://www.fuw.edu.pl/'
EARLIEST = '1998-01-20'  # first capture of fuw.edu.pl the Archive holds (checked 2026-09-10)
UA = 'fuw.lol time machine (+https://fuw.lol)'


def snapshot_url(yyyymmdd):
    return f'https://web.archive.org/web/{yyyymmdd}000000if_/{SITE}'


def resolve(yyyymmdd):
    key = f'wayback:{yyyymmdd}'
    hit = cache.get(key)
    if hit is not None:
        return hit
    result = {'requested': yyyymmdd, 'embed_url': snapshot_url(yyyymmdd), 'timestamp': None}
    try:
        req = urllib.request.Request(snapshot_url(yyyymmdd), method='HEAD', headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=8) as r:
            m = re.search(r'/web/(\d{14})', r.geturl())
            if m:
                result['timestamp'] = m.group(1)
                result['embed_url'] = f'https://web.archive.org/web/{m.group(1)}if_/{SITE}'
    except (urllib.error.URLError, ValueError, OSError):
        pass  # the embed URL still works on its own; only the caption loses precision
    cache.set(key, result, 60 * 60 * 24)
    return result


class WaybackView(APIView):
    def get(self, request):
        date = (request.query_params.get('date') or '').replace('-', '')
        if not re.fullmatch(r'\d{8}', date):
            return Response({'detail': 'date=YYYY-MM-DD'}, status=400)
        data = resolve(date)
        data['earliest'] = EARLIEST
        return Response(data)
