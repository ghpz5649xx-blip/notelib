# apps/artefacts/storage.py
"""
Gestionnaire de stockage des artefacts sur filesystem.

Architecture :
storage/artefacts/
├── by_hash/
│   ├── e3/
│   │   └── e3b0c442...b855.zst
│   └── a4/
│       └── a4d55a8d...4e5b.zst

Choix techniques :
- Compression zstandard (niveau 3 par défaut) : bon compromis vitesse/taux
- Hash SHA-256 sur contenu NON compressé pour déduplication
- Organisation par préfixe (2 premiers caractères) pour éviter trop de fichiers/dossier
- Écriture atomique via fichier temporaire
"""
import os
import hashlib
import cloudpickle
import zstandard as zstd
import logging
from pathlib import Path
from typing import Optional, Tuple, BinaryIO
from django.conf import settings

logger = logging.getLogger("notelib")


class ArtefactStorage:
    """
    Gère le stockage et la récupération des artefacts sur filesystem.
    
    Responsabilités :
    - Sérialisation (cloudpickle) + compression (zstd)
    - Calcul du hash SHA-256
    - Stockage organisé par préfixe
    - Lecture avec streaming pour gros fichiers
    """
    
    # Configuration par défaut
    DEFAULT_COMPRESSION_LEVEL = 3  # zstd: 1-22 (3 = bon compromis)
    HASH_PREFIX_LENGTH = 2  # Nombre de caractères pour le sous-dossier
    
    def __init__(self, base_dir: Optional[str] = None):
        """
        Initialise le gestionnaire de stockage.
        
        Args:
            base_dir: Répertoire racine. Si None, utilise settings.ARTEFACT_STORAGE_DIR
        """
        if base_dir is None:
            base_dir = getattr(
                settings,
                'ARTEFACT_STORAGE_DIR',
                os.path.join(settings.BASE_DIR, 'storage', 'artefacts')
            )
        
        self.base_dir = Path(base_dir)
        self.hash_dir = self.base_dir / "by_hash"
        
        # Création des répertoires
        self.hash_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration compression
        self.compression_level = getattr(
            settings,
            'ARTEFACT_COMPRESSION_LEVEL',
            self.DEFAULT_COMPRESSION_LEVEL
        )
        
        logger.debug(f"ArtefactStorage initialized at {self.base_dir}")
    
    def _get_hash_path(self, hash_value: str) -> Path:
        """
        Génère le chemin de stockage basé sur le hash.
        
        Args:
            hash_value: Hash SHA-256 (64 caractères hex)
        
        Returns:
            Chemin complet : .../by_hash/e3/e3b0c442...zst
        """
        prefix = hash_value[:self.HASH_PREFIX_LENGTH]
        subdir = self.hash_dir / prefix
        subdir.mkdir(exist_ok=True)
        return subdir / f"{hash_value}.zst"
    
    def _get_relative_path(self, hash_value: str) -> str:
        """
        Retourne le chemin relatif pour stockage en BDD.
        
        Args:
            hash_value: Hash SHA-256
        
        Returns:
            Chemin relatif : "by_hash/e3/e3b0c442...zst"
        """
        prefix = hash_value[:self.HASH_PREFIX_LENGTH]
        return f"by_hash/{prefix}/{hash_value}.zst"
    
    def compute_hash(self, data: bytes) -> str:
        """
        Calcule le SHA-256 d'un contenu binaire.
        
        Args:
            data: Données binaires
        
        Returns:
            Hash SHA-256 en hexadécimal (64 caractères)
        """
        return hashlib.sha256(data).hexdigest()
    
    def serialize_and_compress(
        self,
        obj: object
    ) -> Tuple[bytes, bytes, str]:
        """
        Sérialise un objet Python et le compresse.
        
        Workflow :
        1. Sérialisation avec cloudpickle
        2. Calcul du hash sur le binaire non compressé
        3. Compression avec zstd
        
        Args:
            obj: Objet Python à sérialiser
        
        Returns:
            Tuple (données_compressées, données_brutes, hash)
        
        Raises:
            Exception: Si sérialisation ou compression échoue
        """
        try:
            # Sérialisation
            raw_data = cloudpickle.dumps(obj)
            
            # Hash du contenu non compressé (pour déduplication)
            hash_value = self.compute_hash(raw_data)
            
            # Compression
            compressor = zstd.ZstdCompressor(level=self.compression_level)
            compressed_data = compressor.compress(raw_data)
            
            logger.debug(
                f"Serialized and compressed: {len(raw_data)} -> {len(compressed_data)} bytes "
                f"(ratio: {len(compressed_data)/len(raw_data):.2%})"
            )
            
            return compressed_data, raw_data, hash_value
            
        except Exception as e:
            logger.error(f"Failed to serialize/compress object: {e}")
            raise
    
    def decompress_and_deserialize(self, compressed_data: bytes) -> object:
        """
        Décompresse et désérialise un artefact.
        
        Args:
            compressed_data: Données compressées en zstd
        
        Returns:
            Objet Python désérialisé
        
        Raises:
            Exception: Si décompression ou désérialisation échoue
        """
        try:
            # Décompression
            decompressor = zstd.ZstdDecompressor()
            raw_data = decompressor.decompress(compressed_data)
            
            # Désérialisation
            obj = cloudpickle.loads(raw_data)
            
            return obj
            
        except Exception as e:
            logger.error(f"Failed to decompress/deserialize: {e}")
            raise
    
    def exists(self, hash_value: str) -> bool:
        """
        Vérifie si un artefact existe déjà.
        
        Args:
            hash_value: Hash SHA-256
        
        Returns:
            True si le fichier existe
        """
        file_path = self._get_hash_path(hash_value)
        return file_path.exists()
    
    def save(
        self,
        obj: object,
        hash_override: Optional[str] = None
    ) -> Tuple[str, int, int, str]:
        """
        Sauvegarde un objet sérialisé et compressé.
        
        Args:
            obj: Objet Python à persister
            hash_override: Hash pré-calculé (optionnel)
        
        Returns:
            Tuple (chemin_relatif, taille_compressée, taille_brute, hash)
        
        Raises:
            IOError: Si écriture échoue
            ValueError: Si hash ne correspond pas
        """
        # Sérialisation + compression
        compressed_data, raw_data, computed_hash = self.serialize_and_compress(obj)
        
        # Vérification du hash si fourni
        if hash_override and hash_override != computed_hash:
            raise ValueError(
                f"Hash mismatch: expected {hash_override}, got {computed_hash}"
            )
        
        hash_value = hash_override or computed_hash
        file_path = self._get_hash_path(hash_value)
        
        # Vérification si déjà existant (déduplication)
        if file_path.exists():
            logger.info(f"Artefact already exists (deduplicated): {hash_value[:8]}")
            return (
                self._get_relative_path(hash_value),
                len(compressed_data),
                len(raw_data),
                hash_value
            )
        
        try:
            # Écriture atomique via fichier temporaire
            temp_path = file_path.with_suffix('.tmp')
            temp_path.write_bytes(compressed_data)
            temp_path.rename(file_path)
            
            relative_path = self._get_relative_path(hash_value)
            
            logger.info(
                f"💾 Artefact saved: {relative_path} "
                f"({len(compressed_data)} bytes, ratio: {len(compressed_data)/len(raw_data):.2%})"
            )
            
            return relative_path, len(compressed_data), len(raw_data), hash_value
            
        except Exception as e:
            logger.error(f"❌ Failed to save artefact {hash_value}: {e}")
            # Nettoyage du fichier temporaire
            if temp_path.exists():
                temp_path.unlink()
            raise
    
    def load(self, hash_value: str) -> object:
        """
        Charge et désérialise un artefact.
        
        Args:
            hash_value: Hash SHA-256
        
        Returns:
            Objet Python désérialisé
        
        Raises:
            FileNotFoundError: Si l'artefact n'existe pas
        """
        file_path = self._get_hash_path(hash_value)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Artefact not found: {hash_value}")
        
        try:
            compressed_data = file_path.read_bytes()
            obj = self.decompress_and_deserialize(compressed_data)
            
            logger.debug(f"✅ Artefact loaded: {hash_value[:8]}")
            
            return obj
            
        except Exception as e:
            logger.error(f"❌ Failed to load artefact {hash_value}: {e}")
            raise
    
    def stream(self, hash_value: str, chunk_size: int = 8192) -> BinaryIO:
        """
        Ouvre un artefact en mode streaming (pour gros fichiers).
        
        Args:
            hash_value: Hash SHA-256
            chunk_size: Taille des chunks
        
        Returns:
            File object binaire
        
        Raises:
            FileNotFoundError: Si l'artefact n'existe pas
        """
        file_path = self._get_hash_path(hash_value)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Artefact not found: {hash_value}")
        
        return open(file_path, 'rb')
    
    def delete(self, hash_value: str) -> bool:
        """
        Supprime un artefact du filesystem.
        
        Args:
            hash_value: Hash SHA-256
        
        Returns:
            True si supprimé, False si n'existait pas
        """
        file_path = self._get_hash_path(hash_value)
        
        if file_path.exists():
            file_path.unlink()
            logger.info(f"🗑️  Artefact deleted: {hash_value[:8]}")
            return True
        
        return False
    
    def get_size(self, hash_value: str) -> Optional[int]:
        """
        Retourne la taille d'un artefact en octets.
        
        Args:
            hash_value: Hash SHA-256
        
        Returns:
            Taille en octets ou None si inexistant
        """
        file_path = self._get_hash_path(hash_value)
        
        if file_path.exists():
            return file_path.stat().st_size
        
        return None
    
    def cleanup_orphans(self, existing_hashes: set) -> int:
        """
        Nettoie les fichiers orphelins (sans entrée en BDD).
        
        Args:
            existing_hashes: Set des hash présents en BDD
        
        Returns:
            Nombre de fichiers supprimés
        """
        deleted_count = 0
        
        for subdir in self.hash_dir.iterdir():
            if not subdir.is_dir():
                continue
            
            for file_path in subdir.glob("*.zst"):
                hash_value = file_path.stem
                
                if hash_value not in existing_hashes:
                    file_path.unlink()
                    deleted_count += 1
                    logger.info(f"🗑️  Orphan artefact deleted: {hash_value[:8]}")
        
        logger.info(f"🧹 Cleanup completed: {deleted_count} orphan files deleted")
        
        return deleted_count


# Instance globale
artefact_storage = ArtefactStorage()