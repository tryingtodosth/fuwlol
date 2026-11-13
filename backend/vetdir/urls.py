from django.urls import path

from . import views

urlpatterns = [
    path('listings/', views.ListingsView.as_view()),
    # Before `<public_id>/`: an id is 12 characters, so the two never meet, but say it anyway.
    path('listings/confirm/', views.ListingConfirmView.as_view()),
    path('listings/<str:public_id>/', views.ListingView.as_view()),
    path('listings/<str:public_id>/unlist/', views.UnlistView.as_view()),
    path('listings/<str:public_id>/requests/', views.RequestsView.as_view()),
    path('listings/<str:public_id>/requests/<str:request_id>/', views.RequestDecisionView.as_view()),
    path('requests/confirm/', views.RequestConfirmView.as_view()),
    path('requests/cancel/', views.RequestCancelView.as_view()),
]
