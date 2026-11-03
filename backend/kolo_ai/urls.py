from django.urls import path

from . import views

urlpatterns = [
    path('info/', views.InfoView.as_view()),
    path('status/', views.StatusListView.as_view()),
    path('status/<int:pk>/withdraw/', views.StatusWithdrawView.as_view()),
    path('join/', views.JoinView.as_view()),
    path('login/', views.LoginRequestView.as_view()),
    path('link/', views.LinkView.as_view()),
    path('me/', views.MeView.as_view()),
    path('logout/', views.LogoutView.as_view()),
    path('me/founder/', views.MyFounderView.as_view()),
    path('founders/', views.FounderListView.as_view()),
    path('settings/<str:key>/', views.SettingView.as_view()),
    path('members/', views.MemberListView.as_view()),
    path('members/<int:pk>/decide/', views.MemberDecideView.as_view()),
    path('invite/', views.InviteView.as_view()),
    path('polls/', views.PollListView.as_view()),
    path('polls/<int:pk>/', views.PollDetailView.as_view()),
    path('polls/<int:pk>/announce/', views.PollAnnounceView.as_view()),
    path('polls/<int:pk>/cancel/', views.PollCancelView.as_view()),
    path('polls/<int:pk>/vote/', views.VoteView.as_view()),
    path('polls/<int:pk>/object/', views.ObjectView.as_view()),
    path('polls/<int:pk>/comments/', views.CommentListView.as_view()),
    path('polls/<int:pk>/protocol/', views.ProtocolView.as_view()),
    path('comments/<int:pk>/hide/', views.CommentHideView.as_view()),
]
