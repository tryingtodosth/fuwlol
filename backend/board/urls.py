from django.urls import path

from .feeds import BoardFeed
from .views import BoardView, HideView

urlpatterns = [
    path('', BoardView.as_view()),
    path('rss/', BoardFeed()),
    path('<int:pk>/hide/', HideView.as_view(hidden=True)),
    path('<int:pk>/restore/', HideView.as_view(hidden=False)),
]
