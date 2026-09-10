from django.urls import path
from rest_framework.routers import DefaultRouter
from . import views
from .wayback import WaybackView

router = DefaultRouter()
router.register('categories', views.CategoryViewSet, basename='category')
router.register('people', views.PersonViewSet, basename='person')
router.register('tags', views.TagViewSet, basename='tag')
router.register('posts', views.PostViewSet, basename='post')
router.register('reports', views.ReportViewSet, basename='report')

urlpatterns = router.urls + [
    path('comments/<int:pk>/', views.CommentDeleteView.as_view()),
    path('comments/<int:pk>/hide/', views.CommentModerationView.as_view(), {'verb': 'hide'}),
    path('comments/<int:pk>/restore/', views.CommentModerationView.as_view(), {'verb': 'restore'}),
    path('comments/<int:pk>/nuke/', views.CommentModerationView.as_view(), {'verb': 'nuke'}),
    path('moderation/board/', views.ModerationBoardView.as_view()),
    path('wayback/', WaybackView.as_view()),
]
