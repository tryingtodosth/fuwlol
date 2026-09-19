"""Included from config/urls.py under 'api/', BEFORE archive.urls — the archive's router
owns `people/<slug>/`, and a router is a greedy neighbour to live next to (the portraits
app hangs off the same prefix for the same reason)."""
from django.urls import path

from .views import (ClaimConfirmView, ClaimDecideView, ClaimManageView, ClaimQueueView,
                    ClaimWithdrawView, ManageLinkView, PersonClaimView)

urlpatterns = [
    path('people/<slug:slug>/claims/', PersonClaimView.as_view()),
    path('people/<slug:slug>/claims/manage-link/', ManageLinkView.as_view()),
    path('claims/confirm/', ClaimConfirmView.as_view()),
    path('claims/manage/', ClaimManageView.as_view()),
    path('claims/manage/withdraw/', ClaimWithdrawView.as_view()),
    path('claims/queue/', ClaimQueueView.as_view()),
    path('claims/<int:pk>/decide/', ClaimDecideView.as_view()),
]
