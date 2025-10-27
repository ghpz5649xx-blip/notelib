from django.db import models
from django.utils import timezone

class FeatureMeta(models.Model):
    name = models.CharField(max_length=255)
    hash = models.CharField(max_length=128)
    inputs = models.JSONField(default=list)
    outputs = models.JSONField(default=list) 
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("name", "hash")

    def __str__(self):
        return f"{self.name} - {self.hash} @ {self.created_at}"

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
