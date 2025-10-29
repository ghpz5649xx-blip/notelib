# ============================================================
# apps/executions/tasks.py (Celery tasks pour exécution asynchrone)
# ============================================================
"""
Tâches Celery pour l'exécution asynchrone des pipelines.

Installation Celery :
pip install celery redis

Configuration dans settings.py :
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'

Lancement du worker :
celery -A notelib worker --loglevel=info
"""

import logging

logger = logging.getLogger("notelib")



def start_pipeline_run(self, run_id: str):
    """
    Tâche master : démarre l'exécution d'un pipeline.
    
    Workflow :
    1. Calcul du tri topologique
    2. Planification des step tasks selon les layers (parallélisation)
    3. Monitoring et consolidation des résultats
    
    Args:
        run_id: UUID du PipelineRun
    """
    from .models import PipelineRun
    from .services import execution_service
    from pipelines.services import pipeline_service
    
    try:
        run = PipelineRun.objects.select_related('pipeline').get(id=run_id)
        run.mark_running()
        
        logger.info(f"🚀 Starting async execution: {run.id}")
        
        # Calcul des layers pour parallélisation
        layers = pipeline_service.get_execution_layers(run.pipeline.graph)
        
        # Planification des tasks par layer
        for layer_idx, node_ids in enumerate(layers):
            logger.info(f"Layer {layer_idx}: {len(node_ids)} steps")
            
            # Exécution parallèle des steps du layer
            tasks = (
                execute_step.s(run_id, node_id)
                for node_id in node_ids
            )
            tasks.apply_async()
        
        # Note: La consolidation finale est gérée par execute_step
        # via un callback ou polling
        
        return {'status': 'started', 'run_id': run_id}
    
    except Exception as e:
        logger.error(f"Failed to start pipeline run {run_id}: {e}", exc_info=True)
        try:
            run = PipelineRun.objects.get(id=run_id)
            run.mark_failed(str(e))
        except:
            pass
        raise


def execute_step(self, run_id: str, node_id: str):
    """
    Tâche worker : exécute un StepRun individuel.
    
    Args:
        run_id: UUID du PipelineRun
        node_id: ID du node à exécuter
    """
    from .models import PipelineRun, StepRun
    from .services import execution_service
    
    try:
        run = PipelineRun.objects.get(id=run_id)
        step = StepRun.objects.get(pipeline_run=run, node_id=node_id)
        
        logger.info(f"▶️  Executing step (async): {node_id}")
        
        # Vérification des dépendances (les steps parents doivent être SUCCESS)
        dependencies = execution_service._get_dependencies(run, step)
        for dep_node_id in dependencies:
            dep_step = StepRun.objects.get(pipeline_run=run, node_id=dep_node_id)
            if dep_step.status != 'SUCCESS':
                logger.warning(
                    f"Dependency not satisfied: {dep_node_id} "
                    f"(status={dep_step.status})"
                )
                step.mark_skipped()
                return {'status': 'skipped', 'reason': 'dependency_failed'}
        
        # Exécution
        execution_service._execute_step(run, step)
        
        # Vérification si tous les steps sont terminés
        finalize_run_if_complete.delay(run_id)
        
        return {'status': 'success', 'node_id': node_id}
    
    except Exception as e:
        logger.error(f"Step execution failed: {node_id} - {e}", exc_info=True)
        
        # Retry si possible
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60)
        
        # Marque comme failed
        try:
            step = StepRun.objects.get(pipeline_run_id=run_id, node_id=node_id)
            step.mark_failed(str(e))
        except:
            pass
        
        return {'status': 'failed', 'error': str(e)}


def finalize_run_if_complete(run_id: str):
    """
    Vérifie si tous les steps sont terminés et finalise le run.
    
    Args:
        run_id: UUID du PipelineRun
    """
    from .models import PipelineRun
    
    try:
        run = PipelineRun.objects.get(id=run_id)
        
        # Vérification des statuts
        pending = run.step_runs.filter(status='PENDING').count()
        running = run.step_runs.filter(status='RUNNING').count()
        
        if pending > 0 or running > 0:
            # Pas encore terminé
            return {'status': 'incomplete'}
        
        # Tous les steps sont terminés
        failed = run.step_runs.filter(status='FAILED').count()
        success = run.step_runs.filter(status='SUCCESS').count()
        
        if failed > 0:
            run.mark_failed(f"{failed} step(s) failed, {success} succeeded")
        else:
            run.mark_success()
            logger.info(f"✅ Pipeline execution completed: {run.id}")
        
        return {'status': 'finalized', 'result': run.status}
    
    except Exception as e:
        logger.error(f"Failed to finalize run {run_id}: {e}", exc_info=True)
        return {'status': 'error', 'error': str(e)}

