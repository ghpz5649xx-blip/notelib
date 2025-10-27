from django.urls import path
from . import views

app_name = 'notebooks'

urlpatterns = [
    path('', views.notebook_list, name='list'),
    path('upload/', views.notebook_upload, name='upload'),
    path('<int:pk>/', views.notebook_detail, name='detail'),
    path('<int:pk>/reprocess/', views.notebook_reprocess, name='reprocess'),
    path('<int:pk>/delete/', views.notebook_delete, name='delete'),
]