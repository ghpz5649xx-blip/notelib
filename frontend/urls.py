# notelib/frontend/urls.py
"""
URLs pour le frontend NoteLib.
Utilise TemplateView pour servir les templates HTML statiques.
Toute la logique est côté client en JavaScript.
"""

from django.urls import path
from django.views.generic import TemplateView

app_name = 'frontend'

urlpatterns = [
    # Pipelines
    path(
        "pipelines/",
        TemplateView.as_view(template_name="pipelines/list.html"),
        name="pipelines_list"
    ),
    path(
        "pipelines/<uuid:id>/",
        TemplateView.as_view(template_name="pipelines/detail.html"),
        name="pipeline_detail"
    ),
    path(
        "pipelines/<uuid:id>/edit/",
        TemplateView.as_view(template_name="pipelines/edit.html"),
        name="pipeline_edit"
    ),
    
    # Artefacts
    path(
        "artefacts/",
        TemplateView.as_view(template_name="artefacts/list.html"),
        name="artefacts_list"
    ),
    path(
        "artefacts/<str:hash>/",
        TemplateView.as_view(template_name="artefacts/detail.html"),
        name="artefact_detail"
    ),
    
    # Executions (Runs)
    path(
        "runs/",
        TemplateView.as_view(template_name="runs/list.html"),
        name="runs_list"
    ),
    path(
        "runs/<uuid:id>/",
        TemplateView.as_view(template_name="runs/detail.html"),
        name="run_detail"
    ),
    path(
        "runs/launch/",
        TemplateView.as_view(template_name="runs/launch.html"),
        name="run_launch"
    ),
]