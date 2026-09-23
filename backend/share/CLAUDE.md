# share — link previews for scrapers, and the sitemap

No models, no migrations, no admin. Every URL of the SPA is served the same `200.html`, and no
scraper — Messenger, WhatsApp, Telegram, Slack, Google — runs JavaScript, so a shared `/wpis/…` used
to preview as the bare site title. Reasoning: `DESIGN.md` "Link previews"; operations:
`deploy/OVH.md` "Link previews". 43 tests.

## How a request gets here

nginx (`frontend/nginx.conf`) matches the User-Agent against the same list as `views.CRAWLER_UA`
(17 tokens; **the two lists must stay in step**, both files say so), and for a path with no dot in
it rewrites the request to `/share<path>`; Django's `PreviewView` catch-all answers a small page
with `<title>`, `og:*`, `twitter:*`, description and canonical, `max-age=300`. A human who reaches
`/share/…` is redirected to the real page (`FUWLOL_SHARE_REDIRECT_HUMANS`). `/sitemap.xml` is the
same app (`SitemapView`, `max-age=3600`, `SITEMAP_LIMIT` 5000: published posts, listed people,
subjects, categories, the standing pages), named from `robots.txt`.

## Rules

- **Ask the rules, never restate them.** `previews.preview_for(path, query)` calls
  `archive.moderation.can_see_post(None, …)`, `archive.people.visible_people(None)`,
  `person_posts_q`, `portraits.rules.current_portrait`. A hidden, nuked or escalated post gets the
  generic site card **and a 404 byte-identical to a slug that never existed** — a leak here would
  outlive the takedown, because a preview is cached on somebody else's servers.
- Images are absolute: R2 URLs as-is, `/media` prefixed with `FUWLOL_SITE_URL`. A person without a
  portrait gets a 1200×630 card with the faculty silhouette (`og-osoba-{m,f}.png`, and `og-osoba.png`
  with the neutral bust when `sex` is unset — `PERSON_CARDS`, the same three the profile page shows),
  because Facebook drops any image under 200×200 and the silhouettes are 130×130. The fallback cards are drawn
  by `manage.py make_share_images` into `frontend/static/` and committed; re-run it if their wording
  changes.
- `strip_math` / `clean_text` cut a description to `MAX_DESCRIPTION` 200 without half a formula;
  `plural()` is mirrored in `frontend/src/lib/plural.ts` — both docstrings name the other.
- The splice mode — Django serving the real `200.html` with the tags in its `<head>`, for everybody,
  no User-Agent anywhere (`FUWLOL_SPA_INDEX` + `FUWLOL_SHARE_REDIRECT_HUMANS=0`) — is implemented
  and tested for the day the SPA and Django share a filesystem. Today they are two containers, so
  mode b runs; the Django side needs no change when the packaging does.

## After a deploy

Scrapers keep what they cached: paste an already-shared URL into
developers.facebook.com/tools/debug and *Scrape Again* (Telegram: `@WebpageBot`). Check with
`curl -A "facebookexternalhit/1.1" https://fuw.lol/wpis/<slug> | grep og:` — and that a **hidden**
post's URL gives the plain card. Never give Cloudflare a "Cache Everything" rule on HTML: one URL
answers differently by User-Agent and Cloudflare honours `Vary` on `Accept-Encoding` only. nginx
cannot be tested locally — `docker compose exec web nginx -t` on the box after touching the maps.
