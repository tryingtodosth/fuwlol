"""Real client address behind a proxy. Every per-IP throttle (registration, login, guest
chat, reports) and every stored `ip_hash` keys on REMOTE_ADDR; behind Traefik and/or
Cloudflare that is the proxy's own address, so one visitor's budget would be everybody's.

Two settings, both off by default, because a forwarded header is only worth what the hop
that wrote it is worth:

* FUWLOL_TRUST_PROXY=1 + FUWLOL_PROXY_HOPS=N — take the N-th address FROM THE RIGHT of
  X-Forwarded-For. Each trusted proxy appends exactly one address, so the rightmost N were
  written by proxies we run; everything left of them is whatever the client sent and is
  ignored. `[0]` (the leftmost) is the classic mistake: it is client-controlled, and lets
  one visitor mint a fresh throttle budget per request. N=1 for nginx alone, 2 for
  Traefik (Coolify) → nginx.
* FUWLOL_CLOUDFLARE=1 — additionally trust CF-Connecting-IP. Only correct when the origin
  accepts connections from Cloudflare's ranges alone (firewall / Tunnel); otherwise anyone
  can send that header straight to the origin and it is the same hole again.
"""
from django.conf import settings


def client_ip(meta):
    if settings.FUWLOL_CLOUDFLARE:
        cf = (meta.get('HTTP_CF_CONNECTING_IP') or '').strip()
        if cf:
            return cf
    if settings.FUWLOL_TRUST_PROXY:
        chain = [a.strip() for a in (meta.get('HTTP_X_FORWARDED_FOR') or '').split(',') if a.strip()]
        hops = max(1, settings.FUWLOL_PROXY_HOPS)
        if len(chain) >= hops:
            return chain[-hops]
    return None


class RealIpMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ip = client_ip(request.META)
        if ip:
            request.META['REMOTE_ADDR'] = ip
        return self.get_response(request)
