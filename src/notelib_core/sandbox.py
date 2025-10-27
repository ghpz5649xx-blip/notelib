# notelib_core/sandbox.py
import os
import tempfile
import shutil
from contextlib import contextmanager
from pathlib import Path
import logging

logger = logging.getLogger("notelib")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[NoteLib] %(levelname)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


# =======================================================
# 🔒 Sandbox strict (lecture seule)
# =======================================================
@contextmanager
def sandboxed_open_strict():
    """
    Exécute le code dans un environnement où seul le notebook et les modules internes sont accessibles.
    Toute tentative d'accès à d'autres fichiers échoue.
    """
    cwd = os.getcwd()
    tmp_dir = tempfile.mkdtemp(prefix="notelib_strict_")

    # On crée un sous-répertoire minimal
    try:
        os.chdir(tmp_dir)
        logger.debug(f"[sandbox:stric] Entered {tmp_dir}")
        yield
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.debug(f"[sandbox:stric] Cleaned {tmp_dir}")


# =======================================================
# 🧪 Sandbox temporaire (isolée mais permissive)
# =======================================================
@contextmanager
def sandboxed_open_temp():
    """
    Exécute le code dans un répertoire temporaire. Les fichiers créés sont isolés
    et supprimés à la fin.
    """
    cwd = os.getcwd()
    tmp_dir = tempfile.mkdtemp(prefix="notelib_temp_")

    try:
        os.chdir(tmp_dir)
        logger.debug(f"[sandbox:temp] Entered {tmp_dir}")
        yield
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.debug(f"[sandbox:temp] Cleaned {tmp_dir}")


# =======================================================
# 🪶 Sandbox "none" (mode normal)
# =======================================================
@contextmanager
def sandboxed_open_none():
    """Ne fait rien : utilisé pour du debug ou des tests locaux."""
    yield
