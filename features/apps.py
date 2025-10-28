from django.apps import AppConfig
from django.core.signals import request_started
import atexit
import threading



class FeaturesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'features'
    _cache_loaded = False

    def ready(self):
        from django.conf import settings
        from django.db.utils import OperationalError
        from django.core.management import commands
        from .services import feature_service
        from .models import FeatureMeta

        # Ne pas exécuter pendant les commandes de management
        import sys
        if len(sys.argv) > 1 and sys.argv[1] not in ("runserver", "gunicorn"):
            return

        def load_features(sender, **kwargs):
            """Chargement du cache au premier vrai accès HTTP"""
            if self._cache_loaded:
                return
            self._cache_loaded = True
            print("🔄 Chargement du cache des features depuis la DB...")

            try:
                for fh in FeatureMeta.objects.all():
                    feature_service.load_feature(fh.hash)
                print("✅ Cache des features initialisé.")
            except OperationalError as e:
                print("⚠️ Impossible de charger les features : base non accessible.", e)

        # On ne le fait qu'une fois, au premier request
        request_started.connect(load_features, dispatch_uid="load_features_once")

        # Gestion de la sauvegarde à la fermeture
        def save_features_on_exit():
            print("💾 Sauvegarde du cache avant arrêt...")
            feature_service.cleanup_all()

        atexit.register(save_features_on_exit)
