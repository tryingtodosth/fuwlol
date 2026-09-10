"""Real client address behind a proxy. Every per-IP throttle (registration, login, guest
chat, reports) keys on REMOTE_ADDR; behind Traefik and/or Cloudflare that is the proxy's
own address, so one visitor's budget would be everybody's. Enabled only when
FUWLOL_TRUST_PROXY=1 — with a directly exposed server a client could forge the header."""
from django.conf import settings


class RealIpMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.FUWLOL_TRUST_PROXY:
            ip = (request.META.get('HTTP_CF_CONNECTING_IP')  # Cloudflare sets this to the visitor
                  or (request.META.get('HTTP_X_FORWARDED_FOR') or '').split(',')[0].strip())
            if ip:
                request.META['REMOTE_ADDR'] = ip
        return self.get_response(request)
