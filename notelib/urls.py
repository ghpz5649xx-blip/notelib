from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from wiki.urls import get_pattern as get_wiki_pattern
from .views import article_tree_api

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # API du server
    path("api/", include("features.urls")),

    # API pour l'arborescence
    path('api/article-tree/', article_tree_api, name='article_tree_api'),

    # UI Notebooks
    path('notebooks/', include('notebooks.urls')),

    # Artefacts
    path('api/artefacts/', include('artefacts.urls')),

    # Pipelines
    path('api/pipelines/', include('pipelines.urls')),

    # Executions
    path('api/runs/', include('executions.urls')),
    
    # Django-nyt notifications (requis par django-wiki)
    path('notifications/', include('django_nyt.urls')),

    # Front end racine
    path('', include('frontend.urls')),

    # --- Vue HTML ---
    path('runs/', include('executions.web_urls')),

    # Wiki URLs - accessible à la racine
    path('', get_wiki_pattern()),
]

# Servir les fichiers média en développement
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)