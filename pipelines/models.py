# apps/pipelines/models.py
"""
Modèles pour la gestion des pipelines.

Un pipeline est un graphe dirigé acyclique (DAG) composé de :
- Nodes : représentent des features
- Edges : représentent les flux de données (artefacts) entre nodes

Le graphe est stocké en JSON pour faciliter l'édition UI.
"""
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone


class Pipeline(models.Model):
    """
    Représente un pipeline d'exécution.
    
    Un pipeline définit un workflow composable de features.
    Le graphe est stocké en JSON avec la structure :
    {
        "nodes": [
            {
                "id": "node_1",
                "feature_name": "load_data",
                "feature_hash": "abc123...",
                "config": {"param1": "value1"},
                "ports_in": ["input"],
                "ports_out": ["output"],
                "ui": {"x": 100, "y": 200}
            }
        ],
        "edges": [
            {
                "id": "edge_1",
                "from": "node_1",
                "to": "node_2",
                "out_port": "output",
                "in_port": "input"
            }
        ]
    }
    """
    
    # Identification
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    name = models.CharField(
        max_length=255,
        help_text="Nom descriptif du pipeline"
    )
    
    description = models.TextField(
        blank=True,
        help_text="Description du workflow"
    )
    
    # Ownership
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='pipelines',
        help_text="Propriétaire du pipeline"
    )
    
    # Structure du graphe
    graph = models.JSONField(
        default=dict,
        help_text="Représentation JSON du DAG (nodes + edges)"
    )
    
    # Statut
    is_active = models.BooleanField(
        default=True,
        help_text="Si False, le pipeline ne peut pas être exécuté"
    )
    
    is_valid = models.BooleanField(
        default=False,
        help_text="True si le graphe passe la validation (acyclic, ports compatibles)"
    )
    
    validation_errors = models.JSONField(
        default=list,
        help_text="Liste des erreurs de validation"
    )
    
    # Métadonnées
    version = models.IntegerField(
        default=1,
        help_text="Version du pipeline (incrémenté à chaque modification)"
    )
    
    tags = models.JSONField(
        default=list,
        help_text="Tags pour catégorisation"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Pipeline'
        verbose_name_plural = 'Pipelines'
        indexes = [
            models.Index(fields=['-updated_at']),
            models.Index(fields=['owner', '-updated_at']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} (v{self.version})"
    
    def save(self, *args, **kwargs):
        """Override save pour valider le graphe automatiquement."""
        # Validation automatique si le graphe a changé
        if self.pk and Pipeline.objects.filter(pk=self.pk).exists():
            old_instance = Pipeline.objects.get(pk=self.pk)
            if old_instance.graph != self.graph:
                self.version += 1
                # La validation sera faite par le service
        
        super().save(*args, **kwargs)
    
    def get_node_count(self) -> int:
        """Retourne le nombre de nodes."""
        return len(self.graph.get('nodes', []))
    
    def get_edge_count(self) -> int:
        """Retourne le nombre d'edges."""
        return len(self.graph.get('edges', []))
    
    def get_nodes(self) -> list:
        """Retourne la liste des nodes."""
        return self.graph.get('nodes', [])
    
    def get_edges(self) -> list:
        """Retourne la liste des edges."""
        return self.graph.get('edges', [])
    
    def get_node_by_id(self, node_id: str):
        """Récupère un node par son ID."""
        for node in self.get_nodes():
            if node.get('id') == node_id:
                return node
        return None


class PipelineTemplate(models.Model):
    """
    Template de pipeline réutilisable.
    
    Permet de partager des patterns courants entre utilisateurs.
    """
    
    name = models.CharField(max_length=255)
    description = models.TextField()
    graph_template = models.JSONField(
        help_text="Structure du graphe (sans values concrètes)"
    )
    
    # Visibilité
    is_public = models.BooleanField(
        default=False,
        help_text="Si True, visible par tous les utilisateurs"
    )
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='pipeline_templates'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    usage_count = models.IntegerField(
        default=0,
        help_text="Nombre de fois utilisé"
    )
    
    class Meta:
        ordering = ['-usage_count', '-created_at']
        verbose_name = 'Template Pipeline'
        verbose_name_plural = 'Templates Pipeline'
    
    def __str__(self):
        return self.name
    
    def instantiate(self, owner: User, name: str) -> Pipeline:
        """Crée un pipeline depuis ce template."""
        pipeline = Pipeline.objects.create(
            name=name,
            description=f"Créé depuis le template '{self.name}'",
            owner=owner,
            graph=self.graph_template.copy(),
        )
        
        # Incrémente le compteur d'usage
        self.usage_count += 1
        self.save(update_fields=['usage_count'])
        
        return pipeline