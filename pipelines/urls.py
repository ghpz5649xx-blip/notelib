# ============================================================
# apps/pipelines/urls.py
# ============================================================
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PipelineViewSet, PipelineTemplateViewSet

app_name = 'pipelines'

router = DefaultRouter()
router.register(r'', PipelineViewSet, basename='pipeline')
router.register(r'templates', PipelineTemplateViewSet, basename='template')

urlpatterns = [
    path('', include(router.urls)),
]