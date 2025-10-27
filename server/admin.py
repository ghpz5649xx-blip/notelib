from django.contrib import admin
from server.models import *

admin.site.register(FeatureMeta)
admin.site.register(ArtifactMeta)
admin.site.register(ExecutionLog)
admin.site.register(FeatureImportLog)
admin.site.register(FeatureVersion)