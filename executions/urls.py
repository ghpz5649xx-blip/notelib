# ============================================================
# apps/executions/urls.py
# ============================================================
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PipelineRunViewSet

app_name = 'executions'

router = DefaultRouter()
router.register(r'', PipelineRunViewSet, basename='run')

urlpatterns = [
    path('', include(router.urls)),
]