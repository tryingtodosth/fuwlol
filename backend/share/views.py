r"""The endpoints: one page of tags per URL, and a sitemap.

**How a request gets here (mode b).** nginx matches the User-Agent against the scraper
list and rewrites `/wpis/x` to `/share/wpis/x` internally, so the crawler asks for — and
caches — the canonical URL while Django answers it. Nothing about the address a human
sees changes, and a human who is somehow handed a `/share/…` link is bounced back to the
canonical one with a 302 rather than shown a page with no application on it.

**Why the User-Agent is looked at twice.** nginx decides who is routed here; this module
decides only whether to redirect somebody back out. The two lists must stay in step —
`frontend/nginx.conf` holds the other copy, and both say so — but they answer different
questions, and getting the second one wrong costs a redirect, not a leak. That asymmetry
is deliberate: the preview itself never depends on who is asking, so there is no
user-agent branch anywhere near the content.

**Cloudflare sits in front of all of this.** HTML is not in its default cache set (it
caches by file extension), so one URL answering differently by User-Agent is safe as
things stand — but a „Cache Everything" rule would make it unsafe immediately, because
Cloudflare honours `Vary` on `Accept-Encoding` alone. `Vary: User-Agent` is sent anyway,
for every other cache between here and the reader, and deploy/OVH.md states the rule in
prose so nobody adds that page rule without meeting this sentence first.
"""
import os
import re

from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.utils.html import escape
from django.views import View

from archive.models import Category

from .html import render
from .previews import canonical, generic_preview, normalise_path, preview_for, site_url

# The same list as `frontend/nginx.conf`'s `$fuwlol_crawler` map — keep the two in step.
# Every entry is a scraper that fetches a URL to draw a card and runs no JavaScript:
# Facebook and Messenger (facebookexternalhit/Facebot), X, LinkedIn, WhatsApp, Telegram,
# Slack, Discord, iMessage (Applebot), Google, Bing, Pinterest, Reddit, the two embed
# services, Skype and Signal.
CRAWLER_UA = re.compile(
    r'facebookexternalhit|Facebot|Twitterbot|LinkedInBot|WhatsApp|TelegramBot|Slackbot'
    r'|Discordbot|Applebot|Googlebot|bingbot|Pinterest|redditbot|Iframely|Embedly'
    r'|SkypeUriPreview|Signal', re.I)

PREVIEW_MAX_AGE = 300
SITEMAP_MAX_AGE = 3600
# How many rows of one kind the sitemap will list. The protocol's own ceiling is 50 000
# URLs / 50 MB per file, and an archive of faculty folklore is three orders of magnitude
# away from it — this is here so that the day it is not, the file stays valid and somebody
# has to come and split it deliberately.
SITEMAP_LIMIT = 5000


def _flag(name: str, default: str = '1') -> bool:
    return (str(getattr(settings, name, '') or os.environ.get(name, default)) == '1')


def is_crawler(request) -> bool:
    return bool(CRAWLER_UA.search(request.META.get('HTTP_USER_AGENT', '') or ''))


class PreviewView(View):
    """GET /share/<anything> — the tags for `<anything>`.

    Django's `View` answers HEAD with the same code as GET, which matters: several
    scrapers HEAD a URL before they fetch it, and a 405 there is read as „this link is
    broken" rather than as „this server is fussy".
    """

    def get(self, request, path=''):
        path = normalise_path(path)
        query = request.GET
        # Mode (b): a person who followed a /share/ link wants the site, not this page.
        # Done before anything is resolved, so a human is redirected just as fast for a
        # post that does not exist as for one that does.
        if _flag('FUWLOL_SHARE_REDIRECT_HUMANS') and not is_crawler(request):
            target = canonical(path, request.GET.urlencode()) if site_url() else path
            return HttpResponseRedirect(target)

        preview = preview_for(path, query)
        status = 200
        if preview is None:
            # Not published, not visible, or never existed — one answer for all three.
            preview = generic_preview()
            status = 404
        response = HttpResponse(render(preview), status=status, content_type='text/html; charset=utf-8')
        response['Cache-Control'] = f'public, max-age={PREVIEW_MAX_AGE}'
        response['Vary'] = 'User-Agent'
        return response


def _url_entry(loc: str, lastmod=None) -> str:
    """One <url> element. `escape` because a browse URL carries a query string, and a bare
    `&` is not XML — the one character that turns a sitemap into a parse error."""
    mod = f'<lastmod>{lastmod.date().isoformat()}</lastmod>' if lastmod else ''
    return f'<url><loc>{escape(loc)}</loc>{mod}</url>'


def build_sitemap() -> str:
    """Everything an anonymous visitor may read, once each.

    Built from the same queryset the previews are (`previews.public_posts`), so a hidden,
    pending or escalated post cannot be advertised to Google by the one surface nobody
    thinks to check. People come from `visible_people(None)` for the same reason.

    `lastmod` is a date, not a timestamp: the hour a post was published is nobody's
    business and the day is all a crawler acts on.
    """
    from archive.people import visible_people

    from .previews import STANDING, listed_subjects, public_posts

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
           _url_entry(canonical('/')),
           _url_entry(canonical('/przegladaj')),
           _url_entry(canonical('/ludzie')),
           _url_entry(canonical('/przedmioty'))]
    out += [_url_entry(canonical(path)) for path in STANDING]
    for post in public_posts().order_by('-published_at')[:SITEMAP_LIMIT]:
        out.append(_url_entry(canonical(f'/wpis/{post.slug}'), post.published_at))
    for person in visible_people(None)[:SITEMAP_LIMIT]:
        out.append(_url_entry(canonical(f'/ludzie/{person.slug}')))
    for subject in listed_subjects()[:SITEMAP_LIMIT]:
        out.append(_url_entry(canonical(f'/przedmioty/{subject.slug}')))
    for category in Category.objects.all()[:SITEMAP_LIMIT]:
        out.append(_url_entry(canonical('/przegladaj', f'category={category.slug}')))
    out.append('</urlset>')
    return '\n'.join(out)


class SitemapView(View):
    """GET /sitemap.xml (proxied to /share/sitemap.xml — see frontend/nginx.conf).

    Hand-built rather than `django.contrib.sitemaps`: that framework wants `get_absolute_url`
    on the models and a site whose URLs Django owns, and Django owns none of these — every
    address in here belongs to the SvelteKit router. Forty lines that state the truth beat a
    framework configured to lie about who serves what.
    """

    def get(self, request):
        response = HttpResponse(build_sitemap(), content_type='application/xml; charset=utf-8')
        response['Cache-Control'] = f'public, max-age={SITEMAP_MAX_AGE}'
        return response
