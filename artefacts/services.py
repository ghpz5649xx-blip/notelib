# apps/artefacts/services.py
"""
Service orchestrant la logique métier des artefacts.

Responsabilités :
- Création et enregistrement des artefacts
- Gestion du cycle de vie (refs, cleanup)
- Coordination entre BDD, FS et cache
"""
import logging
from typing import Dict, Any, Optional, Tuple, BinaryIO
from django.db import transaction
from django.conf import settings

from .models import ArtefactMeta, ArtefactAccessLog
from .storage import artefact_storage

logger = logging.getLogger("notelib")


class ArtefactService:
    """
    Service de gestion des artefacts.
    
    Orchestration de bout en bout :
    - Création : sérialisation + compression + stockage + métadonnées BDD
    - Lecture : chargement depuis FS + désérialisation
    - Suppression : vérification refs + cleanup FS + BDD
    """
    
    def __init__(self):
        self.storage = artefact_storage
        self.max_size = getattr(
            settings,
            'NOTELIB_ARTIFACT_MAX_BYTES',
            100 * 1024 * 1024  # 100 MB par défaut
        )
    
    def create_artefact(
        self,
        obj: object,
        feature_hash: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None
    ) -> ArtefactMeta:
        """
        Crée un artefact depuis un objet Python.
        
        Workflow :
        1. Sérialise + compresse + calcule hash
        2. Vérifie si déjà existant (déduplication)
        3. Sauvegarde sur FS
        4. Crée l'entrée BDD
        
        Args:
            obj: Objet Python à persister
            feature_hash: Hash de la feature productrice (optionnel)
            meta: Métadonnées additionnelles
        
        Returns:
            Instance ArtefactMeta créée ou existante
        
        Raises:
            ValueError: Si taille > max autorisée
        """
        # Sérialisation + compression
        relative_path, size_compressed, size_raw, hash_value = self.storage.save(obj)
        
        # Vérification de la taille
        if size_compressed > self.max_size:
            # Nettoyage du fichier créé
            self.storage.delete(hash_value)
            raise ValueError(
                f"Artefact too large: {size_compressed} bytes "
                f"(max: {self.max_size} bytes)"
            )
        
        # Recherche si artefact déjà existant (déduplication)
        try:
            existing = ArtefactMeta.objects.get(hash=hash_value)
            logger.info(f"ℹ️  Artefact deduplicated: {hash_value[:8]}")
            return existing
        except ArtefactMeta.DoesNotExist:
            pass
        
        # Récupération de la feature si fournie
        feature = None
        if feature_hash:
            from features.models import FeatureMeta
            try:
                feature = FeatureMeta.objects.get(hash=feature_hash)
            except FeatureMeta.DoesNotExist:
                logger.warning(f"Feature not found: {feature_hash}")
        
        # Préparation des métadonnées
        meta_data = meta or {}
        meta_data.update({
            'schema_version': '1.0',  # Versioning du format
            'compression': 'zstd',
            'serialization': 'cloudpickle',
        })
        
        # Création en BDD (transaction atomique)
        with transaction.atomic():
            artefact = ArtefactMeta.objects.create(
                hash=hash_value,
                feature=feature,
                size=size_compressed,
                size_uncompressed=size_raw,
                storage_path=relative_path,
                meta=meta_data,
            )
            
            logger.info(
                f"✅ Artefact created: {hash_value[:8]} "
                f"({size_compressed} bytes, ratio: {size_compressed/size_raw:.2%})"
            )
        
        return artefact
    
    def get_artefact(self, hash_value: str) -> Optional[ArtefactMeta]:
        """
        Récupère les métadonnées d'un artefact.
        
        Args:
            hash_value: Hash SHA-256
        
        Returns:
            Instance ArtefactMeta ou None
        """
        try:
            artefact = ArtefactMeta.objects.get(hash=hash_value)
            artefact.save(update_fields=['last_accessed_at'])  # MAJ last_accessed
            return artefact
        except ArtefactMeta.DoesNotExist:
            return None
    
    def load_artefact(
        self,
        hash_value: str,
        log_access: bool = True,
        user=None
    ) -> object:
        """
        Charge et désérialise un artefact.
        
        Args:
            hash_value: Hash SHA-256
            log_access: Si True, enregistre l'accès dans ArtefactAccessLog
            user: Utilisateur effectuant l'accès (optionnel)
        
        Returns:
            Objet Python désérialisé
        
        Raises:
            ArtefactMeta.DoesNotExist: Si artefact inexistant
            FileNotFoundError: Si fichier FS manquant
        """
        # Vérification en BDD
        artefact = ArtefactMeta.objects.get(hash=hash_value)
        
        # Chargement depuis FS
        obj = self.storage.load(hash_value)
        
        # MAJ last_accessed
        artefact.save(update_fields=['last_accessed_at'])
        
        # Log d'accès (optionnel)
        if log_access:
            ArtefactAccessLog.objects.create(
                artefact=artefact,
                accessed_by=user,
                access_type='download'
            )
        
        logger.debug(f"✅ Artefact loaded: {hash_value[:8]}")
        
        return obj
    
    def stream_artefact(
        self,
        hash_value: str,
        log_access: bool = True,
        user=None
    ) -> BinaryIO:
        """
        Ouvre un artefact en mode streaming.
        
        Args:
            hash_value: Hash SHA-256
            log_access: Si True, enregistre l'accès
            user: Utilisateur effectuant l'accès
        
        Returns:
            File object binaire
        
        Raises:
            ArtefactMeta.DoesNotExist: Si artefact inexistant
        """
        # Vérification en BDD
        artefact = ArtefactMeta.objects.get(hash=hash_value)
        
        # MAJ last_accessed
        artefact.save(update_fields=['last_accessed_at'])
        
        # Log d'accès
        if log_access:
            ArtefactAccessLog.objects.create(
                artefact=artefact,
                accessed_by=user,
                access_type='stream'
            )
        
        # Ouverture du stream
        return self.storage.stream(hash_value)
    
    def delete_artefact(self, hash_value: str, force: bool = False) -> bool:
        """
        Supprime un artefact.
        
        Args:
            hash_value: Hash SHA-256
            force: Si True, ignore le ref_count (danger !)
        
        Returns:
            True si supprimé, False si impossible
        
        Raises:
            ValueError: Si ref_count > 0 et force=False
        """
        try:
            artefact = ArtefactMeta.objects.get(hash=hash_value)
        except ArtefactMeta.DoesNotExist:
            logger.warning(f"Artefact not found for deletion: {hash_value}")
            return False
        
        # Vérification des références
        if not force and not artefact.can_delete():
            raise ValueError(
                f"Cannot delete artefact {hash_value}: "
                f"ref_count={artefact.ref_count} (use force=True to override)"
            )
        
        # Suppression FS
        self.storage.delete(hash_value)
        
        # Suppression BDD
        artefact.delete()
        
        logger.info(f"🗑️  Artefact deleted: {hash_value[:8]}")
        
        return True
    
    def cleanup_orphans(self) -> Tuple[int, int]:
        """
        Nettoie les artefacts orphelins (FS sans BDD et BDD sans FS).
        
        Returns:
            Tuple (fs_orphans, db_orphans)
        """
        # Récupération de tous les hash en BDD
        db_hashes = set(
            ArtefactMeta.objects.values_list('hash', flat=True)
        )
        
        # Nettoyage des fichiers orphelins (FS sans BDD)
        fs_orphans = self.storage.cleanup_orphans(db_hashes)
        
        # Nettoyage des entrées BDD sans fichier
        db_orphans = 0
        for artefact in ArtefactMeta.objects.all():
            if not self.storage.exists(artefact.hash):
                logger.warning(
                    f"BDD entry without file: {artefact.hash[:8]}, deleting..."
                )
                artefact.delete()
                db_orphans += 1
        
        logger.info(
            f"🧹 Cleanup completed: {fs_orphans} FS orphans, {db_orphans} DB orphans"
        )
        
        return fs_orphans, db_orphans
    
    def cleanup_old_artefacts(self, days: int = 30) -> int:
        """
        Supprime les artefacts non référencés et anciens.
        
        Args:
            days: Âge minimum en jours
        
        Returns:
            Nombre d'artefacts supprimés
        """
        from django.utils import timezone
        from datetime import timedelta
        
        cutoff_date = timezone.now() - timedelta(days=days)
        
        old_artefacts = ArtefactMeta.objects.filter(
            ref_count=0,
            last_accessed_at__lt=cutoff_date
        )
        
        deleted_count = 0
        for artefact in old_artefacts:
            try:
                self.delete_artefact(artefact.hash)
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete old artefact {artefact.hash}: {e}")
        
        logger.info(f"🧹 Deleted {deleted_count} old artefacts (>{days} days)")
        
        return deleted_count
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Retourne des statistiques sur les artefacts.
        
        Returns:
            Dictionnaire de statistiques
        """
        from django.db.models import Sum, Avg, Count
        
        stats = ArtefactMeta.objects.aggregate(
            total_count=Count('id'),
            total_size=Sum('size'),
            total_size_uncompressed=Sum('size_uncompressed'),
            avg_compression_ratio=Avg('size') / Avg('size_uncompressed'),
        )
        
        stats['orphans'] = ArtefactMeta.objects.filter(ref_count=0).count()
        stats['referenced'] = ArtefactMeta.objects.filter(ref_count__gt=0).count()
        
        return stats


# Instance globale
artefact_service = ArtefactService()