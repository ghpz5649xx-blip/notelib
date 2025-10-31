# apps/pipelines/views.py
"""
Vues API REST pour la gestion des pipelines.

Endpoints :
- GET /api/pipelines/ : Liste
- POST /api/pipelines/ : Création
- GET /api/pipelines/{id}/ : Détails
- PUT /api/pipelines/{id}/ : Mise à jour
- DELETE /api/pipelines/{id}/ : Suppression
- POST /api/pipelines/{id}/validate/ : Validation
- POST /api/pipelines/{id}/duplicate/ : Duplication
"""
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import PermissionDenied

from .models import Pipeline, PipelineTemplate
from .serializers import (
    PipelineSerializer,
    PipelineCreateSerializer,
    PipelineTemplateSerializer,
)
from .services import pipeline_service, PipelineValidationError

logger = logging.getLogger("notelib")


class PipelineViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour la gestion CRUD des pipelines.
    
    Permissions :
    - Liste/Lecture : Authentifié (filtre par owner)
    - Création : Authentifié
    - Modification/Suppression : Owner ou admin
    """
    
    serializer_class = PipelineSerializer
    permission_classes = [IsAuthenticated]

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        # pipeline = request.data
        # pipeline['owner'] = request.user
        serializer = self.get_serializer(instance, data=request.data, partial=False)

        if not serializer.is_valid():
            logger.error("❌ Serializer errors: %s", serializer.errors)
            print("❌ Serializer errors:", serializer.errors)  # Affichage direct en console
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        self.perform_update(serializer)
        logger.info("✅ Pipeline updated successfully: %s", instance.name)
        return Response(serializer.data)
    
    def get_queryset(self):
        """Filtre par propriétaire si non-admin."""
        queryset = Pipeline.objects.select_related('owner').all()
        
        # Non-admin : seulement ses propres pipelines
        if not self.request.user.is_staff:
            queryset = queryset.filter(owner=self.request.user)
        
        # Filtrage optionnel
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        is_valid = self.request.query_params.get('is_valid')
        if is_valid is not None:
            queryset = queryset.filter(is_valid=is_valid.lower() == 'true')
        
        return queryset.order_by('-updated_at')
    
    def perform_create(self, serializer):
        """Assigne l'owner et valide automatiquement."""
        pipeline = serializer.save(owner=self.request.user)
        
        # Validation automatique
        is_valid, errors = pipeline_service.validate_and_save(pipeline)
        
        if not is_valid:
            logger.warning(
                f"Pipeline created but invalid: {pipeline.name}\n"
                f"Errors: {errors}"
            )
    
    def perform_update(self, serializer):
        """Revalide après modification."""
        pipeline = serializer.save()
        
        # Revalidation
        pipeline_service.validate_and_save(pipeline)
    
    def destroy(self, request, *args, **kwargs):
        """Vérifie ownership avant suppression."""
        pipeline = self.get_object()
        
        # Vérification ownership
        if pipeline.owner != request.user and not request.user.is_staff:
            raise PermissionDenied("You don't own this pipeline")
        
        # Vérification si des runs sont en cours
        active_runs = pipeline.runs.filter(
            status__in=['PENDING', 'RUNNING']
        ).count()
        
        if active_runs > 0:
            return Response(
                {
                    'error': f'Cannot delete pipeline: {active_runs} run(s) in progress'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return super().destroy(request, *args, **kwargs)
    
    @action(detail=True, methods=['post'])
    def validate(self, request, pk=None):
        """
        Valide un pipeline manuellement.
        
        POST /api/pipelines/{id}/validate/
        
        Retourne les erreurs de validation le cas échéant.
        """
        try:
            pipeline = self.get_object()
            
            is_valid, errors = pipeline_service.validate_and_save(pipeline)
            
            if is_valid:
                # Calcul du tri topologique
                try:
                    execution_order = pipeline_service.topological_sort(pipeline.graph)
                    layers = pipeline_service.get_execution_layers(pipeline.graph)
                    
                    return Response({
                        'status': 'valid',
                        'execution_order': execution_order,
                        'execution_layers': layers,
                    })
                except PipelineValidationError as e:
                    return Response({
                        'status': 'invalid',
                        'errors': [str(e)],
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({
                    'status': 'invalid',
                    'errors': errors,
                }, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            logger.error(f"Error validating pipeline {pk}: {e}", exc_info=True)
            return Response(
                {'error': 'Internal server error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """
        Duplique un pipeline.
        
        POST /api/pipelines/{id}/duplicate/
        {
            "name": "Copy of Original"
        }
        """
        try:
            original = self.get_object()
            
            new_name = request.data.get('name', f"Copy of {original.name}")
            
            # Création de la copie
            duplicate = Pipeline.objects.create(
                name=new_name,
                description=original.description,
                owner=request.user,
                graph=original.graph.copy(),
                tags=original.tags.copy() if original.tags else [],
            )
            
            # Validation
            pipeline_service.validate_and_save(duplicate)
            
            serializer = PipelineSerializer(duplicate)
            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED
            )
        
        except Exception as e:
            logger.error(f"Error duplicating pipeline {pk}: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def export(self, request, pk=None):
        """
        Exporte un pipeline au format JSON.
        
        GET /api/pipelines/{id}/export/
        """
        try:
            pipeline = self.get_object()
            
            export_data = {
                'name': pipeline.name,
                'description': pipeline.description,
                'graph': pipeline.graph,
                'version': pipeline.version,
                'tags': pipeline.tags,
                'exported_at': pipeline.updated_at.isoformat(),
            }
            
            return Response(export_data)
        
        except Exception as e:
            logger.error(f"Error exporting pipeline {pk}: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def import_pipeline(self, request):
        """
        Importe un pipeline depuis JSON.
        
        POST /api/pipelines/import_pipeline/
        {
            "name": "Imported Pipeline",
            "description": "...",
            "graph": {...}
        }
        """
        try:
            name = request.data.get('name')
            description = request.data.get('description', '')
            graph = request.data.get('graph')
            
            if not name or not graph:
                return Response(
                    {'error': 'Missing required fields: name, graph'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Création
            pipeline = Pipeline.objects.create(
                name=name,
                description=description,
                owner=request.user,
                graph=graph,
            )
            
            # Validation
            pipeline_service.validate_and_save(pipeline)
            
            serializer = PipelineSerializer(pipeline)
            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED
            )
        
        except Exception as e:
            logger.error(f"Error importing pipeline: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PipelineTemplateViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour la gestion des templates de pipeline.
    """
    
    serializer_class = PipelineTemplateSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filtre par visibilité."""
        queryset = PipelineTemplate.objects.all()
        
        # Non-admin : seulement templates publics + propres créations
        if not self.request.user.is_staff:
            queryset = queryset.filter(
                models.Q(is_public=True) | models.Q(created_by=self.request.user)
            )
        
        return queryset.order_by('-usage_count', '-created_at')
    
    def perform_create(self, serializer):
        """Assigne le créateur."""
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def instantiate(self, request, pk=None):
        """
        Crée un pipeline depuis un template.
        
        POST /api/pipelines/templates/{id}/instantiate/
        {
            "name": "My Pipeline"
        }
        """
        try:
            template = self.get_object()
            name = request.data.get('name')
            
            if not name:
                return Response(
                    {'error': 'Missing required field: name'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Instanciation
            pipeline = template.instantiate(request.user, name)
            
            # Validation
            pipeline_service.validate_and_save(pipeline)
            
            serializer = PipelineSerializer(pipeline)
            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED
            )
        
        except Exception as e:
            logger.error(f"Error instantiating template {pk}: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )