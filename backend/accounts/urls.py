from django.urls import path
from . import views
urlpatterns = [
    path('register/', views.RegisterView.as_view()),
    path('login/', views.LoginView.as_view()),
    path('logout/', views.LogoutView.as_view()),
    path('me/', views.MeView.as_view()),
    path('verify/request/', views.VerifyRequestView.as_view()),
    path('verify/confirm/', views.VerifyConfirmView.as_view()),
    path('trusted-domains/', views.TrustedDomainsView.as_view()),
]
