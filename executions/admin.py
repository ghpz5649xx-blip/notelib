# ============================================================
# apps/executions/admin.py
# ============================================================
from django.contrib import admin
from django.utils.html import format_html
from .models import PipelineRun, StepRun, ExecutionLog


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = [
        'id_short',
        'pipeline',
        'initiator',
        'status_badge',
        'execution_mode',
        'duration_display',
        'created_at',
    ]
    list_filter = ['status', 'execution_mode', 'created_at']
    search_fields = ['id', 'pipeline__name', 'initiator__username']
    readonly_fields = [
        'id', 'status', 'output_artefacts',
        'created_at', 'started_at', 'finished_at',
        'duration', 'logs', 'error_message',
    ]
    
    def id_short(self, obj):
        return str(obj.id)[:8]
    id_short.short_description = 'ID'
    
    def status_badge(self, obj):
        colors = {
            'PENDING': 'gray',
            'RUNNING': 'blue',
            'SUCCESS': 'green',
            'FAILED': 'red',
            'CANCELLED': 'orange',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 6px; border-radius: 3px;">{}</span>',
            colors.get(obj.status, 'gray'),
            obj.status
        )
    status_badge.short_description = 'Statut'
    
    def duration_display(self, obj):
        d = obj.duration
        if d:
            return f"{d:.1f}s"
        return '-'
    duration_display.short_description = 'Durée'


@admin.register(StepRun)
class StepRunAdmin(admin.ModelAdmin):
    list_display = [
        'id_short', 'pipeline_run', 'node_id',
        'feature_name', 'status_badge',
        'attempts', 'duration_display','is_last',
    ]
    list_filter = ['status', 'attempts']
    search_fields = ['id', 'node_id', 'feature_name']
    readonly_fields = [
        'id', 'pipeline_run', 'node_id', 'feature_name', 'feature_hash',
        'status', 'artefact', 'started_at', 'finished_at',
        'error', 'stdout', 'stderr',
    ]
    
    def id_short(self, obj):
        return str(obj.id)[:8]
    id_short.short_description = 'ID'
    
    def status_badge(self, obj):
        colors = {
            'PENDING': 'gray',
            'RUNNING': 'blue',
            'SUCCESS': 'green',
            'FAILED': 'red',
            'SKIPPED': 'orange',
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 6px;">{}</span>',
            colors.get(obj.status, 'gray'),
            obj.status
        )
    status_badge.short_description = 'Statut'
    
    def duration_display(self, obj):
        d = obj.duration
        if d:
            return f"{d:.1f}s"
        return '-'
    duration_display.short_description = 'Durée'


@admin.register(ExecutionLog)
class ExecutionLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'level', 'message_short', 'pipeline_run', 'step_run']
    list_filter = ['level', 'timestamp']
    search_fields = ['message']
    readonly_fields = ['pipeline_run', 'step_run', 'level', 'message', 'metadata', 'timestamp']
    
    def message_short(self, obj):
        return obj.message[:100]
    message_short.short_description = 'Message'