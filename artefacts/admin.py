# apps/artefacts/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import ArtefactMeta, ArtefactAccessLog


@admin.register(ArtefactMeta)
class ArtefactMetaAdmin(admin.ModelAdmin):
    list_display = [
        'hash_short',
        'feature_link',
        'size_display',
        'compression_display',
        'ref_count',
        'can_delete_badge',
        'created_at',
    ]
    list_filter = ['created_at', 'mime']
    search_fields = ['hash', 'feature__name']
    readonly_fields = [
        'id',
        'hash',
        'size',
        'size_uncompressed',
        'storage_path',
        'ref_count',
        'created_at',
        'last_accessed_at',
        'compression_ratio',
    ]
    
    fieldsets = (
        ('Identification', {
            'fields': ('id', 'hash', 'feature')
        }),
        ('Stockage', {
            'fields': ('storage_path', 'size', 'size_uncompressed', 'compression_ratio', 'mime')
        }),
        ('Métadonnées', {
            'fields': ('meta',)
        }),
        ('Gestion', {
            'fields': ('ref_count', 'created_at', 'last_accessed_at')
        }),
    )
    
    def hash_short(self, obj):
        return f"{obj.hash[:12]}..."
    hash_short.short_description = 'Hash'
    
    def feature_link(self, obj):
        if obj.feature:
            return format_html(
                '<a href="{}">{}</a>',
                reverse('admin:features_featuremeta_change', args=[obj.feature.pk]),
                obj.feature.name
            )
        return '-'
    feature_link.short_description = 'Feature'
    
    def size_display(self, obj):
        size_mb = obj.size / (1024 * 1024)
        return f"{size_mb:.2f} MB"
    size_display.short_description = 'Taille'
    
    def compression_display(self, obj):
        ratio = obj.compression_ratio
        if ratio:
            return f"{ratio:.1%}"
        return '-'
    compression_display.short_description = 'Compression'
    
    def can_delete_badge(self, obj):
        if obj.can_delete():
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: red;">✗ (refs: {})</span>', obj.ref_count)
    can_delete_badge.short_description = 'Supprimable'


@admin.register(ArtefactAccessLog)
class ArtefactAccessLogAdmin(admin.ModelAdmin):
    list_display = [
        'artefact_hash',
        'accessed_by',
        'access_type',
        'accessed_at',
        'ip_address',
    ]
    list_filter = ['access_type', 'accessed_at']
    search_fields = ['artefact__hash', 'accessed_by__username']
    readonly_fields = ['artefact', 'accessed_by', 'access_type', 'accessed_at', 'ip_address', 'user_agent']
    
    def artefact_hash(self, obj):
        return f"{obj.artefact.hash[:12]}..."
    artefact_hash.short_description = 'Artefact'