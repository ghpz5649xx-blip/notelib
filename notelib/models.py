from django.db import models

class FeatureMeta(models.Model):
    name = models.CharField(max_length=255)
    version = models.CharField(max_length=64)
    input_types = models.JSONField(default=list)
    output_types = models.JSONField(default=list)
    notebook_path = models.TextField()
    code_hash = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("name", "version")

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