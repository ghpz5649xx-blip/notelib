# ============================================================
# apps/executions/serializers.py
# ============================================================
from rest_framework import serializers
from .models import PipelineRun, StepRun, ExecutionLog


class StepRunSerializer(serializers.ModelSerializer):
    duration = serializers.FloatField(read_only=True)
    can_retry = serializers.BooleanField(read_only=True)
    artefact_hash = serializers.CharField(source='artefact.hash', read_only=True, allow_null=True)
    
    class Meta:
        model = StepRun
        fields = [
            'id', 'node_id', 'feature_name', 'feature_hash',
            'status', 'inputs', 'artefact', 'artefact_hash',
            'attempts', 'max_attempts', 'can_retry',
            'started_at', 'finished_at', 'duration',
            'error', 'stdout', 'stderr','is_last'
        ]
        read_only_fields = ['id', 'started_at', 'finished_at']


class PipelineRunSerializer(serializers.ModelSerializer):
    duration = serializers.FloatField(read_only=True)
    initiator_username = serializers.CharField(source='initiator.username', read_only=True)
    pipeline_name = serializers.CharField(source='pipeline.name', read_only=True)
    step_runs = StepRunSerializer(many=True, read_only=True)
    last_artefact_hash = serializers.CharField(read_only=True)
    
    class Meta:
        model = PipelineRun
        fields = [
            'id', 'pipeline', 'pipeline_name', 'initiator', 'initiator_username',
            'status', 'input_manifest', 'execution_mode', 'output_artefacts',
            'created_at', 'started_at', 'finished_at', 'duration',
            'logs', 'error_message', 'step_runs', 'description', 'last_artefact_hash',
        ]
        read_only_fields = [
            'id', 'status', 'output_artefacts',
            'created_at', 'started_at', 'finished_at',
            'logs', 'error_message',
        ]

class PipelineRunCreateSerializer(serializers.Serializer):
    input_manifest = serializers.JSONField(required=True)
    execution_mode = serializers.ChoiceField(
        choices=['sync', 'async'],
        default='sync'
    )
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
