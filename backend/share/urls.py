"""Mounted once, from config/urls.py: `path('share/', include('share.urls'))`.

The catch-all is last and matches everything, including the empty path, because the whole
job of this app is to have an answer for any URL the SPA would have routed — including the
ones it would have 404ed, which get the generic card and a 404 of their own.
"""
from django.urls import path, re_path

from .views import PreviewView, SitemapView

urlpatterns = [
    # /sitemap.xml at the site root is proxied here by frontend/nginx.conf; in dev it is
    # reachable directly at /share/sitemap.xml.
    path('sitemap.xml', SitemapView.as_view()),
    re_path(r'^(?P<path>.*)$', PreviewView.as_view()),
]
