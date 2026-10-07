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
    # The practice round. `practice/me/…` is the practitioner's own; `practices/…` is public;
    # `visits/…` and `notes/mine/` are the patient's.
    path('practices/', views.PracticeListView.as_view()),
    path('practices/<uuid:public_id>/', views.PracticeDetailView.as_view()),
    path('practices/<uuid:public_id>/slots/', views.PracticeSlotsView.as_view()),
    path('practice/me/', views.PracticeMeView.as_view()),
    path('practice/me/visits/', views.PracticeVisitsView.as_view()),
    path('practice/me/patients/', views.PracticePatientsView.as_view()),
    path('practice/me/patients/<str:username>/', views.PracticePatientView.as_view()),
    path('practice/me/notes/<uuid:public_id>/share/', views.NoteShareView.as_view()),
    path('visits/', views.VisitsView.as_view()),
    path('visits/mine/', views.VisitsMineView.as_view()),
    path('visits/<uuid:public_id>/<slug:action>/', views.VisitActionView.as_view()),
    path('notes/mine/', views.NotesMineView.as_view()),
]
