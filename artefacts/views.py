# apps/artefacts/views.py
"""
Vues API REST pour la gestion des artefacts.

Endpoints :
- GET /api/artefacts/ : Liste
- POST /api/artefacts/ : Création (serveur sérialise)
- GET /api/artefacts/{hash}/ : Métadonnées
- GET /api/artefacts/{hash}/download/ : Téléchargement
- DELETE /api/artefacts/{hash}/ : Suppression
"""
import logging
import json
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, HttpResponse, FileResponse
from rest_framework.renderers import JSONRenderer
from .renderers import XLSXRenderer, CSVRenderer  # ton renderer XLSX custom

import pandas as pd

from .models import ArtefactMeta
from .serializers import (
    ArtefactMetaSerializer,
    ArtefactCreateSerializer,
    ArtefactStatsSerializer,
)
from .services import artefact_service

logger = logging.getLogger("notelib")


class ArtefactViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour la gestion CRUD des artefacts.
    
    Permissions :
    - Liste/Lecture : Authentifié
    - Création : Authentifié
    - Suppression : Authentifié + ownership ou admin
    """
    
    queryset = ArtefactMeta.objects.select_related('feature').all()
    serializer_class = ArtefactMetaSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'hash'
    renderer_classes = [JSONRenderer, CSVRenderer, XLSXRenderer]
    
    def get_queryset(self):
        """Filtre par propriétaire si non-admin."""
        queryset = super().get_queryset()
        
        # Filtrage optionnel par feature
        feature_hash = self.request.query_params.get('feature')
        if feature_hash:
            queryset = queryset.filter(feature__hash=feature_hash)
        
        # Filtrage par ref_count
        orphans_only = self.request.query_params.get('orphans_only')
        if orphans_only == 'true':
            queryset = queryset.filter(ref_count=0)
        
        return queryset.order_by('-created_at')
    
    def create(self, request, *args, **kwargs):
        """
        Crée un artefact depuis un objet Python.
        
        Note: Cette route est principalement utilisée en interne par
        le système d'exécution. Pour créer un artefact depuis un client,
        utiliser l'endpoint d'exécution de feature.
        
        POST /api/artefacts/
        {
            "feature_hash": "abc123...",
            "meta": {...}
        }
        
        L'objet Python doit être fourni dans request.data['obj']
        """
        serializer = ArtefactCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Extraction de l'objet Python (fourni directement, pas sérialisé en JSON)
        obj = request.data.get('obj')
        if obj is None:
            return Response(
                {'error': 'Missing "obj" in request data'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Création via le service
            artefact = artefact_service.create_artefact(
                obj=obj,
                feature_hash=serializer.validated_data.get('feature_hash'),
                meta=serializer.validated_data.get('meta', {})
            )
            
            # Sérialisation de la réponse
            response_serializer = ArtefactMetaSerializer(artefact)
            
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
            logger.error(f"Error creating artefact: {e}", exc_info=True)
            return Response(
                {'error': 'Internal server error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def download(self, request, hash=None):
        """
        Télécharge un artefact compressé.
        
        GET /api/artefacts/{hash}/download/
        
        Retourne le fichier .zst brut (pour client qui veut décompresser lui-même)
        ou l'objet désérialisé (si paramètre ?deserialize=true)
        """
        try:
            artefact = self.get_object()
            deserialize = request.query_params.get('deserialize', 'false').lower() in ['true', '1', 'yes']
            
            if  not deserialize:
                # Mode streaming pour gros fichiers
                file_stream = artefact_service.stream_artefact(
                    hash,
                    log_access=True,
                    user=request.user
                )

                response = FileResponse(
                    file_stream,
                    content_type='application/zstd'
                )
                response['Content-Disposition'] = f'attachment; filename="{hash[:8]}.zst"'
                response['Content-Length'] = artefact.size
                
                return response
            
            # Chargement
            obj = artefact_service.load_artefact(
                hash,
                log_access=True,
                user=request.user
            )

            logger.info(f"artefact après load {obj}")

            try:
                data = obj
            except json.JSONDecodeError:
                logger.error(f"Artefact {hash} n'est pas du JSON valide après décompression.")
                return Response(
                    {'error': 'Artefact non valide ou non désérialisable'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 🔧 Si l'objet est un DataFrame → conversion JSON propre
            if isinstance(data, pd.DataFrame):
                df = data.replace({float("inf"): None, float("-inf"): None})
                df = df.where(pd.notnull(df), None)
                payload = {
                    "columns": list(df.columns),
                    "rows": df.to_dict(orient="records"),
                    "count": len(df),
                }
                return JsonResponse(
                    payload,
                    safe=False,
                    json_dumps_params={"ensure_ascii": False},
                    content_type="application/json; charset=utf-8",
                )

            # 🔧 Sinon, renvoyer un JSON normal (avec UTF-8)
            return JsonResponse(
                data,
                safe=False,
                json_dumps_params={"ensure_ascii": False},
                content_type="application/json; charset=utf-8",
            )

            
            return Response(data)

            
        except ArtefactMeta.DoesNotExist:
            return Response(
                {'error': 'Artefact not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except FileNotFoundError:
            return Response(
                {'error': 'Artefact file missing on filesystem'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"Error downloading artefact {hash}: {e}", exc_info=True)
            return Response(
                {'error': 'Internal server error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def load(self, request, hash=None):
        """
        Charge et désérialise un artefact (retourne l'objet Python).
        
        GET /api/artefacts/{hash}/load/
        
        Note: Cette route nécessite une sérialisation JSON de l'objet Python,
        ce qui peut échouer pour des objets complexes. Préférer download()
        et désérialiser côté client si possible.
        """
        try:
            artefact = self.get_object()
            
            # Vérification ownership
            if artefact.feature and artefact.feature.uploaded_by:
                if (artefact.feature.uploaded_by != request.user 
                    and not request.user.is_staff):
                    raise PermissionDenied("You don't own this artefact")
            
            # Chargement
            obj = artefact_service.load_artefact(
                hash,
                log_access=True,
                user=request.user
            )
            
            # Tentative de sérialisation JSON
            # Note: Peut échouer pour des objets non-JSON-serializable
            try:
                return Response({
                    'hash': hash,
                    'data': obj,  # DRF tentera de sérialiser
                    'type': type(obj).__name__,
                })
            except Exception as e:
                return Response({
                    'hash': hash,
                    'error': 'Object not JSON-serializable',
                    'type': type(obj).__name__,
                    'repr': repr(obj)[:500],  # Aperçu limité
                })
            
        except ArtefactMeta.DoesNotExist:
            return Response(
                {'error': 'Artefact not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error loading artefact {hash}: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def destroy(self, request, *args, **kwargs):
        """
        Supprime un artefact.
        
        DELETE /api/artefacts/{hash}/
        
        Vérifie que ref_count=0 avant suppression.
        """
        try:
            artefact = self.get_object()
            hash_value = artefact.hash
            
            # Vérification ownership
            # if artefact.feature and artefact.feature.uploaded_by:
            #     if (artefact.feature.uploaded_by != request.user 
            #         and not request.user.is_staff):
            #         raise PermissionDenied("You don't own this artefact")
            
            # Suppression via le service (vérifie ref_count)
            force = request.query_params.get('force') == 'true' and request.user.is_staff
            
            artefact_service.delete_artefact(hash_value, force=force)
            
            return Response(
                {'status': 'deleted', 'hash': hash_value},
                status=status.HTTP_204_NO_CONTENT
            )
            
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error deleting artefact: {e}", exc_info=True)
            return Response(
                {'error': 'Internal server error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Retourne des statistiques sur les artefacts.
        
        GET /api/artefacts/stats/
        """
        try:
            stats = artefact_service.get_stats()
            serializer = ArtefactStatsSerializer(stats)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting artefact stats: {e}", exc_info=True)
            return Response(
                {'error': 'Internal server error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def cleanup(self, request):
        """
        Lance un nettoyage des artefacts orphelins.
        
        POST /api/artefacts/cleanup/
        
        Requiert admin.
        """
        if not request.user.is_staff:
            raise PermissionDenied("Admin only")
        
        try:
            fs_orphans, db_orphans = artefact_service.cleanup_orphans()
            
            return Response({
                'status': 'success',
                'fs_orphans': fs_orphans,
                'db_orphans': db_orphans,
            })
        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
    @action(detail=True, methods=['get'])
    def preview(self, request, hash=None):
        """
        Prévisualise un artefact tabulaire (DataFrame).
        GET /api/artefacts/{hash}/preview/?limit=50
        """
        limit = int(request.query_params.get('limit', 50))
        try:
            df = artefact_service.get_dataframe_preview(hash, max_rows=limit)
            if df is None:
                return Response(
                    {"error": "L'artefact n'est pas un DataFrame"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 🔧 Nettoyage : remplacer NaN/NaT/inf par None
            df = df.replace({float("inf"): None, float("-inf"): None})
            df = df.where(pd.notnull(df), None)

            data = {
                "columns": list(df.columns),
                "rows": df.to_dict(orient="records"),
                "count": len(df),
            }

            # 🔧 JSON propre + UTF-8 + accents préservés
            return JsonResponse(
                data,
                safe=False,
                json_dumps_params={"ensure_ascii": False},
                content_type="application/json; charset=utf-8",
            )

        except Exception as e:
            logger.error(f"Erreur preview artefact {hash}: {e}", exc_info=True)
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=['get'])
    def export(self, request, hash=None):
        """
        Exporte un artefact tabulaire (DataFrame) via DRF renderers.
        Exemple :
          - /api/artefacts/{hash}/export/?format=csv
          - /api/artefacts/{hash}/export/?format=xlsx
        """
        fmt = request.query_params.get('format', 'csv').lower()
        if fmt not in ['csv', 'xlsx', 'json']:
            return Response(
                {"error": f"Format non supporté : {fmt}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            df = artefact_service.get_dataframe_preview(hash, max_rows=None)
            if df is None:
                return Response(
                    {"error": "L'artefact n'est pas un DataFrame"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Nettoyage du DataFrame
            df = df.replace({float("inf"): None, float("-inf"): None})
            df = df.where(pd.notnull(df), None)
            data = df.to_dict(orient="records")

            # Définir un nom de fichier pour le renderer
            self.export_filename = f"artefact_{hash[:8]}.{fmt}"

            return Response(data)

        except Exception as e:
            logger.error(f"Erreur export artefact {hash}: {e}", exc_info=True)
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
