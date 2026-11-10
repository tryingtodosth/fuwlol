from django.urls import path

from .views import ConfirmView, SubscribeView, UnsubscribeView

urlpatterns = [
    path('', SubscribeView.as_view()),
    path('confirm/', ConfirmView.as_view()),
    path('unsubscribe/', UnsubscribeView.as_view()),
]
