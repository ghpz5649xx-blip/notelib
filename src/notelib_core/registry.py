import threading
from typing import Dict, List, Optional

from typing import List, Optional, Callable
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

        # récupérer le code source
        self.code = code_override or ""

        # hash du code
        self.hash = hash_value or hashlib.sha256(self.code.encode()).hexdigest()

        # inputs / outputs
        if inspect.isclass(obj):
            try:
                sig = inspect.signature(obj.__init__)
                self.inputs = [p for p in sig.parameters if p != "self"]
            except Exception:
                self.inputs = []
            self.outputs = [obj.__name__]
        else:
            try:
                sig = inspect.signature(obj)
                self.inputs = list(sig.parameters.keys())
            except Exception:
                self.inputs = []
            self.outputs = [obj.__name__]

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
