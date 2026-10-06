from django.urls import path

from . import views

urlpatterns = [
    path('auth/register/', views.RegisterView.as_view()),
    path('auth/login/', views.LoginView.as_view()),
    path('auth/logout/', views.LogoutView.as_view()),
    path('auth/me/', views.MeView.as_view()),
    path('templates/', views.TemplateListView.as_view()),
    path('templates/<slug:slug>/', views.TemplateDetailView.as_view()),
    path('publications/', views.PublicationListView.as_view()),
    # Before `<uuid:public_id>/` for readability; the converter would not match "mine" anyway.
    path('publications/mine/', views.PublicationMineView.as_view()),
    path('publications/<uuid:public_id>/', views.PublicationDetailView.as_view()),
    path('publications/<uuid:public_id>/withdraw/', views.PublicationWithdrawView.as_view()),
]
