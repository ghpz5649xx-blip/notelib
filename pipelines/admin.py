
# ============================================================
# apps/pipelines/admin.py
# ============================================================
from django.contrib import admin
from django.utils.html import format_html
from .models import Pipeline, PipelineTemplate


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'owner',
        'node_count_display',
        'edge_count_display',
        'is_valid_badge',
        'is_active',
        'version',
        'updated_at',
    ]
    list_filter = ['is_active', 'is_valid', 'created_at']
    search_fields = ['name', 'description', 'owner__username']
    readonly_fields = [
        'id',
        'is_valid',
        'validation_errors',
        'version',
        'created_at',
        'updated_at',
    ]
    
    fieldsets = (
        ('Informations', {
            'fields': ('id', 'name', 'description', 'owner')
        }),
        ('Graphe', {
            'fields': ('graph',)
        }),
        ('Validation', {
            'fields': ('is_valid', 'validation_errors')
        }),
        ('Statut', {
            'fields': ('is_active', 'version', 'tags')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def node_count_display(self, obj):
        return obj.get_node_count()
    node_count_display.short_description = 'Nodes'
    
    def edge_count_display(self, obj):
        return obj.get_edge_count()
    edge_count_display.short_description = 'Edges'
    
    def is_valid_badge(self, obj):
        if obj.is_valid:
            return format_html('<span style="color: green;">✓</span>')
        return format_html(
            '<span style="color: red;" title="{}">✗</span>',
            ', '.join(obj.validation_errors[:3])
        )
    is_valid_badge.short_description = 'Valid'


@admin.register(PipelineTemplate)
class PipelineTemplateAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'is_public',
        'created_by',
        'usage_count',
        'created_at',
    ]
    list_filter = ['is_public', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'usage_count']