# notelib_core/feature.py
import textwrap
import ast
import inspect
import logging
from typing import Callable, List, Any, Dict

from .registry import FEATURE_REGISTRY, FeatureDef

logger = logging.getLogger("notelib")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[NoteLib] %(levelname)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)



# =======================================================
# 🧠 Décorateur principal
# =======================================================
def _extract_obj_code_from_cell(cell_code: str, obj_name: str) -> str:
    """
    Extrait uniquement le code source de la fonction ou classe `obj_name`
    définie dans un code de cellule (cell_code).
    """
    try:
        tree = ast.parse(cell_code)
    except SyntaxError:
        return cell_code

    lines = cell_code.splitlines()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == obj_name:
                # Les numéros de ligne dans AST sont 1-based
                start = node.lineno - 1
                end = getattr(node, "end_lineno", None)
                if end is None:
                    # Python < 3.8 fallback
                    end = start + len(inspect.getsource(node).splitlines())
                snippet = "\n".join(lines[start:end])
                return textwrap.dedent(snippet)
    return cell_code  # fallback


def feature_factory(registry, globals_dict: Dict[str, Any]):
    """
    Factory du décorateur @feature.
    Isole automatiquement le code de chaque fonction/classe décorée.
    """
    def feature(obj):
        # Récupérer le code de la cellule
        cell_code = globals_dict.get("__last_cell_code__", "") or ""
        cell_code = textwrap.dedent(cell_code)

        # Extraire le code propre à cet objet
        obj_code = _extract_obj_code_from_cell(cell_code, obj.__name__)

        # Enregistrer la feature avec ce code isolé
        registry.register(obj, code_override=obj_code)
        return obj

    return feature



def feature(obj):
    import textwrap
    code = ""
    # récupérer le code courant injecté par le loader
    import builtins
    code = globals().get("__last_cell_code__", "") or getattr(builtins, "__last_cell_code__", "")
    FEATURE_REGISTRY.register(obj, code_override=textwrap.dedent(code))
    return obj