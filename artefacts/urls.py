# apps/artefacts/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ArtefactViewSet

app_name = 'artefacts'

router = DefaultRouter()
router.register(r'', ArtefactViewSet, basename='artefact')

urlpatterns = [
    path('', include(router.urls)),
]