import threading
import ast
from typing import Optional, Dict, List, Any
import inspect
import hashlib

class FeatureDef:
    """Représentation d'une feature enregistrée."""

    def __init__(self, obj, defined_in: Optional[str] = None, code_override: Optional[str] = None, hash_value: Optional[str] = None):
        if not (inspect.isfunction(obj) or inspect.isclass(obj)):
            raise TypeError(f"FeatureDef can only wrap a function or class, got {type(obj)}")

        self.obj = obj
        self.name = obj.__name__
        self.defined_in = defined_in

        # Récupérer le code source
        self.code = code_override or ""
        self.hash = hash_value or hashlib.sha256(self.code.encode()).hexdigest()

        if inspect.isclass(obj):
            self._extract_class_signature(obj)
        else:
            self._extract_function_signature_and_output(obj)

    # =======================================================
    # 🔍 Extraction pour les classes
    # =======================================================
    def _extract_class_signature(self, obj):
        try:
            sig = inspect.signature(obj.__init__)
            self.inputs = [
                f"{name}:{param.annotation.__name__ if param.annotation != inspect._empty else 'Any'}"
                for name, param in sig.parameters.items()
                if name != "self"
            ]
        except Exception:
            self.inputs = []
        self.outputs = [f"{obj.__name__}:object"]

    # =======================================================
    # 🔍 Extraction pour les fonctions
    # =======================================================
    def _extract_function_signature_and_output(self, obj):
        # Récupérer les inputs avec types
        try:
            sig = inspect.signature(obj)
            self.inputs = []
            for name, param in sig.parameters.items():
                ann = param.annotation
                ann_str = self._annotation_to_str(ann)
                self.inputs.append(f"{name}:{ann_str}")
        except Exception:
            self.inputs = []

        # Déterminer l’output (nom + type)
        output_name, output_type = self._infer_output_from_code_and_signature()
        self.outputs = [f"{output_name}:{output_type}"]

    # =======================================================
    # 🧠 Conversion d’annotation -> string
    # =======================================================
    def _annotation_to_str(self, ann: Any) -> str:
        if ann == inspect._empty:
            return "Any"
        if hasattr(ann, "__name__"):
            return ann.__name__
        if hasattr(ann, "__module__"):
            return f"{ann.__module__}.{getattr(ann, '__name__', str(ann))}"
        return str(ann)

    # =======================================================
    # 🧩 Analyse AST du code pour extraire le nom de variable retournée
    # =======================================================
    def _infer_output_from_code_and_signature(self):
        output_name = self.name  # fallback
        output_type = "Any"

        # Essayer d'obtenir le type de retour via l’annotation
        try:
            sig = inspect.signature(self.obj)
            if sig.return_annotation != inspect._empty:
                output_type = self._annotation_to_str(sig.return_annotation)
        except Exception:
            pass

        # Si on a du code source : analyser le AST pour détecter le return
        if self.code:
            try:
                tree = ast.parse(self.code)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Return) and isinstance(node.value, ast.Name):
                        output_name = node.value.id
                        break
            except Exception:
                pass

        return output_name, output_type

    # =======================================================
    # 🔧 Conversion en dict
    # =======================================================
    def to_dict(self):
        return {
            "name": self.name,
            "hash": self.hash,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "defined_in": self.defined_in,
            "code": self.code,
        }


class FeatureRegistry:
    """
    Thread-safe feature registry. Stores features by name and provides access to them.
    """

    def __init__(self):
        self._features_by_name: Dict[str, FeatureDef] = {}
        self._features_by_hash: Dict[str, FeatureDef] = {}
        self._lock = threading.Lock()

    # -- Base API --
    def register(self, obj, code_override: Optional[str] = None, hash_value: Optional[str] = None):
        with self._lock:
            feature_def = FeatureDef(obj, code_override=code_override, hash_value=hash_value)
            self._features_by_name[feature_def.name] = feature_def
            self._features_by_hash[feature_def.hash] = feature_def
    
    def register_feature_def(self, feature_def:FeatureDef):
        with self._lock:
            self._features_by_name[feature_def.name] = feature_def
            self._features_by_hash[feature_def.hash] = feature_def


    def unregister(self, key: str):
        with self._lock:
            if key in self._features_by_name:
                feature = self._features_by_name.pop(key)
                self._features_by_hash.pop(feature.hash, None)
            
            elif key in self._features_by_hash:
                feature = self._features_by_hash.pop(key)
                self._features_by_name.pop(feature.name, None)


    def get(self, key: str) -> Optional[FeatureDef]:
        return self._features_by_name.get(key) or self._features_by_hash.get(key)

    def all(self) -> List[FeatureDef]:
        return list(self._features_by_name.values())
    
    def is_loaded(self, key: str) -> bool:
        return key in self._features_by_hash or key in self._features_by_name

    def clear(self):
        with self._lock:
            self._features_by_name.clear()

    # -- Utilitaires --

    def to_dict(self):
        return [f.to_dict() for f in self.all()]
    
    def list_hashes(self):
        return list(self._features_by_hash.keys())


# 🔧 Instance globale du registre utilisée par le décorateur @feature
FEATURE_REGISTRY = FeatureRegistry()
