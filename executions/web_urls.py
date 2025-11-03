# executions/web_urls.py
from django.urls import path
from .web_views import launch_pipeline_view

app_name = 'executions_web'

urlpatterns = [
    path('<uuid:pipeline_id>/launch/', launch_pipeline_view, name='launch_pipeline'),
]
