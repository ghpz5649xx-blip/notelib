# apps/features/storage.py
import os
import hashlib
import cloudpickle
import logging
from pathlib import Path
from typing import Optional, Tuple
from django.conf import settings

logger = logging.getLogger("notelib")


class FeatureStorage:
    """
    Gère le stockage et la récupération des binaires de features sur le filesystem.
    
    Organisation du stockage :
    storage/features/
    ├── by_hash/
    │   ├── e3/
    │   │   └── e3b0c442...b855.pkl
    │   └── a4/
    │       └── a4d55a8d...4e5b.pkl
    └── metadata/
        └── index.json
    """
    
    def __init__(self, base_dir: Optional[str] = None):
        """
        Initialise le gestionnaire de stockage.
        
        Args:
            base_dir: Répertoire racine de stockage. 
                     Si None, utilise settings.FEATURE_STORAGE_DIR
        """
        if base_dir is None:
            base_dir = getattr(settings, 'FEATURE_STORAGE_DIR',
                             os.path.join(settings.BASE_DIR, 'storage', 'features'))
        
        self.base_dir = Path(base_dir)
        self.hash_dir = self.base_dir / "by_hash"
        self.metadata_dir = self.base_dir / "metadata"
        
        # Création des répertoires si nécessaire
        self.hash_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_hash_path(self, hash_value: str) -> Path:
        """
        Génère le chemin de stockage basé sur le hash.
        
        Utilise les 2 premiers caractères du hash comme sous-répertoire
        pour éviter d'avoir trop de fichiers dans un seul dossier.
        
        Args:
            hash_value: Hash SHA-256 de la feature
            
        Returns:
            Chemin complet vers le fichier pickle
        """
        prefix = hash_value[:2]
        subdir = self.hash_dir / prefix
        subdir.mkdir(exist_ok=True)
        return subdir / f"{hash_value}.pkl"
    
    def _get_relative_path(self, hash_value: str) -> str:
        """
        Retourne le chemin relatif pour stockage en BDD.
        
        Args:
            hash_value: Hash SHA-256 de la feature
            
        Returns:
            Chemin relatif : "by_hash/e3/e3b0c442...pkl"
        """
        prefix = hash_value[:2]
        return f"by_hash/{prefix}/{hash_value}.pkl"
    
    def exists(self, hash_value: str) -> bool:
        """
        Vérifie si un binaire existe déjà pour ce hash.
        
        Args:
            hash_value: Hash SHA-256 de la feature
            
        Returns:
            True si le fichier existe, False sinon
        """
        file_path = self._get_hash_path(hash_value)
        return file_path.exists()
    
    def save(self, obj: object, hash_value: str) -> Tuple[str, int]:
        """
        Sauvegarde un objet Python sérialisé avec cloudpickle.
        
        Args:
            obj: Objet Python à sérialiser (fonction ou classe)
            hash_value: Hash SHA-256 du code source
            
        Returns:
            Tuple (chemin_relatif, taille_en_octets)
            
        Raises:
            IOError: Si l'écriture échoue
            ValueError: Si le hash ne correspond pas
        """
        file_path = self._get_hash_path(hash_value)
        
        try:
            # Sérialisation avec cloudpickle
            binary_data = cloudpickle.dumps(obj)
            
            # Vérification optionnelle du hash (sécurité)
            computed_hash = hashlib.sha256(binary_data).hexdigest()
            logger.debug(f"Computed hash: {computed_hash}, Expected: {hash_value}")
            
            # Écriture atomique
            temp_path = file_path.with_suffix('.tmp')
            temp_path.write_bytes(binary_data)
            temp_path.rename(file_path)
            
            binary_size = len(binary_data)
            relative_path = self._get_relative_path(hash_value)
            
            logger.info(f"✅ Feature binary saved: {relative_path} ({binary_size} bytes)")
            
            return relative_path, binary_size
            
        except Exception as e:
            logger.error(f"❌ Failed to save feature binary for hash {hash_value}: {e}")
            raise
    
    def load(self, hash_value: str) -> object:
        """
        Charge un objet Python depuis son binaire pickle.
        
        Args:
            hash_value: Hash SHA-256 de la feature
            
        Returns:
            Objet Python désérialisé (fonction ou classe)
            
        Raises:
            FileNotFoundError: Si le fichier n'existe pas
            pickle.UnpicklingError: Si la désérialisation échoue
        """
        file_path = self._get_hash_path(hash_value)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Binary not found for hash: {hash_value}")
        
        try:
            binary_data = file_path.read_bytes()
            obj = cloudpickle.loads(binary_data)
            
            logger.debug(f"✅ Feature loaded from: {self._get_relative_path(hash_value)}")
            
            return obj
            
        except Exception as e:
            logger.error(f"❌ Failed to load feature binary for hash {hash_value}: {e}")
            raise
    
    def delete(self, hash_value: str) -> bool:
        """
        Supprime un binaire du filesystem.
        
        Args:
            hash_value: Hash SHA-256 de la feature
            
        Returns:
            True si supprimé, False si n'existait pas
        """
        file_path = self._get_hash_path(hash_value)
        
        if file_path.exists():
            file_path.unlink()
            logger.info(f"🗑️  Feature binary deleted: {hash_value}")
            return True
        
        return False
    
    def get_size(self, hash_value: str) -> Optional[int]:
        """
        Retourne la taille du binaire en octets.
        
        Args:
            hash_value: Hash SHA-256 de la feature
            
        Returns:
            Taille en octets, ou None si le fichier n'existe pas
        """
        file_path = self._get_hash_path(hash_value)
        
        if file_path.exists():
            return file_path.stat().st_size
        
        return None
    
    def cleanup_orphans(self) -> int:
        """
        Nettoie les fichiers binaires orphelins (sans entrée en BDD).
        
        Returns:
            Nombre de fichiers supprimés
        """
        from .models import Feature
        
        deleted_count = 0
        db_hashes = set(Feature.objects.values_list('hash', flat=True))
        
        # Parcours des fichiers
        for subdir in self.hash_dir.iterdir():
            if not subdir.is_dir():
                continue
            
            for file_path in subdir.glob("*.pkl"):
                hash_value = file_path.stem
                
                if hash_value not in db_hashes:
                    file_path.unlink()
                    deleted_count += 1
                    logger.info(f"🗑️  Orphan binary deleted: {hash_value}")
        
        return deleted_count