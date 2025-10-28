from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import NotebookMeta, NotebookExecution, NotebookFeature


@admin.register(NotebookMeta)
class NotebookMetaAdmin(admin.ModelAdmin):
    list_display = [
        'name', 
        'status_badge', 
        'feature_count', 
        'uploaded_by', 
        'uploaded_at',
        'actions_column'
    ]
    list_filter = ['status', 'uploaded_at', 'uploaded_by']
    search_fields = ['name', 'hash']
    readonly_fields = [
        'hash', 
        'size', 
        'uploaded_at', 
        'processed_at',
        'feature_count',
        'cell_count'
    ]
    
    fieldsets = (
        ('Identification', {
            'fields': ('name', 'file', 'hash')
        }),
        ('Métadonnées', {
            'fields': ('size', 'cell_count', 'feature_count')
        }),
        ('Statut', {
            'fields': ('status', 'error_message')
        }),
        ('Relations', {
            'fields': ('uploaded_by', 'wiki_article')
        }),
        ('Timestamps', {
            'fields': ('uploaded_at', 'processed_at')
        }),
    )
    
    def status_badge(self, obj):
        colors = {
            'pending': '#6c757d',
            'processing': '#ffc107',
            'success': '#28a745',
            'error': '#dc3545',
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            colors.get(obj.status, '#6c757d'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Statut'
    
    def actions_column(self, obj):
        detail_url = reverse('notebooks:detail', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}">Voir les détails</a>',
            detail_url
        )
    actions_column.short_description = 'Actions'


@admin.register(NotebookExecution)
class NotebookExecutionAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'notebook',
        'sandbox_mode',
        'features_imported',
        'features_existing',
        'errors_count',
        'duration_display',
        'started_at'
    ]
    list_filter = ['sandbox_mode', 'started_at']
    search_fields = ['notebook__name']
    readonly_fields = [
        'notebook',
        'sandbox_mode',
        'features_imported',
        'features_existing',
        'errors_count',
        'execution_log',
        'started_at',
        'completed_at',
        'duration'
    ]
    
    def duration_display(self, obj):
        if obj.duration:
            return f"{obj.duration:.2f}s"
        return "-"
    duration_display.short_description = 'Durée'


@admin.register(NotebookFeature)
class NotebookFeatureAdmin(admin.ModelAdmin):
    list_display = [
        'notebook',
        'feature_name',
        'cell_index',
        'created_at'
    ]
    list_filter = ['created_at']
    search_fields = ['notebook__name', 'feature__name']
    readonly_fields = ['notebook', 'feature', 'cell_index', 'created_at']
    
    def feature_name(self, obj):
        return obj.feature.name
    feature_name.short_description = 'Feature'