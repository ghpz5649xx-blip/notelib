# apps/artefacts/serializers.py
"""
Serializers DRF pour l'API des artefacts.
"""
from rest_framework import serializers
from .models import ArtefactMeta, ArtefactAccessLog


class ArtefactMetaSerializer(serializers.ModelSerializer):
    """Serializer pour les métadonnées d'artefact."""
    
    feature_name = serializers.CharField(
        source='feature.name',
        read_only=True,
        allow_null=True
    )
    
    compression_ratio = serializers.FloatField(read_only=True)
    
    can_delete = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = ArtefactMeta
        fields = [
            'id',
            'hash',
            'feature',
            'feature_name',
            'size',
            'size_uncompressed',
            'compression_ratio',
            'mime',
            'storage_path',
            'meta',
            'ref_count',
            'can_delete',
            'created_at',
            'last_accessed_at',
        ]
        read_only_fields = [
            'id',
            'hash',
            'size',
            'size_uncompressed',
            'storage_path',
            'ref_count',
            'created_at',
            'last_accessed_at',
        ]


class ArtefactCreateSerializer(serializers.Serializer):
    """
    Serializer pour la création d'artefact côté serveur.
    
    Note: L'objet Python est fourni directement dans la requête,
    le serveur se charge de la sérialisation.
    """
    
    feature_hash = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Hash de la feature productrice"
    )
    
    meta = serializers.JSONField(
        required=False,
        default=dict,
        help_text="Métadonnées additionnelles"
    )
    
    # Note: L'objet Python est passé dans le contexte, pas dans le payload JSON


class ArtefactAccessLogSerializer(serializers.ModelSerializer):
    """Serializer pour les logs d'accès."""
    
    artefact_hash = serializers.CharField(source='artefact.hash', read_only=True)
    user_name = serializers.CharField(source='accessed_by.username', read_only=True)
    
    class Meta:
        model = ArtefactAccessLog
        fields = [
            'id',
            'artefact',
            'artefact_hash',
            'accessed_by',
            'user_name',
            'access_type',
            'accessed_at',
            'ip_address',
            'user_agent',
        ]
        read_only_fields = ['id', 'accessed_at']


class ArtefactStatsSerializer(serializers.Serializer):
    """Serializer pour les statistiques d'artefacts."""
    
    total_count = serializers.IntegerField()
    total_size = serializers.IntegerField()
    total_size_uncompressed = serializers.IntegerField()
    avg_compression_ratio = serializers.FloatField()
    orphans = serializers.IntegerField()
    referenced = serializers.IntegerField()