# apps/executions/models.py
"""
Modèles pour l'exécution asynchrone des pipelines.

Architecture :
- PipelineRun : instanciation d'un pipeline avec inputs spécifiques
- StepRun : exécution d'un node individuel
- ExecutionLog : logs d'exécution (optionnel, peut utiliser système externe)
"""
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class PipelineRun(models.Model):
    """
    Représente une exécution d'un pipeline.
    
    Workflow :
    1. Création avec status=PENDING
    2. Création des StepRuns
    3. Lancement asynchrone (Celery)
    4. Mise à jour status au fur et à mesure
    """
    
    STATUS_CHOICES = [
        ('PENDING', 'En attente'),
        ('RUNNING', 'En cours'),
        ('SUCCESS', 'Terminé avec succès'),
        ('FAILED', 'Échec'),
        ('CANCELLED', 'Annulé'),
    ]
    
    # Identification
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    # Référence au pipeline
    pipeline = models.ForeignKey(
        'pipelines.Pipeline',
        on_delete=models.CASCADE,
        related_name='runs',
        help_text="Pipeline exécuté"
    )

    # Description du run
    description = models.TextField(
        default=None,
        blank=True,
        null=True
    )
    
    # Initiateur
    initiator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='pipeline_runs',
        help_text="Utilisateur ayant lancé l'exécution"
    )
    
    # Statut
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING',
        db_index=True
    )
    
    # Inputs fournis par l'utilisateur
    input_manifest = models.JSONField(
        default=dict,
        help_text="Mapping des inputs : {node_id: {param: value/artefact_hash}}"
    )
    
    # Metadata d'exécution
    execution_mode = models.CharField(
        max_length=20,
        choices=[
            ('sync', 'Synchrone'),
            ('async', 'Asynchrone (Celery)'),
        ],
        default='async'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    
    # Résultats
    output_artefacts = models.JSONField(
        default=dict,
        help_text="Mapping {node_id: artefact_hash}"
    )
    
    # Logs (optionnel, peut pointer vers système externe)
    logs = models.TextField(
        blank=True,
        help_text="Logs d'exécution consolidés"
    )
    
    error_message = models.TextField(
        blank=True,
        help_text="Message d'erreur si échec"
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Exécution Pipeline'
        verbose_name_plural = 'Exécutions Pipeline'
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['pipeline', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['initiator', '-created_at']),
        ]
    
    def __str__(self):
        return f"Run {self.id} - {self.pipeline.name} ({self.status})"
    
    @property
    def duration(self) -> float:
        """Retourne la durée d'exécution en secondes."""
        if self.started_at and self.finished_at:
            delta = self.finished_at - self.started_at
            return delta.total_seconds()
        return 0.0
    
    def mark_running(self):
        """Marque le run comme démarré."""
        self.status = 'RUNNING'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at'])
    
    def mark_success(self):
        """Marque le run comme terminé avec succès."""
        self.status = 'SUCCESS'
        self.finished_at = timezone.now()
        self.save(update_fields=['status', 'finished_at'])
    
    def mark_failed(self, error_message: str):
        """Marque le run comme échoué."""
        self.status = 'FAILED'
        self.finished_at = timezone.now()
        self.error_message = error_message
        self.save(update_fields=['status', 'finished_at', 'error_message'])
    
    def mark_cancelled(self):
        """Marque le run comme annulé."""
        self.status = 'CANCELLED'
        self.finished_at = timezone.now()
        self.save(update_fields=['status', 'finished_at'])

    @property
    def last_step(self):
        """Retourne la dernière étape du pipeline (celle marquée is_last=True)."""
        return self.step_runs.filter(is_last=True).first()

    @property
    def last_artefact_hash(self):
        """Retourne l'artefact associé à la dernière étape, s'il existe."""
        last = self.last_step
        return last.artefact.hash if last else None


class StepRun(models.Model):
    """
    Représente l'exécution d'un node individuel dans un pipeline.
    
    Un StepRun :
    - Exécute une feature dans une sandbox
    - Produit un artefact
    - Peut être retryé en cas d'échec
    """
    
    STATUS_CHOICES = [
        ('PENDING', 'En attente'),
        ('RUNNING', 'En cours'),
        ('SUCCESS', 'Terminé'),
        ('FAILED', 'Échec'),
        ('SKIPPED', 'Ignoré'),
    ]
    
    # Identification
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    # Référence au run parent
    pipeline_run = models.ForeignKey(
        PipelineRun,
        on_delete=models.CASCADE,
        related_name='step_runs',
        help_text="Run parent"
    )
    
    # Référence au node du pipeline
    node_id = models.CharField(
        max_length=255,
        help_text="ID du node dans le graphe du pipeline"
    )
    
    feature_name = models.CharField(
        max_length=255,
        help_text="Nom de la feature exécutée"
    )
    
    feature_hash = models.CharField(
        max_length=64,
        help_text="Hash de la feature (pour traçabilité)"
    )
    
    # Statut
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING',
        db_index=True
    )
    
    # Inputs/Outputs
    inputs = models.JSONField(
        default=dict,
        help_text="Inputs fournis à la feature : {param: artefact_hash ou valeur}"
    )
    
    artefact = models.ForeignKey(
        'artefacts.ArtefactMeta',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='step_runs',
        help_text="Artefact produit par cette étape"
    )
    
    # Retry
    attempts = models.IntegerField(
        default=0,
        help_text="Nombre de tentatives d'exécution"
    )
    
    max_attempts = models.IntegerField(
        default=3,
        help_text="Nombre maximum de tentatives"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    
    # Erreur
    error = models.TextField(
        blank=True,
        help_text="Stacktrace en cas d'erreur"
    )
    
    # Logs (optionnel)
    stdout = models.TextField(blank=True)
    stderr = models.TextField(blank=True)

    # Identifie si c'est la last step
    is_last = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['created_at']
        verbose_name = 'Étape d\'exécution'
        verbose_name_plural = 'Étapes d\'exécution'
        unique_together = ('pipeline_run', 'node_id')
        indexes = [
            models.Index(fields=['pipeline_run', 'status']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"Step {self.node_id} - {self.feature_name} ({self.status})"
    
    @property
    def duration(self) -> float:
        """Retourne la durée d'exécution en secondes."""
        if self.started_at and self.finished_at:
            delta = self.finished_at - self.started_at
            return delta.total_seconds()
        return 0.0
    
    @property
    def can_retry(self) -> bool:
        """Vérifie si un retry est possible."""
        return self.attempts < self.max_attempts and self.status == 'FAILED'
    
    def mark_running(self):
        """Marque le step comme démarré."""
        self.status = 'RUNNING'
        self.started_at = timezone.now()
        self.attempts += 1
        self.save(update_fields=['status', 'started_at', 'attempts'])
    
    def mark_success(self, artefact_hash: str):
        """Marque le step comme terminé."""
        from artefacts.models import ArtefactMeta
        
        self.status = 'SUCCESS'
        self.finished_at = timezone.now()
        
        # Lien vers l'artefact
        try:
            self.artefact = ArtefactMeta.objects.get(hash=artefact_hash)
        except ArtefactMeta.DoesNotExist:
            pass
        
        self.save(update_fields=['status', 'finished_at', 'artefact'])
    
    def mark_failed(self, error_message: str, stdout: str = '', stderr: str = ''):
        """Marque le step comme échoué."""
        self.status = 'FAILED'
        self.finished_at = timezone.now()
        self.error = error_message
        self.stdout = stdout
        self.stderr = stderr
        self.save(update_fields=['status', 'finished_at', 'error', 'stdout', 'stderr'])
    
    def mark_skipped(self):
        """Marque le step comme ignoré (dépendances non satisfaites)."""
        self.status = 'SKIPPED'
        self.finished_at = timezone.now()
        self.save(update_fields=['status', 'finished_at'])


class ExecutionLog(models.Model):
    """
    Log d'événement d'exécution (optionnel, pour observabilité fine).
    
    Alternative : utiliser un système de logging externe (Sentry, ELK, etc.)
    """
    
    LEVEL_CHOICES = [
        ('DEBUG', 'Debug'),
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
    ]
    
    pipeline_run = models.ForeignKey(
        PipelineRun,
        on_delete=models.CASCADE,
        related_name='execution_logs',
        null=True,
        blank=True
    )
    
    step_run = models.ForeignKey(
        StepRun,
        on_delete=models.CASCADE,
        related_name='execution_logs',
        null=True,
        blank=True
    )
    
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='INFO')
    message = models.TextField()
    metadata = models.JSONField(default=dict)
    
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['pipeline_run', 'timestamp']),
            models.Index(fields=['step_run', 'timestamp']),
            models.Index(fields=['level']),
        ]
    
    def __str__(self):
        return f"[{self.level}] {self.message[:50]}"