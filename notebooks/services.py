import logging
import hashlib
import time
from pathlib import Path
from typing import Dict, Any
from django.db import transaction
from django.utils import timezone

from .models import NotebookMeta, NotebookExecution, NotebookFeature
from server.models import FeatureMeta
from notelib_core.loader import load_notebook_features

logger = logging.getLogger("notelib")


class NotebookService:
    """
    Service orchestrant le traitement des notebooks.
    
    Responsabilités :
    - Upload et validation des notebooks
    - Traitement et extraction des features
    - Mise à jour du statut et des métadonnées
    - Création optionnelle d'articles wiki
    """
    
    @staticmethod
    def compute_hash(file_path: Path) -> str:
        """Calcule le hash SHA-256 d'un fichier."""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    @staticmethod
    def process_notebook(
        notebook: NotebookMeta,
        sandbox_mode: str = "temp",
        create_wiki_article: bool = False
    ) -> NotebookExecution:
        """
        Traite un notebook : extraction des features et mise à jour des métadonnées.
        
        Args:
            notebook: Instance de NotebookMeta
            sandbox_mode: Mode d'exécution ("strict", "temp", "none")
            create_wiki_article: Si True, crée un article wiki pour le notebook
        
        Returns:
            Instance de NotebookExecution avec les résultats
        """
        execution = NotebookExecution.objects.create(
            notebook=notebook,
            sandbox_mode=sandbox_mode,
        )
        
        start_time = time.time()
        
        try:
            # Mise à jour du statut
            notebook.status = 'processing'
            notebook.save()
            
            # Chargement du notebook
            notebook_path = Path(notebook.file.path)
            result = load_notebook_features(
                notebook_path,
                sandbox_mode=sandbox_mode,
                publish=True  # Publie vers le serveur
            )
            
            # Mise à jour des statistiques
            features = result.get('features', [])
            errors = result.get('errors', [])
            
            features_imported = 0
            features_existing = 0
            
            with transaction.atomic():
                # Enregistrement des features dans la DB
                for feature_def in features:
                    feature_meta, created = FeatureMeta.objects.get_or_create(
                        name=feature_def.name,
                        hash=feature_def.hash,
                        defaults={
                            'inputs': feature_def.inputs,
                            'outputs': feature_def.outputs,
                        }
                    )
                    
                    if created:
                        features_imported += 1
                    else:
                        features_existing += 1
                    
                    # Lien notebook → feature
                    NotebookFeature.objects.get_or_create(
                        notebook=notebook,
                        feature=feature_meta,
                        defaults={'cell_index': 0}  # TODO: extraire l'index réel
                    )
                
                # Mise à jour du notebook
                notebook.status = 'success'
                notebook.feature_count = len(features)
                notebook.processed_at = timezone.now()
                notebook.save()
            
            # Création optionnelle d'un article wiki
            if create_wiki_article and not notebook.wiki_article:
                NotebookService._create_wiki_article(notebook)
            
            # Finalisation de l'exécution
            execution.features_imported = features_imported
            execution.features_existing = features_existing
            execution.errors_count = len(errors)
            execution.execution_log = {
                'features': [f.to_dict() for f in features],
                'errors': errors,
            }
            execution.completed_at = timezone.now()
            execution.duration = time.time() - start_time
            execution.save()
            
            logger.info(
                f"✅ Notebook processed: {notebook.name} "
                f"({features_imported} imported, {features_existing} existing)"
            )
            
            return execution
            
        except Exception as e:
            # Gestion des erreurs
            notebook.status = 'error'
            notebook.error_message = str(e)
            notebook.save()
            
            execution.errors_count = 1
            execution.execution_log = {'error': str(e)}
            execution.completed_at = timezone.now()
            execution.duration = time.time() - start_time
            execution.save()
            
            logger.error(f"❌ Notebook processing failed: {notebook.name} - {e}")
            
            raise
    
    @staticmethod
    def _create_wiki_article(notebook: NotebookMeta):
        """
        Crée un article wiki pour documenter le notebook.
        
        Args:
            notebook: Instance de NotebookMeta
        """
        from wiki.models import Article, ArticleRevision, URLPath
        from django.contrib.auth.models import User
        
        try:
            # Récupération de l'utilisateur système
            system_user = notebook.uploaded_by or User.objects.first()
            
            # Création de l'article
            root = URLPath.root()
            slug = f"notebook-{notebook.id}"
            
            # Génération du contenu markdown
            content = f"""# {notebook.name}

## Informations

- **Uploadé par** : {notebook.uploaded_by.username if notebook.uploaded_by else 'Système'}
- **Date** : {notebook.uploaded_at.strftime('%d/%m/%Y %H:%M')}
- **Features** : {notebook.feature_count}
- **Statut** : {notebook.get_status_display()}

## Features extraites

"""
            for feature_link in notebook.features.all():
                feature = feature_link.feature
                content += f"- **{feature.name}** (hash: `{feature.hash[:8]}...`)\n"
            
            # Création de l'article wiki
            article = Article.objects.create()
            
            ArticleRevision.objects.create(
                article=article,
                title=notebook.name,
                content=content,
                user=system_user,
            )
            
            URLPath.objects.create(
                site_id=1,
                parent=root,
                slug=slug,
                article=article,
            )
            
            notebook.wiki_article = article
            notebook.save()
            
            logger.info(f"📝 Wiki article created for notebook: {notebook.name}")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to create wiki article: {e}")


notebook_service = NotebookService()