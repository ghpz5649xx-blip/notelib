# artefacts/models.py
"""
Modèles pour la gestion des artefacts.

Un artefact représente la sortie sérialisée et compressée d'une feature.
Il est identifié par un hash SHA-256 du contenu non compressé pour permettre
la déduplication automatique.
"""
import uuid
from django.db import models
from django.utils import timezone
from django.conf import settings


class ArtefactMeta(models.Model):
    """
    Métadonnées d'un artefact persisté.
    
    Un artefact est créé par l'exécution d'une feature et contient :
    - Le résultat sérialisé (cloudpickle) et compressé (zstd)
    - Un hash SHA-256 pour déduplication
    - Des métadonnées sur le producteur et le contexte d'exécution
    
    Choix techniques :
    - Hash calculé sur le contenu NON compressé pour déduplication exacte
    - Stockage filesystem pour les gros volumes (vs BDD)
    - JSONField pour métadonnées extensibles
    """
    
    # Identification unique
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Identifiant unique UUID"
    )
    
    hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="SHA-256 du contenu non compressé (déduplication)"
    )
    
    # Provenance
    feature = models.ForeignKey(
        'features.FeatureMeta',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='artefacts',
        help_text="Feature ayant produit cet artefact"
    )
    
    # Métadonnées de contenu
    size = models.BigIntegerField(
        help_text="Taille du fichier compressé en octets"
    )
    
    size_uncompressed = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Taille avant compression (optionnel)"
    )
    
    mime = models.CharField(
        max_length=255,
        default='application/octet-stream',
        help_text="Type MIME du contenu"
    )
    
    # Stockage
    storage_path = models.CharField(
        max_length=512,
        help_text="Chemin relatif du fichier .zst sur le filesystem"
    )
    
    # Métadonnées extensibles
    meta = models.JSONField(
        default=dict,
        help_text="Métadonnées additionnelles : inputs, params, versions, etc."
    )
    
    # Gestion du cycle de vie
    ref_count = models.IntegerField(
        default=0,
        help_text="Nombre de références actives (pipelines/runs)"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )
    
    last_accessed_at = models.DateTimeField(
        auto_now=True,
        help_text="Dernière lecture (pour politique de rétention)"
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Artefact'
        verbose_name_plural = 'Artefacts'
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['hash']),
            models.Index(fields=['feature', '-created_at']),
        ]
    
    def __str__(self):
        feature_name = self.feature.name if self.feature else "orphan"
        return f"{feature_name}:{self.hash[:8]}"
    
    def increment_ref(self):
        """Incrémente le compteur de références."""
        self.ref_count = models.F('ref_count') + 1
        self.save(update_fields=['ref_count'])
        self.refresh_from_db(fields=['ref_count'])
    
    def decrement_ref(self):
        """Décrémente le compteur de références."""
        self.ref_count = models.F('ref_count') - 1
        self.save(update_fields=['ref_count'])
        self.refresh_from_db(fields=['ref_count'])
    
    def can_delete(self) -> bool:
        """Vérifie si l'artefact peut être supprimé (ref_count = 0)."""
        return self.ref_count <= 0
    
    @property
    def compression_ratio(self) -> float:
        """Calcule le ratio de compression."""
        if self.size_uncompressed and self.size_uncompressed > 0:
            return self.size / self.size_uncompressed
        return 1.0


class ArtefactAccessLog(models.Model):
    """
    Log des accès aux artefacts (optionnel, pour observabilité).
    
    Permet de tracer qui accède à quoi et quand, utile pour :
    - Audit de sécurité
    - Analyse d'usage
    - Politique de cache/rétention
    """
    
    artefact = models.ForeignKey(
        ArtefactMeta,
        on_delete=models.CASCADE,
        related_name='access_logs'
    )
    
    accessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    access_type = models.CharField(
        max_length=20,
        choices=[
            ('download', 'Téléchargement'),
            ('stream', 'Streaming'),
            ('metadata', 'Lecture métadonnées'),
        ],
        default='download'
    )
    
    accessed_at = models.DateTimeField(auto_now_add=True)
    
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-accessed_at']
        verbose_name = 'Log d\'accès'
        verbose_name_plural = 'Logs d\'accès'
        indexes = [
            models.Index(fields=['-accessed_at']),
            models.Index(fields=['artefact', '-accessed_at']),
        ]