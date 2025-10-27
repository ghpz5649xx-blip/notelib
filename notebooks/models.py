from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from wiki.models import Article


class NotebookMeta(models.Model):
    """Métadonnées d'un notebook uploadé"""
    
    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('processing', 'En cours de traitement'),
        ('success', 'Succès'),
        ('error', 'Erreur'),
    ]
    
    # Identification
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to='notebooks/%Y/%m/%d/')
    hash = models.CharField(max_length=128, unique=True)
    
    # Métadonnées
    size = models.BigIntegerField()
    cell_count = models.IntegerField(default=0)
    feature_count = models.IntegerField(default=0)
    
    # Statut
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True, null=True)
    
    # Relations
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    wiki_article = models.ForeignKey(Article, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Timestamps
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Notebook'
        verbose_name_plural = 'Notebooks'
    
    def __str__(self):
        return f"{self.name} ({self.status})"


class NotebookExecution(models.Model):
    """Historique d'exécution d'un notebook"""
    
    notebook = models.ForeignKey(NotebookMeta, on_delete=models.CASCADE, related_name='executions')
    sandbox_mode = models.CharField(max_length=20, default='temp')
    
    # Résultats
    features_imported = models.IntegerField(default=0)
    features_existing = models.IntegerField(default=0)
    errors_count = models.IntegerField(default=0)
    execution_log = models.JSONField(default=dict)
    
    # Timing
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration = models.FloatField(null=True, blank=True)  # en secondes
    
    class Meta:
        ordering = ['-started_at']
    
    def __str__(self):
        return f"Execution {self.id} - {self.notebook.name}"


class NotebookFeature(models.Model):
    """Lien entre un notebook et les features qu'il produit"""
    
    notebook = models.ForeignKey(NotebookMeta, on_delete=models.CASCADE, related_name='features')
    feature = models.ForeignKey('server.FeatureMeta', on_delete=models.CASCADE)
    cell_index = models.IntegerField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('notebook', 'feature')
        ordering = ['cell_index']
    
    def __str__(self):
        return f"{self.notebook.name} → {self.feature.name}"