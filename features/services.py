# apps/features/services.py
import logging
from typing import Dict, Any, Optional, Tuple
from django.db import transaction
from django.utils import timezone

from .models import FeatureMeta, FeatureVersion
from .storage import FeatureStorage
from notelib_core.registry import FeatureRegistry

logger = logging.getLogger("notelib")

_registry = FeatureRegistry()


class FeatureService:
    """
    Service orchestrant la logique métier des features.
    
    Responsabilités :
    - Import et enregistrement de nouvelles features
    - Chargement des features en mémoire
    - Gestion du versioning
    - Coordination entre BDD, FS et Registry runtime
    """
    
    def __init__(self):
        self.storage = FeatureStorage()
        self.registry = _registry
    
    def import_feature(self, feature_data: Dict[str, Any]) -> Tuple[FeatureMeta, bool]:
        """
        Importe une feature depuis un notebook.
        
        Workflow:
        1. Vérifie si le hash existe déjà (évite les doublons)
        2. Sauvegarde le binaire sur FS si nouveau
        3. Crée l'entrée en BDD
        4. Met à jour le versioning si c'est une nouvelle version
        
        Args:
            feature_data: Dictionnaire contenant:
                - name: str
                - hash: str
                - code: str
                - inputs: list
                - outputs: list
                - obj: object (fonction/classe Python)
                - defined_in: str (optionnel)
        
        Returns:
            Tuple (Feature, created: bool)
            - Feature: Instance du modèle
            - created: True si nouvelle feature, False si existante
        
        Raises:
            ValueError: Si des champs requis manquent
        """
        # Validation
        required_fields = ['name', 'hash', 'code', 'obj']
        missing = [f for f in required_fields if f not in feature_data]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")
        
        name = feature_data['name']
        hash_value = feature_data['hash']
        code = feature_data['code']
        obj = feature_data['obj']
        
        # Vérification si déjà existant
        try:
            existing = FeatureMeta.objects.get(hash=hash_value)
            logger.info(f"ℹ️  Feature already exists: {name} ({hash_value[:8]})")
            return existing, False
        except FeatureMeta.DoesNotExist:
            pass
        
        # Sauvegarde du binaire sur FS
        if not self.storage.exists(hash_value):
            relative_path, binary_size = self.storage.save(obj, hash_value)
        else:
            relative_path = self.storage._get_relative_path(hash_value)
            binary_size = self.storage.get_size(hash_value) or 0
            logger.info(f"ℹ️  Binary already exists: {relative_path}")
        
        # Création de la feature en BDD (transaction atomique)
        with transaction.atomic():
            feature, created = FeatureMeta.objects.get_or_create(
                name=name,
                hash=hash_value,
                inputs=feature_data.get('inputs', []),
                outputs=feature_data.get('outputs', []),
            )
            
            # Gestion du versioning
            self._create_version(feature)
            
            logger.info(f"✅ Feature created: {name} ({hash_value[:8]})")
        
        # Enregistrement de la feature dans le registre si non présente
        self.load_feature(hash_value=hash_value)
        
        return feature, created
    
    def _create_version(self, feature: FeatureMeta):
        """
        Crée une entrée de version pour une feature.
        
        Si c'est une nouvelle version d'une feature existante (même nom),
        incrémente le numéro de version.
        
        Args:
            feature: Instance de Feature
        """
        # Recherche des versions précédentes du même nom
        previous_features = FeatureMeta.objects.filter(
            name=feature.name
        ).exclude(
            id=feature.id
        ).order_by('-created_at')
        
        if previous_features.exists():
            latest = previous_features.first()
            latest_version = FeatureVersion.objects.filter(
                feature__name=feature.name
            ).order_by('-version_number').first()
            
            version_number = (latest_version.version_number + 1) if latest_version else 2
            previous_hash = latest.hash
        else:
            version_number = 1
            previous_hash = None
        
        FeatureVersion.objects.create(
            feature=feature,
            version_number=version_number,
            previous_hash=previous_hash,
        )
        
        logger.debug(f"📋 Version created: {feature.name} v{version_number}")
    
    def list_hashes(self) -> list:
        """
        Liste l'ensemble des features mises en cache dans le registre

        Returns:
            hash list
        """

        return self.registry.list_hashes()
    
    
    def load_feature(self, hash_value: str) -> object:
        """
        Charge une feature en mémoire.
        
        Workflow:
        1. Vérifie si déjà en mémoire (registry)
        2. Sinon, charge depuis FS
        3. Met en cache dans le registry
        4. Met à jour les métadonnées BDD
        
        Args:
            hash_value: Hash SHA-256 de la feature
        
        Returns:
            Objet Python (fonction ou classe)
        
        Raises:
            Feature.DoesNotExist: Si la feature n'existe pas en BDD
            FileNotFoundError: Si le binaire n'existe pas sur FS
        """
        # Vérification en registry
        if self.registry.is_loaded(hash_value):
            logger.info(f"✅ Feature retrieved from registry: {hash_value[:8]}")
            return self.registry.get(hash_value).obj
        
        # Chargement depuis BDD
        feature = FeatureMeta.objects.get(hash=hash_value)
        
        # Chargement depuis FS
        obj = self.storage.load(hash_value)
        
        # Mise en cache dans le registry
        self.registry.register(obj, hash_value=feature.hash)

        feature.mark_as_loaded()
        
        logger.info(f"✅ Feature loaded in registry: {feature.name} ({hash_value[:8]})")
        
        return obj
    
    def unload_feature(self, hash_value: str):
        """
        Décharge une feature de la mémoire.
        
        Args:
            hash_value: Hash SHA-256 de la feature
        """

        if self.registry.is_loaded(hash_value):
            self.registry.unregister(hash_value)
            
            try:
                feature = FeatureMeta.objects.get(hash=hash_value)
                feature.mark_as_unloaded()
                logger.info(f"🗑️  Feature unloaded: {feature.name} ({hash_value[:8]})")
            except FeatureMeta.DoesNotExist:
                pass
    
    def get_feature_by_name(self, name: str, version: Optional[int] = None) -> Optional[FeatureMeta]:
        """
        Récupère une feature par son nom.
        
        Args:
            name: Nom de la feature
            version: Numéro de version (optionnel, prend la plus récente si None)
        
        Returns:
            Instance de Feature ou None si introuvable
        """
        queryset = FeatureMeta.objects.filter(name=name)
        
        if version is not None:
            # Récupération d'une version spécifique
            version_obj = FeatureVersion.objects.filter(
                feature__name=name,
                version_number=version
            ).select_related('feature').first()
            
            return version_obj.feature if version_obj else None
        else:
            # Version la plus récente
            return queryset.order_by('-created_at').first()
    
    def list_features(self, loaded_only: bool = False) -> list:
        """
        Liste toutes les features.
        
        Args:
            loaded_only: Si True, ne retourne que les features chargées en mémoire
        
        Returns:
            Liste de Features
        """
        queryset = FeatureMeta.objects.all()
        
        if loaded_only:
            queryset = queryset.filter(is_loaded=True)
        
        return list(queryset)
    
    def cleanup_all(self):
        """
        Nettoie le registre et les fichiers orphelins.
        """
        for hash in self.registry.list_hashes():
            self.unload_feature(hash_value=hash)
        orphans_count = self.storage.cleanup_orphans()
        logger.info(f"🧹 Cleanup completed: {orphans_count} orphan files deleted")

    def cleanup_orphans(self):
        """
        Nettoie le registre et le FS de features orphelines (sans entrée en BDD)

        Returns:
            Nombre de features unregister
        """
        
        deleted_count = 0
        db_hashes = set(FeatureMeta.objects.values_list('hash', flat=True))
        registry_hashes = self.list_hashes()

        logger.info(f" Looking for orphans feature in registry")
        logger.info(f" registry hashes {registry_hashes}")
        logger.info(f" db hashed {db_hashes}")

        for hash_value in registry_hashes:
            if hash_value not in db_hashes:
                self.registry.unregister(hash_value)
                logger.info(f"🗑️  Orphan binary deleted: {hash_value}")
                deleted_count += 1
        
        self.storage.cleanup_orphans()

        return deleted_count



feature_service = FeatureService()