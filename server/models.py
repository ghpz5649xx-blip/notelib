from django.db import models
from django.utils import timezone

class FeatureMeta(models.Model):
    name = models.CharField(max_length=255)
    hash = models.CharField(max_length=128)
    inputs = models.JSONField(default=list)
    outputs = models.JSONField(default=list) 
    created_at = models.DateTimeField(auto_now_add=True)

    # 🆕 Ajout du tracking de l'état en mémoire
    is_loaded = models.BooleanField(default=False)
    loaded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("name", "hash")

    def __str__(self):
        return f"{self.name} - {self.hash} @ {self.created_at}"
    
    # 🆕 Méthodes pour gérer l'état
    def mark_as_loaded(self):
        """Marque la feature comme chargée en mémoire"""
        from django.utils import timezone
        self.is_loaded = True
        self.loaded_at = timezone.now()
        self.save(update_fields=['is_loaded', 'loaded_at'])
    
    def mark_as_unloaded(self):
        """Marque la feature comme déchargée de la mémoire"""
        self.is_loaded = False
        self.save(update_fields=['is_loaded'])

class FeatureVersion(models.Model):
    feature = models.ForeignKey(FeatureMeta,on_delete=models.CASCADE)
    version_number = models.IntegerField(default=1)
    previous_hash = models.CharField(max_length=128, null=True, blank=True)

class ArtifactMeta(models.Model):
    type = models.CharField(max_length=255)
    feature = models.ForeignKey(FeatureMeta, null=True, on_delete=models.SET_NULL)
    path = models.TextField()
    hash = models.CharField(max_length=128)
    size = models.BigIntegerField()
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

class ExecutionLog(models.Model):
    feature = models.ForeignKey(FeatureMeta, on_delete=models.SET_NULL, null=True)
    inputs = models.JSONField(default=dict)   # {artifact_type: artifact_id}
    outputs = models.JSONField(default=dict)  # {artifact_type: artifact_id}
    status = models.CharField(max_length=32)
    duration = models.FloatField(null=True)
    log_path = models.TextField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class FeatureImportLog(models.Model):
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=[("ok","ok"),("ko","ko")])
    error_msg = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.name} - {self.status} @ {self.timestamp}"
