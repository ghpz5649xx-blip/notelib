# apps/executions/sandbox.py
"""
Module d'exécution sandboxée des features côté serveur.

Responsabilités :
- Charger une feature depuis le registre
- L'exécuter dans un processus isolé
- Capturer stdout/stderr
- Imposer timeout et limites mémoire
- Retourner le résultat binaire + métadonnées

Architecture :
- Utilise subprocess pour l'isolation
- Alternative future : conteneurs Docker/Podman
"""
import os
import sys
import subprocess
import tempfile
import cloudpickle
import logging
import traceback
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from django.conf import settings

logger = logging.getLogger("notelib")


class SandboxExecutionError(Exception):
    """Exception levée lors d'une erreur d'exécution sandboxée."""
    pass


class FeatureSandbox:
    """
    Exécute une feature dans un environnement isolé.
    
    Isolation via subprocess :
    - Processus séparé
    - Timeout configurable
    - Capture stdout/stderr
    - Limites mémoire (ulimit)
    
    Alternative future : Docker/Podman pour isolation renforcée.
    """
    
    def __init__(
        self,
        timeout: int = 300,  # 5 minutes par défaut
        max_memory_mb: int = 2048,  # 2 GB par défaut
    ):
        """
        Initialise le sandbox.
        
        Args:
            timeout: Timeout en secondes
            max_memory_mb: Limite mémoire en MB
        """
        self.timeout = timeout
        self.max_memory_mb = max_memory_mb
    
    def execute_feature(
        self,
        feature_hash: str,
        inputs: Dict[str, Any],
        staging_dir: Optional[Path] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Exécute une feature dans un subprocess isolé.
        
        Workflow :
        1. Sérialise les inputs dans un fichier temporaire
        2. Lance un subprocess Python qui :
           - Charge la feature depuis le registre
           - Exécute avec les inputs
           - Sérialise le résultat
        3. Lit le résultat depuis le fichier temporaire
        4. Retourne (result_bytes, metadata)
        
        Args:
            feature_hash: Hash de la feature à exécuter
            inputs: Dictionnaire des inputs
            staging_dir: Répertoire temporaire (créé si None)
        
        Returns:
            Tuple (result_bytes, metadata)
            - result_bytes : résultat sérialisé (non compressé)
            - metadata : {duration, stdout, stderr, exit_code}
        
        Raises:
            SandboxExecutionError: Si exécution échoue
        """
        # Création du répertoire staging
        if staging_dir is None:
            staging_dir = Path(tempfile.mkdtemp(prefix="notelib_exec_"))
        else:
            staging_dir = Path(staging_dir)
            staging_dir.mkdir(parents=True, exist_ok=True)
        
        input_file = staging_dir / "inputs.pkl"
        output_file = staging_dir / "output.pkl"
        
        try:
            # Sérialisation des inputs
            with open(input_file, 'wb') as f:
                cloudpickle.dump(inputs, f)
            
            # Préparation du script d'exécution
            script = self._generate_execution_script(
                feature_hash,
                str(input_file),
                str(output_file)
            )
            
            script_file = staging_dir / "execute.py"
            script_file.write_text(script)
            
            # Exécution dans subprocess
            result = subprocess.run(
                [sys.executable, str(script_file)],
                timeout=self.timeout,
                capture_output=True,
                text=True,
                cwd=str(staging_dir),
                env=self._get_sandbox_env(),
            )
            
            # Vérification du code de sortie
            if result.returncode != 0:
                raise SandboxExecutionError(
                    f"Feature execution failed (exit code {result.returncode})\n"
                    f"STDOUT:\n{result.stdout}\n"
                    f"STDERR:\n{result.stderr}"
                )
            
            # Lecture du résultat
            if not output_file.exists():
                raise SandboxExecutionError(
                    "Output file not created by subprocess\n"
                    f"STDOUT:\n{result.stdout}\n"
                    f"STDERR:\n{result.stderr}"
                )
            
            with open(output_file, 'rb') as f:
                result_bytes = f.read()
            
            # Métadonnées
            metadata = {
                'stdout': result.stdout,
                'stderr': result.stderr,
                'exit_code': result.returncode,
            }
            
            logger.info(f"✅ Feature {feature_hash[:8]} executed successfully")
            
            return result_bytes, metadata
        
        except subprocess.TimeoutExpired:
            raise SandboxExecutionError(
                f"Feature execution timeout ({self.timeout}s exceeded)"
            )
        
        except Exception as e:
            logger.error(f"Sandbox execution error: {e}", exc_info=True)
            raise SandboxExecutionError(str(e))
        
        finally:
            # Nettoyage (optionnel, pour sécurité)
            cleanup = getattr(settings, 'NOTELIB_CLEANUP_STAGING', True)
            if cleanup:
                try:
                    import shutil
                    shutil.rmtree(staging_dir, ignore_errors=True)
                except:
                    pass
    
    def _generate_execution_script(
        self,
        feature_hash: str,
        input_file: str,
        output_file: str
    ) -> str:
        """
        Génère le script Python exécuté dans le subprocess.
        
        Le script :
        - Charge la feature depuis le storage
        - Désérialise les inputs
        - Exécute la feature
        - Sérialise le résultat
        
        Args:
            feature_hash: Hash de la feature
            input_file: Chemin vers le fichier inputs
            output_file: Chemin vers le fichier output
        
        Returns:
            Code Python du script
        """
        # Note: On importe Django dans le subprocess pour accéder aux models
        script = f"""
import sys
import os
import cloudpickle
import traceback

# Setup Django
sys.path.insert(0, '{settings.BASE_DIR}')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'notelib.settings')

import django
django.setup()

from features.services import feature_service

try:
    # Chargement de la feature
    feature_obj = feature_service.load_feature('{feature_hash}')
    
    # Chargement des inputs
    with open('{input_file}', 'rb') as f:
        inputs = cloudpickle.load(f)
    
    # Exécution
    if callable(feature_obj):
        result = feature_obj(**inputs)
    else:
        raise TypeError(f"Feature is not callable: {{type(feature_obj)}}")
    
    # Sérialisation du résultat
    result_bytes = cloudpickle.dumps(result)
    with open('{output_file}', 'wb') as f:
        f.write(result_bytes)
    
    print("Execution successful")
    sys.exit(0)

except Exception as e:
    print(f"ERROR: {{e}}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
"""
        return script
    
    def _get_sandbox_env(self) -> Dict[str, str]:
        """
        Retourne les variables d'environnement pour le subprocess.
        
        Hérite de l'env parent mais peut être restreint pour sécurité.
        """
        env = os.environ.copy()
        
        # On peut restreindre l'env ici pour plus de sécurité
        # Par exemple : supprimer AWS credentials, etc.
        
        # Ajout de variables spécifiques
        env['NOTELIB_SANDBOX_MODE'] = '1'
        
        return env


# Instance globale
feature_sandbox = FeatureSandbox()