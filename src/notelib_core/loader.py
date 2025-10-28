# notelib_core/loader.py
import nbformat
import traceback
import contextlib
from pathlib import Path
from typing import Literal, Dict, Any, List
import logging
import types
import sys

from .sandbox import sandboxed_open_strict, sandboxed_open_temp
from .registry import FeatureRegistry
from .client import NoteLibClient

logger = logging.getLogger("notelib")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[NoteLib] %(levelname)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

client = NoteLibClient()


class NotebookSandbox:
    """
    Encapsule l'environnement d'exécution isolé d'un notebook.
    
    Chaque instance maintient :
    - Son propre registre de features
    - Son propre espace de globals (sandbox_globals)
    - Ses propres modules notelib_core isolés
    """
    
    def __init__(self, notebook_path: Path):
        self.path = notebook_path
        self.registry = FeatureRegistry()
        self.globals = self._create_sandbox_globals()
        self.errors: List[Dict[str, Any]] = []
        
        # Sauvegarde des modules sys.modules originaux
        self._original_modules = {}
        
    def _create_sandbox_globals(self) -> Dict[str, Any]:
        """Crée l'espace de globals isolé pour le notebook."""
        return {
            "__name__": "__notebook__",
            "__file__": str(self.path),
            "__builtins__": __builtins__,
        }
    
    def _inject_notelib_modules(self):
        """Injecte les modules notelib_core isolés dans le sandbox."""
        from .feature import feature_factory
        
        # Création du décorateur @feature avec closure sur sandbox_globals
        feature_decorator = feature_factory(self.registry, self.globals)
        
        # Création du module feature
        feature_mod = types.ModuleType("notelib_core.feature")
        feature_mod.feature = feature_decorator
        feature_mod.FEATURE_REGISTRY = self.registry
        
        # Création du module registry
        registry_mod = types.ModuleType("notelib_core.registry")
        registry_mod.FEATURE_REGISTRY = self.registry
        registry_mod.FeatureRegistry = FeatureRegistry
        
        # Création du module notelib_core
        notelib_core_mod = types.ModuleType("notelib_core")
        notelib_core_mod.feature = feature_mod
        notelib_core_mod.registry = registry_mod
        
        # Injection dans sandbox_globals
        self.globals["notelib_core"] = notelib_core_mod
        
        # Sauvegarde et injection temporaire dans sys.modules
        for mod_name in ["notelib_core", "notelib_core.feature", "notelib_core.registry"]:
            self._original_modules[mod_name] = sys.modules.get(mod_name)
        
        sys.modules["notelib_core"] = notelib_core_mod
        sys.modules["notelib_core.feature"] = feature_mod
        sys.modules["notelib_core.registry"] = registry_mod
    
    def _restore_modules(self):
        """Restaure les modules sys.modules originaux."""
        for mod_name, original_mod in self._original_modules.items():
            if original_mod is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = original_mod
        self._original_modules.clear()
    
    def execute_cell(self, cell_index: int, cell_code: str):
        """
        Exécute une cellule de code dans le sandbox.
        
        Args:
            cell_index: Index de la cellule
            cell_code: Code source de la cellule
        """
        if not cell_code.strip():
            return
        
        try:
            # Injection du code source dans le sandbox pour capture par @feature
            self.globals["__last_cell_code__"] = cell_code
            
            # Exécution dans le sandbox isolé
            exec(compile(cell_code, f"{self.path}#cell{cell_index}", "exec"), self.globals)
            
        except Exception as e:
            # Capture de l'erreur
            tb = traceback.format_exc()
            has_feature = "@feature" in cell_code
            
            self.errors.append({
                "cell": cell_index,
                "error": str(e),
                "trace": tb,
                "is_feature": has_feature,
            })
            
            # Log approprié selon le type de cellule
            log_fn = logger.error if has_feature else logger.warning
            log_fn(f"Cell {cell_index} failed ({'feature' if has_feature else 'non-feature'}): {e}")
        
        finally:
            # Nettoyage du code source pour éviter la pollution
            self.globals.pop("__last_cell_code__", None)
    
    def get_features(self) -> List:
        """Retourne toutes les features enregistrées dans ce sandbox."""
        return self.registry.all()


def load_notebook_features(
    notebook_path: str | Path,
    sandbox_mode: Literal["strict", "temp", "none"] = "temp",
    publish: bool = True,
) -> Dict[str, Any]:
    """
    Exécute un notebook .ipynb dans un environnement sandboxé et détecte les features via @feature.
    
    Args:
        notebook_path: Chemin vers le notebook .ipynb
        sandbox_mode: Mode de sandbox pour le système de fichiers
            - "strict": Accès lecture seule aux fichiers
            - "temp": Accès lecture/écriture dans un répertoire temporaire
            - "none": Pas de sandbox filesystem
        publish: Si True, publie les features vers le serveur (non implémenté ici)
    
    Returns:
        Dictionnaire contenant:
            - features: Liste des FeatureDef détectées
            - errors: Liste des erreurs rencontrées
    """
    path = Path(notebook_path)
    if not path.exists():
        raise FileNotFoundError(f"Notebook not found: {notebook_path}")
    
    # Lecture du notebook
    nb = nbformat.read(path, as_version=4)
    
    # Création du sandbox isolé
    sandbox = NotebookSandbox(path)
    
    # Sélection du contexte de sandbox filesystem
    fs_context = (
        sandboxed_open_strict() if sandbox_mode == "strict"
        else sandboxed_open_temp() if sandbox_mode == "temp"
        else contextlib.nullcontext()
    )
    
    try:
        # Injection des modules notelib_core isolés
        sandbox._inject_notelib_modules()
        
        # Exécution des cellules dans le sandbox filesystem
        with fs_context:
            for idx, cell in enumerate(nb.cells):
                if cell.get("cell_type") == "code":
                    cell_code = cell.get("source", "")
                    sandbox.execute_cell(idx, cell_code)
        
        # Extraction des features
        features_def = sandbox.get_features()
            
        # instenciation du log des features créés / existantes
        features_existing = 0
        features_imported = 0
        
        # Serialisation des features et enregistrement dans le file system 
        if publish:
            for feature_def in features_def : 
                response = client.publish_feature(feature_def)
                created = response.get('created',False)

                if created:
                    features_imported+=1
                else:
                    features_existing+=1



        
        # Log du résultat
        logger.info(
            f"✅ Notebook {path.name}: "
            f"{len(features_def)} features, "
            f"{len(sandbox.errors)} errors"
        )
        
        return {
            "features_def": features_def,
            "errors": sandbox.errors,
            "features_imported": features_imported,
            "features_existing": features_existing
        }
    
    finally:
        # Nettoyage : restauration des modules originaux
        sandbox._restore_modules()