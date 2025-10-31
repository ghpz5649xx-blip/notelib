# apps/executions/services.py
"""
Service d'orchestration des exécutions de pipelines.

Modes supportés :
1. Synchrone (dev) : exécution séquentielle bloquante
2. Asynchrone (prod) : délégation à Celery workers

Ce fichier implémente l'orchestration synchrone.
L'orchestration asynchrone est dans tasks.py (Celery).
"""
import logging
from typing import Dict, Any, List, Optional
from django.db import transaction
from django.utils import timezone

from .models import PipelineRun, StepRun, ExecutionLog
from .sandbox import feature_sandbox, SandboxExecutionError
from pipelines.models import Pipeline
from pipelines.services import pipeline_service
from artefacts.services import artefact_service
from features.models import FeatureMeta
import json

logger = logging.getLogger("notelib")


class ExecutionService:
    """
    Service d'orchestration des exécutions de pipeline.
    
    Implémentation synchrone :
    - Parcours topologique du DAG
    - Exécution séquentielle des steps
    - Propagation des artefacts entre steps
    """
    
    def __init__(self):
        self.sandbox = feature_sandbox
    
    def create_run(
        self,
        pipeline: Pipeline,
        input_manifest: Dict[str, Any],
        initiator,
        execution_mode: str = 'sync'
    ) -> PipelineRun:
        """
        Crée un PipelineRun et ses StepRuns.
        
        Args:
            pipeline: Pipeline à exécuter
            input_manifest: Inputs fournis
            initiator: Utilisateur
            execution_mode: 'sync' ou 'async'
        
        Returns:
            Instance PipelineRun
        
        Raises:
            ValueError: Si pipeline invalide
        """
        # Validation du pipeline
        if not pipeline.is_valid:
            raise ValueError(
                f"Pipeline is invalid: {pipeline.validation_errors}"
            )
        
        if not pipeline.is_active:
            raise ValueError("Pipeline is not active")
        
        with transaction.atomic():
            # Création du run
            run = PipelineRun.objects.create(
                pipeline=pipeline,
                initiator=initiator,
                input_manifest=input_manifest,
                execution_mode=execution_mode,
                status='PENDING',
            )
            
            # Création des StepRuns pour chaque node
            nodes = pipeline.get_nodes()
            for node in nodes:
                node_id = node['id']
                feature_name = node.get('feature_name')
                feature_hash = node.get('feature_hash')
                
                # Récupération de la feature
                if feature_hash:
                    feature = FeatureMeta.objects.filter(hash=feature_hash).first()
                elif feature_name:
                    feature = FeatureMeta.objects.filter(name=feature_name).first()
                else:
                    logger.warning(f"Node {node_id} has no feature reference")
                    continue
                
                if not feature:
                    logger.warning(
                        f"Feature not found for node {node_id}: "
                        f"name={feature_name}, hash={feature_hash}"
                    )
                    continue
                
                StepRun.objects.create(
                    pipeline_run=run,
                    node_id=node_id,
                    feature_name=feature.name,
                    feature_hash=feature.hash,
                    status='PENDING',
                )
            
            logger.info(
                f"✅ PipelineRun created: {run.id} "
                f"({len(nodes)} steps, mode={execution_mode})"
            )
        
        return run
    
    def execute_sync(self, run_id: str) -> PipelineRun:
        """
        Exécute un pipeline en mode synchrone (bloquant).
        
        Workflow :
        1. Calcul du tri topologique
        2. Pour chaque step dans l'ordre :
           - Vérifie dépendances satisfaites
           - Exécute dans sandbox
           - Crée artefact
           - Propage aux steps suivants
        
        Args:
            run_id: UUID du PipelineRun
        
        Returns:
            PipelineRun mis à jour
        
        Raises:
            Exception: Si exécution échoue
        """
        run = PipelineRun.objects.select_related('pipeline').get(id=run_id)
        
        try:
            # Marque le run comme démarré
            run.mark_running()
            
            # Calcul de l'ordre d'exécution
            execution_order = pipeline_service.topological_sort(run.pipeline.graph)
            
            logger.info(
                f"🚀 Starting sync execution: {run.id}\n"
                f"Order: {' -> '.join(execution_order)}"
            )
            
            # Exécution séquentielle
            for node_id in execution_order:
                step_run = StepRun.objects.get(
                    pipeline_run=run,
                    node_id=node_id
                )
                
                try:
                    self._execute_step(run, step_run)
                except Exception as e:
                    logger.error(f"Step {node_id} failed: {e}", exc_info=True)
            
            # Vérification du statut global
            failed_steps = run.step_runs.filter(status='FAILED').count()
            success_steps = run.step_runs.filter(status='SUCCESS').count()
            
            if failed_steps > 0:
                run.mark_failed(
                    f"{failed_steps} step(s) failed, {success_steps} succeeded"
                )
            else:
                run.mark_success()
                logger.info(f"✅ Pipeline execution completed: {run.id}")
            
            return run
        
        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}", exc_info=True)
            run.mark_failed(str(e))
            raise
    
    def _execute_step(self, run: PipelineRun, step: StepRun):
        """
        Exécute un StepRun individuel.
        
        Workflow :
        1. Résout les inputs depuis les artefacts des étapes précédentes
        2. Exécute la feature dans sandbox
        3. Crée l'artefact de sortie
        4. Met à jour le StepRun
        
        Args:
            run: PipelineRun parent
            step: StepRun à exécuter
        
        Raises:
            Exception: Si exécution échoue
        """
        logger.info(f"▶️  Executing step: {step.node_id} ({step.feature_name})")
        
        step.mark_running()
        
        try:
            # 1. Résolution des inputs
            inputs = self._resolve_inputs(run, step)
            
            # 2. Exécution dans sandbox
            result_bytes, metadata = self.sandbox.execute_feature(
                feature_hash=step.feature_hash,
                inputs=inputs
            )
            
            # 3. Désérialisation du résultat
            import cloudpickle
            result_obj = cloudpickle.loads(result_bytes)
            
            # 4. Création de l'artefact
            artefact = artefact_service.create_artefact(
                obj=result_obj,
                feature_hash=step.feature_hash,
                meta={
                    'pipeline_run_id': str(run.id),
                    'step_run_id': str(step.id),
                    'node_id': step.node_id,
                    'inputs': list(inputs.keys()),
                }
            )
            
            # 5. Mise à jour du step
            step.mark_success(artefact.hash)
            step.stdout = metadata.get('stdout', '')
            step.stderr = metadata.get('stderr', '')
            step.save(update_fields=['stdout', 'stderr'])
            
            # 6. Enregistrement dans output_artefacts du run
            run.output_artefacts[step.node_id] = artefact.hash
            run.save(update_fields=['output_artefacts'])
            
            logger.info(
                f"✅ Step completed: {step.node_id} -> {artefact.hash[:8]}"
            )
        
        except SandboxExecutionError as e:
            error_msg = f"Sandbox execution failed: {e}"
            step.mark_failed(error_msg)
            logger.error(error_msg)
            raise
        
        except Exception as e:
            error_msg = f"Step execution error: {e}"
            step.mark_failed(error_msg)
            logger.error(error_msg, exc_info=True)
            raise
    
    def _resolve_inputs(
        self,
        run: PipelineRun,
        step: StepRun
    ) -> Dict[str, Any]:
        """
        Résout les inputs d'un step depuis les artefacts des étapes précédentes.
        
        Workflow :
        1. Récupère les edges entrants du node
        2. Pour chaque edge, récupère l'artefact produit par le node source
        3. Désérialise les artefacts
        4. Combine avec les inputs du manifest
        
        Args:
            run: PipelineRun
            step: StepRun
        
        Returns:
            Dictionnaire des inputs résolus
        """
        inputs = {}
        
        # 1. Inputs depuis le manifest (fournis par l'utilisateur)
        node_id = step.node_id
        if node_id in run.input_manifest:
            inputs.update(run.input_manifest[node_id])
        
        # 2. Inputs depuis les artefacts des étapes précédentes
        graph = run.pipeline.graph
        edges = graph.get('edges', [])
        
        for edge in edges:
            if edge['to'] == node_id:
                # Récupère l'artefact du node source
                source_node_id = edge['from']
                
                if source_node_id in run.output_artefacts:
                    artefact_hash = run.output_artefacts[source_node_id]
                    
                    # Chargement de l'artefact
                    try:
                        artefact_obj = artefact_service.load_artefact(
                            artefact_hash,
                            log_access=False
                        )
                        
                        # Mapping du port de sortie vers port d'entrée
                        in_port = edge.get('in_port', 'input')
                        inputs[in_port] = artefact_obj
                        
                    except Exception as e:
                        logger.error(
                            f"Failed to load artefact {artefact_hash}: {e}"
                        )
                        raise

        log = {
            "node_id": node_id,
            "input": inputs
        }
        
        return inputs
    
    def cancel_run(self, run_id: str) -> PipelineRun:
        """
        Annule une exécution en cours.
        
        Note: En mode synchrone, l'annulation est difficile (thread bloqué).
        En mode asynchrone (Celery), on peut révoquer les tasks.
        
        Args:
            run_id: UUID du PipelineRun
        
        Returns:
            PipelineRun mis à jour
        """
        run = PipelineRun.objects.get(id=run_id)
        
        if run.status not in ['PENDING', 'RUNNING']:
            raise ValueError(f"Cannot cancel run in status {run.status}")
        
        # Annulation des steps en cours
        run.step_runs.filter(status='PENDING').update(status='SKIPPED')
        run.step_runs.filter(status='RUNNING').update(status='FAILED')
        
        run.mark_cancelled()
        
        logger.info(f"🚫 Run cancelled: {run.id}")
        
        return run


# Instance globale
execution_service = ExecutionService()