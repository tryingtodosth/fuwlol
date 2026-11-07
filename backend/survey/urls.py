from django.urls import path

from .views import SurveyView, SurveyWithdrawView

urlpatterns = [
    path('', SurveyView.as_view()),
    path('withdraw/', SurveyWithdrawView.as_view()),
]
