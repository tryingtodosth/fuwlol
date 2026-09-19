r"""The half of a link preview that is HTML: the tags, and the page they sit in.

Two deliveries are possible, and this module is written so that the choice between them
is a setting rather than a rewrite. `deploy/OVH.md` records which one fuw.lol runs and why.

**(b) crawler routing — what fuw.lol does.** nginx matches the User-Agent and sends the
scrapers (and only the scrapers) to Django, which answers a small page: the tags, an
`<h1>`, the description and a link to the real URL. Everybody else is served the same
static `200.html` as before, byte for byte. This is the only mode available here because
the built SPA lives in the `web` image and Django lives in the `api` image — separate
containers, separate filesystems, and Django cannot read a file it does not have.

**(a) inject for everyone — what to switch to if that ever changes.** Point
`FUWLOL_SPA_INDEX` at the built shell (`/usr/share/nginx/html/200.html` on a shared
volume) and this module splices the same tags into the real `<head>`, so the crawler and
the human are served the identical document and no User-Agent is ever looked at. Set
`FUWLOL_SHARE_REDIRECT_HUMANS=0` with it, and point the proxy at Django for these routes
rather than at the static file.

The splice is implemented and tested either way, because the failure mode of the
alternative — discovering on the day of the switch that it was never exercised — is a
site whose every page is suddenly a 500.

**Everything interpolated is escaped, without exception.** A post title is user input that
a moderator approved, not user input that a parser checked: `escape()` turns `<`, `>`, `&`,
`"` and `'` into entities, which is what keeps a title containing `</title><script>` a
title. The same function is used for the body text of the minimal page, so there is one
answer rather than a per-field judgement call.
"""
import os
import re

from django.conf import settings
from django.utils.html import escape

from .previews import LOCALE, SITE_NAME

# Where the frontend build's SPA shell is, for mode (a). Read through `getattr` rather
# than declared in settings.py because config/ belongs to the rest of the project and this
# app is meant to be addable in two lines; an environment variable works with neither
# touched. A deployment that settles on mode (a) should promote it to a real setting.
SPA_INDEX_SETTING = 'FUWLOL_SPA_INDEX'


def spa_index_path() -> str:
    return str(getattr(settings, SPA_INDEX_SETTING, '') or os.environ.get(SPA_INDEX_SETTING, '') or '')


def read_spa_index() -> str | None:
    """The built shell, or None — and None is a supported answer, not an error. In mode (b)
    the file is deliberately absent (it lives in the other container), and in dev nobody
    has run `npm run build` at all. Re-read per request on purpose: the file is two
    kilobytes in the page cache, and caching it would mean a deploy serving the previous
    build's asset hashes until somebody restarted gunicorn."""
    path = spa_index_path()
    if not path:
        return None
    try:
        with open(path, encoding='utf-8') as fh:
            return fh.read()
    except OSError:
        # Configured but unreadable is worth knowing about, and worth surviving: the
        # minimal page below still carries every tag a scraper needs.
        return None


def _meta(attr: str, key: str, value) -> str:
    return f'<meta {attr}="{escape(key)}" content="{escape(str(value))}">'


def head_tags(preview) -> str:
    """Every tag a scraper reads, newest-standard first, one per line.

    `og:*` is what Facebook, Messenger, WhatsApp, Telegram, Slack, Discord, LinkedIn and
    iMessage read. `twitter:*` is Twitter/X's own, and repeating the title, description
    and image there rather than relying on their og: fallback costs four lines and removes
    a dependency on somebody else's fallback logic. `<title>` and `<meta name=description>`
    are for Google, which reads neither of the other two as gospel.

    `twitter:card` is always `summary_large_image`, because every image this project emits
    is either a real attachment or one of the generated 1200×630 cards — see
    `previews.PERSON_CARDS` for why the faculty's 130 px silhouettes are never linked
    directly.
    """
    p = preview
    out = [f'<title>{escape(p.title)}</title>',
           _meta('name', 'description', p.description)]
    if not p.noindex:
        out.append(f'<link rel="canonical" href="{escape(p.url)}">')
    else:
        # A page nobody should index: the login form, a random-post redirect, and every
        # 404. Saying so is cheaper than explaining later why Google has the login form.
        out.append(_meta('name', 'robots', 'noindex, follow'))
    out += [
        _meta('property', 'og:site_name', SITE_NAME),
        _meta('property', 'og:locale', LOCALE),
        _meta('property', 'og:type', p.type),
        _meta('property', 'og:title', p.title),
        _meta('property', 'og:description', p.description),
        _meta('property', 'og:url', p.url),
    ]
    if p.image:
        out += [_meta('property', 'og:image', p.image),
                _meta('property', 'og:image:alt', p.image_alt)]
    if p.published_time is not None:
        out.append(_meta('property', 'article:published_time', p.published_time.isoformat()))
    for tag in p.tags:
        out.append(_meta('property', 'article:tag', tag))
    out += [
        _meta('name', 'twitter:card', 'summary_large_image'),
        _meta('name', 'twitter:title', p.title),
        _meta('name', 'twitter:description', p.description),
    ]
    if p.image:
        out += [_meta('name', 'twitter:image', p.image),
                _meta('name', 'twitter:image:alt', p.image_alt)]
    return '\n'.join(out)


