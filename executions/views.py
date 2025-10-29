# apps/executions/views.py
"""
Vues API REST pour la gestion des exécutions.

Endpoints :
- POST /api/pipelines/{id}/runs/ : Lancer une exécution
- GET /api/runs/ : Liste des exécutions
- GET /api/runs/{id}/ : Détails d'une exécution
- POST /api/runs/{id}/cancel/ : Annuler
- GET /api/runs/{id}/download/{node_id}/ : Télécharger artefact
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import PermissionDenied
from django.http import FileResponse

from .models import PipelineRun, StepRun
from .serializers import (
    PipelineRunSerializer,
    PipelineRunCreateSerializer,
    StepRunSerializer,
)
from .services import execution_service
from pipelines.models import Pipeline
from artefacts.services import artefact_service

logger = logging.getLogger("notelib")


class PipelineRunViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour la gestion des exécutions de pipeline.
    
    Permissions :
    - Création : Authentifié + ownership du pipeline
    - Lecture : Authentifié + ownership
    - Annulation : Owner ou admin
    """
    
    serializer_class = PipelineRunSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filtre par propriétaire si non-admin."""
        queryset = PipelineRun.objects.select_related(
            'pipeline', 'initiator'
        ).prefetch_related('step_runs').all()
        
        # Filtrage par owner (non-admin)
        if not self.request.user.is_staff:
            queryset = queryset.filter(initiator=self.request.user)
        
        # Filtrage optionnel par pipeline
        pipeline_id = self.request.query_params.get('pipeline')
        if pipeline_id:
            queryset = queryset.filter(pipeline_id=pipeline_id)
        
        # Filtrage par statut
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter.upper())
        
        return queryset.order_by('-created_at')
    
    def create(self, request, *args, **kwargs):
        """
        Lance une nouvelle exécution de pipeline.
        
        POST /api/pipelines/{pipeline_id}/runs/
        {
            "input_manifest": {
                "node_1": {"param1": "value1"},
                "node_2": {"input": "abc123..."}
            },
            "execution_mode": "async"
        }
        
        Note: Cette route est également accessible via :
        POST /api/runs/ avec "pipeline" dans le body
        """
        serializer = PipelineRunCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Récupération du pipeline
        pipeline_id = request.data.get('pipeline')
        if not pipeline_id:
            # Tentative depuis l'URL (si nested route)
            pipeline_id = self.kwargs.get('pipeline_id')
        
        if not pipeline_id:
            return Response(
                {'error': 'Missing pipeline ID'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            pipeline = Pipeline.objects.get(id=pipeline_id)
        except Pipeline.DoesNotExist:
            return Response(
                {'error': 'Pipeline not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Vérification ownership
        if pipeline.owner != request.user and not request.user.is_staff:
            raise PermissionDenied("You don't own this pipeline")
        
        try:
            # Création du run
            run = execution_service.create_run(
                pipeline=pipeline,
                input_manifest=serializer.validated_data['input_manifest'],
                initiator=request.user,
                execution_mode=serializer.validated_data['execution_mode'],
            )
            
            # Lancement selon le mode
            execution_mode = serializer.validated_data['execution_mode']
            
            if execution_mode == 'sync':
                # Exécution synchrone (bloquante)
                run = execution_service.execute_sync(str(run.id))
            else:
                # Exécution asynchrone (Celery)
                from .tasks import start_pipeline_run
                start_pipeline_run.delay(str(run.id))
            
            # Sérialisation de la réponse
            response_serializer = PipelineRunSerializer(run)
            
            return Response(
                response_serializer.data,
                status=status.HTTP_201_CREATED
            )
        
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error creating run: {e}", exc_info=True)
            return Response(
                {'error': 'Internal server error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Annule une exécution en cours.
        
        POST /api/runs/{id}/cancel/
        """
        try:
            run = self.get_object()
            
            # Vérification ownership
            if run.initiator != request.user and not request.user.is_staff:
                raise PermissionDenied("You didn't initiate this run")
            
            # Annulation
            run = execution_service.cancel_run(str(run.id))
            
            serializer = PipelineRunSerializer(run)
            return Response(serializer.data)
        
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error cancelling run {pk}: {e}", exc_info=True)
            return Response(
                {'error': 'Internal server error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """
        Télécharge l'artefact d'un step spécifique.
        
        GET /api/runs/{id}/download/?node_id=node_1
        
        Retourne le fichier .zst compressé.
        """
        try:
            run = self.get_object()
            node_id = request.query_params.get('node_id')
            
            if not node_id:
                return Response(
                    {'error': 'Missing node_id parameter'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Vérification ownership
            if run.initiator != request.user and not request.user.is_staff:
                raise PermissionDenied("You didn't initiate this run")
            
            # Récupération de l'artefact
            if node_id not in run.output_artefacts:
                return Response(
                    {'error': f'No artefact for node {node_id}'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            artefact_hash = run.output_artefacts[node_id]
            
            # Streaming
            file_stream = artefact_service.stream_artefact(
                artefact_hash,
                log_access=True,
                user=request.user
            )
            
            response = FileResponse(
                file_stream,
                content_type='application/zstd'
            )
            response['Content-Disposition'] = (
                f'attachment; filename="{node_id}_{artefact_hash[:8]}.zst"'
            )
            
            return response
        
        except Exception as e:
            logger.error(f"Error downloading artefact: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def logs(self, request, pk=None):
        """
        Récupère les logs d'exécution.
        
        GET /api/runs/{id}/logs/
        
        Retourne les logs consolidés ou par step.
        """
        try:
            run = self.get_object()
            
            # Vérification ownership
            if run.initiator != request.user and not request.user.is_staff:
                raise PermissionDenied("You didn't initiate this run")
            
            # Option : logs globaux ou par step
            step_id = request.query_params.get('step_id')
            
            if step_id:
                # Logs d'un step spécifique
                try:
                    step = run.step_runs.get(id=step_id)
                    return Response({
                        'node_id': step.node_id,
                        'status': step.status,
                        'stdout': step.stdout,
                        'stderr': step.stderr,
                        'error': step.error,
                    })
                except StepRun.DoesNotExist:
                    return Response(
                        {'error': 'Step not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            else:
                # Logs globaux
                steps_logs = []
                for step in run.step_runs.all():
                    steps_logs.append({
                        'node_id': step.node_id,
                        'status': step.status,
                        'stdout': step.stdout,
                        'stderr': step.stderr,
                        'error': step.error,
                    })
                
                return Response({
                    'run_id': str(run.id),
                    'status': run.status,
                    'logs': run.logs,
                    'error_message': run.error_message,
                    'steps': steps_logs,
                })
        
        except Exception as e:
            logger.error(f"Error retrieving logs: {e}", exc_info=True)
            return Response(
                {'error': 'Internal server error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        """
        Relance une exécution échouée.
        
        POST /api/runs/{id}/retry/
        
        Crée un nouveau run avec les mêmes inputs.
        """
        try:
            original_run = self.get_object()
            
            # Vérification ownership
            if original_run.initiator != request.user and not request.user.is_staff:
                raise PermissionDenied("You didn't initiate this run")
            
            # Création d'un nouveau run
            new_run = execution_service.create_run(
                pipeline=original_run.pipeline,
                input_manifest=original_run.input_manifest,
                initiator=request.user,
                execution_mode=original_run.execution_mode,
            )
            
            # Lancement
            if original_run.execution_mode == 'sync':
                new_run = execution_service.execute_sync(str(new_run.id))
            else:
                from .tasks import start_pipeline_run
                start_pipeline_run.delay(str(new_run.id))
            
            serializer = PipelineRunSerializer(new_run)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            logger.error(f"Error retrying run {pk}: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )