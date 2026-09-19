"""Included from config/urls.py under 'api/', BEFORE archive.urls — the archive's router
owns `people/<slug>/`, and a router is a greedy neighbour to live next to."""
from django.urls import path

from .views import PersonPortraitsView, PortraitModerateView, PortraitQueueView, PortraitVoteView

urlpatterns = [
    path('people/<slug:slug>/portraits/', PersonPortraitsView.as_view()),
    path('portraits/queue/', PortraitQueueView.as_view()),
    path('portraits/<int:pk>/vote/', PortraitVoteView.as_view()),
    path('portraits/<int:pk>/moderate/', PortraitModerateView.as_view()),
]
