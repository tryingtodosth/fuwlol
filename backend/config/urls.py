from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/board/', include('board.urls')),
    path('api/moderation/', include('escalation.urls')),
    # MedApp's only call to a server (feedback/). Its own prefix, so nothing about it
    # depends on the archive router's greedy people/<slug>/ ordering below.
    path('api/feedback/', include('feedback.urls')),
    # BEFORE archive.urls: the archive's DefaultRouter owns `people/<slug>/`, and the
    # portrait gallery hangs one segment deeper under the same prefix.
    path('api/', include('portraits.urls')),
    path('api/', include('consent.urls')),
    path('api/', include('archive.urls')),
    # Link previews + sitemap.xml for the scrapers that do not run JavaScript (share/).
    path('share/', include('share.urls')),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
