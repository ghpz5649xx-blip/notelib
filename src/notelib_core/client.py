# notelib_core/client.py
"""
Client API pour communiquer avec le serveur NoteLib.

Ce module permet à notelib_core (client) d'envoyer les features
au serveur Django sans créer de dépendance avec Django.
"""
import requests
import cloudpickle
import base64
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
from .config import BASE_URL

logger = logging.getLogger("notelib")


class NoteLibClient:
    """
    Client HTTP pour interagir avec le serveur NoteLib.
    
    Usage:
        client = NoteLibClient("http://localhost:8000")
        client.publish_feature(feature_def)
    """
    
    def __init__(self, base_url: str = BASE_URL, api_key: Optional[str] = None, timeout: int = 30):
        """
        Initialise le client.
        
        Args:
            base_url: URL du serveur (ex: "http://localhost:8000")
            api_key: Clé API pour authentification (optionnel)
            timeout: Timeout des requêtes en secondes
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()
        
        if api_key:
            self.session.headers.update({'Authorization': f'Bearer {api_key}'})
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Effectue une requête HTTP vers le serveur.
        
        Args:
            method: Méthode HTTP (GET, POST, etc.)
            endpoint: Endpoint de l'API (ex: "/api/features/")
            **kwargs: Arguments passés à requests
        
        Returns:
            Réponse JSON ou None si erreur
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = self.session.request(
                method,
                url,
                timeout=kwargs.pop('timeout', self.timeout),
                **kwargs
            )
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.Timeout:
            logger.error(f"⏱️  Timeout while connecting to {url}")
            return None
        except requests.exceptions.ConnectionError:
            logger.error(f"🔌 Connection error to {url}")
            return None
        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ HTTP error {e.response.status_code}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            return None
    
    def publish_feature(self, feature_def) -> Optional[Dict[str, Any]]:
        """
        Publie une feature sur le serveur.
        
        Args:
            feature_def: Instance de FeatureDef
        
        Returns:
            Réponse du serveur ou None si erreur
        """
        try:
            # Sérialisation de l'objet Python avec cloudpickle
            obj_bytes = cloudpickle.dumps(feature_def.obj)
            obj_b64 = base64.b64encode(obj_bytes).decode('utf-8')
            
            payload = {
                'name': feature_def.name,
                'hash': feature_def.hash,
                'code': feature_def.code,
                'inputs': feature_def.inputs,
                'outputs': feature_def.outputs,
                'defined_in': feature_def.defined_in,
                'obj_data': obj_b64,
            }
            
            response = self._make_request(
                'POST',
                '/api/features/import/',
                json=payload
            )
            
            if response:
                logger.info(f"✅ Feature published: {feature_def.name}")
            else:
                logger.warning(f"⚠️  Failed to publish feature: {feature_def.name}")
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Error publishing feature {feature_def.name}: {e}")
            return None
    
    def publish_notebook(self, notebook_path: str, sandbox_mode: str = "temp") -> Optional[Dict[str, Any]]:
        """
        Envoie un notebook au serveur pour traitement.
        
        Le serveur se charge de charger le notebook et d'extraire les features.
        
        Args:
            notebook_path: Chemin vers le notebook
            sandbox_mode: Mode sandbox ("strict", "temp", "none")
        
        Returns:
            Réponse du serveur avec les features importées
        """
        payload = {
            'path': str(notebook_path),
            'sandbox_mode': sandbox_mode,
            'publish': True,
        }
        
        response = self._make_request(
            'POST',
            '/api/features/load_notebook/',
            json=payload
        )
        
        if response:
            logger.info(
                f"✅ Notebook published: {response.get('features_imported', 0)} imported, "
                f"{response.get('features_existing', 0)} existing"
            )
        
        return response
    
    def list_features(self, loaded_only: bool = False) -> Optional[List[Dict[str, Any]]]:
        """
        Liste toutes les features sur le serveur.
        
        Args:
            loaded_only: Si True, ne retourne que les features chargées en mémoire
        
        Returns:
            Liste des features ou None si erreur
        """
        params = {'loaded_only': 'true' if loaded_only else 'false'}
        
        response = self._make_request(
            'GET',
            '/api/features/list/',
            params=params
        )
        
        return response.get('features', []) if response else None
    
    def get_feature(self, hash_value: str) -> Optional[Dict[str, Any]]:
        """
        Récupère les détails d'une feature.
        
        Args:
            hash_value: Hash de la feature
        
        Returns:
            Détails de la feature ou None si erreur
        """
        return self._make_request(
            'GET',
            f'/api/features/{hash_value}/'
        )
    
    def load_feature(self, hash_value: str) -> bool:
        """
        Demande au serveur de charger une feature en mémoire.
        
        Args:
            hash_value: Hash de la feature
        
        Returns:
            True si succès, False sinon
        """
        response = self._make_request(
            'POST',
            f'/api/features/{hash_value}/load/'
        )
        
        return response is not None and response.get('status') == 'success'
    
    def unload_feature(self, hash_value: str) -> bool:
        """
        Demande au serveur de décharger une feature de la mémoire.
        
        Args:
            hash_value: Hash de la feature
        
        Returns:
            True si succès, False sinon
        """
        response = self._make_request(
            'POST',
            f'/api/features/{hash_value}/unload/'
        )
        
        return response is not None and response.get('status') == 'success'
    
    def get_registry_stats(self) -> Optional[Dict[str, Any]]:
        """
        Récupère les statistiques du registry serveur.
        
        Returns:
            Statistiques ou None si erreur
        """
        return self._make_request(
            'GET',
            '/api/features/registry/stats/'
        )
    
    def ping(self) -> bool:
        """
        Vérifie si le serveur est accessible.
        
        Returns:
            True si le serveur répond, False sinon
        """
        try:
            response = self.session.get(
                f"{self.base_url}/api/health/",
                timeout=5
            )
            return response.status_code == 200
        except:
            return False


# Instance globale optionnelle (peut être configurée via un fichier de config)
_default_client: Optional[NoteLibClient] = None


def configure_client(base_url: str, api_key: Optional[str] = None):
    """
    Configure le client global.
    
    Args:
        base_url: URL du serveur NoteLib
        api_key: Clé API (optionnel)
    """
    global _default_client
    _default_client = NoteLibClient(base_url, api_key)
    logger.info(f"🔗 NoteLib client configured: {base_url}")


def get_client() -> Optional[NoteLibClient]:
    """
    Retourne le client global configuré.
    
    Returns:
        Instance de NoteLibClient ou None si non configuré
    """
    return _default_client