# The page a crawler gets in mode (b). It is readable with JavaScript switched off, which
# is the point: a scraper that falls back to reading the body (several do, and Google is
# one) must find the same title and the same sentence the tags promise. No <img>: the
# site's CSP allows images from this origin only, and a picture on this page would be
# blocked in a browser while adding nothing for a scraper, which reads og:image.
_MINIMAL = """<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{tags}
<style>
body {{ font-family: Tahoma, Verdana, Arial, sans-serif; font-size: 13px; color: #444;
       background: #fff; margin: 0; }}
.bar {{ background: #175e4c; color: #fff; padding: 8px 16px; font-weight: bold; }}
.bar a {{ color: #fff; text-decoration: none; }}
.in {{ max-width: 900px; margin: 0 auto; padding: 16px; }}
h1 {{ font-size: 20px; color: #222; margin: 0 0 8px; }}
a {{ color: #a84204; }}
</style>
</head>
<body>
<div class="bar"><a href="{site}">✱ fuw.lol</a> — archiwum Wydziału Fizyki UW</div>
<div class="in">
<h1>{title}</h1>
<p>{description}</p>
<p><a href="{url}">{url}</a></p>
</div>
</body>
</html>
"""


def minimal_page(preview) -> str:
    from .previews import site_url
    return _MINIMAL.format(tags=head_tags(preview), site=escape(site_url() or '/'),
                           title=escape(preview.title), description=escape(preview.description),
                           url=escape(preview.url))


# What the SPA shell already carries and this module is about to say better:
# frontend/src/app.html holds a generic fallback card (og:site_name, og:image, a Polish
# description) so that an unrouted scraper still gets something. In mode (a) those tags
# would sit in the SAME document as the per-page ones — and a duplicated og:title is not
# a tie, it is a loss: consumers take the FIRST occurrence, which would be the generic one
# every time, and the splice would appear to do nothing. So they come out first.
_SUPERSEDED_META = re.compile(
    r"""<meta\s[^>]*?(?:property|name)\s*=\s*["'](?:og:[^"']*|twitter:[^"']*|description|robots)["'][^>]*>""",
    re.I)
_SUPERSEDED_LINK = re.compile(r"""<link\s[^>]*?rel\s*=\s*["']canonical["'][^>]*>""", re.I)


def splice(index_html: str, preview) -> str | None:
    """The built shell with our tags in its `<head>` — mode (a). None when the file is not
    a document we recognise, so the caller can fall back rather than serve half a page.

    The existing `<title>`, og:/twitter: metas, description and canonical are REMOVED
    rather than left in place: two of any of them in one document is undefined behaviour
    dressed up as a choice, and the one that loses is whichever the scraper reads second.
    Everything else in the head — the module preloads, the stylesheet, the icon, the
    charset — is untouched, because it is what makes the page still be the application.
    """
    if '</head>' not in index_html:
        return None
    head, sep, rest = index_html.partition('</head>')
    head = re.sub(r'<title\b[^>]*>.*?</title>', '', head, count=1, flags=re.S | re.I)
    head = _SUPERSEDED_META.sub('', head)
    head = _SUPERSEDED_LINK.sub('', head)
    return head + head_tags(preview) + '\n' + sep + rest


def render(preview) -> str:
    """The document for this preview: the real SPA shell when one is configured and
    readable, the minimal page otherwise. One function, so a view never has to know which
    delivery mode it is running in."""
    index_html = read_spa_index()
    if index_html:
        spliced = splice(index_html, preview)
        if spliced:
            return spliced
    return minimal_page(preview)
