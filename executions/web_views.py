# apps/executions/views.py
from django.shortcuts import render, get_object_or_404
from pipelines.models import Pipeline
from django.contrib.auth.decorators import login_required


@login_required
def launch_pipeline_view(request, pipeline_id):
    """
    Page permettant de lancer une exécution pour un pipeline spécifique.
    """
    pipeline = get_object_or_404(Pipeline, id=pipeline_id)

    # Vérification des permissions
    if pipeline.owner != request.user and not request.user.is_staff:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("Vous n'êtes pas autorisé à exécuter ce pipeline.")

    context = {
        "pipeline_id": str(pipeline.id),
        "pipeline_name": pipeline.name,
    }
    return render(request, "runs/launch.html", context)
