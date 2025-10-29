# ============================================================
# apps/pipelines/serializers.py
# ============================================================
from rest_framework import serializers
from .models import Pipeline, PipelineTemplate


class PipelineSerializer(serializers.ModelSerializer):
    """Serializer pour les pipelines."""
    
    node_count = serializers.SerializerMethodField()
    edge_count = serializers.SerializerMethodField()
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    
    class Meta:
        model = Pipeline
        fields = [
            'id',
            'name',
            'description',
            'owner',
            'owner_username',
            'graph',
            'is_active',
            'is_valid',
            'validation_errors',
            'version',
            'tags',
            'node_count',
            'edge_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'is_valid',
            'validation_errors',
            'version',
            'created_at',
            'updated_at',
        ]
    
    def get_node_count(self, obj):
        return obj.get_node_count()
    
    def get_edge_count(self, obj):
        return obj.get_edge_count()


class PipelineCreateSerializer(serializers.ModelSerializer):
    """Serializer pour la création de pipeline."""
    
    class Meta:
        model = Pipeline
        fields = ['name', 'description', 'graph', 'tags']


class PipelineTemplateSerializer(serializers.ModelSerializer):
    """Serializer pour les templates."""
    
    created_by_username = serializers.CharField(
        source='created_by.username',
        read_only=True
    )
    
    class Meta:
        model = PipelineTemplate
        fields = [
            'id',
            'name',
            'description',
            'graph_template',
            'is_public',
            'created_by',
            'created_by_username',
            'created_at',
            'usage_count',
        ]
        read_only_fields = ['id', 'created_at', 'usage_count']