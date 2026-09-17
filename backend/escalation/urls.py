from django.urls import path

from . import views

urlpatterns = [
    path('escalations/', views.EscalationListView.as_view()),
    path('escalations/<int:pk>/', views.EscalationDetailView.as_view()),
    path('escalations/<int:pk>/decide/', views.EscalationDecideView.as_view()),
    path('escalations/<int:pk>/evidence/<str:filename>', views.EscalationEvidenceFileView.as_view()),
]
