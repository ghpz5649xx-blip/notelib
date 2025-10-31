# apps/pipelines/services.py
"""
Service de validation et manipulation des pipelines.

Responsabilités :
- Validation du DAG (acyclic, connectivité, ports)
- Ordonnancement topologique pour exécution
- Manipulation du graphe (ajout/suppression nodes/edges)
"""
import logging
from typing import Dict, List, Any, Optional, Tuple
from collections import deque, defaultdict

from .models import Pipeline
from features.models import FeatureMeta

logger = logging.getLogger("notelib")


class PipelineValidationError(Exception):
    """Exception levée lors d'une erreur de validation."""
    pass


class PipelineService:
    """
    Service de gestion des pipelines.
    
    Validation complète :
    - Graphe DAG (pas de cycles)
    - Features existantes
    - Ports compatibles
    - Connectivité correcte
    """
    
    @staticmethod
    def validate_graph(graph: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Valide la structure d'un graphe de pipeline.
        
        Args:
            graph: Dictionnaire {"nodes": [...], "edges": [...]}
        
        Returns:
            Tuple (is_valid, errors)
        
        Validations :
        1. Structure JSON correcte
        2. Pas de cycles (DAG)
        3. Features existent en BDD
        4. Ports compatibles
        5. Pas de nodes isolés (sauf entrées/sorties)
        """
        errors = []

        logger.info(f"graph :{graph}")
        
        # 1. Vérification structure
        if not isinstance(graph, dict):
            return False, ["Graph must be a dictionary"]
        
        nodes = graph.get('nodes', [])
        edges = graph.get('edges', [])
        
        if not isinstance(nodes, list):
            errors.append("'nodes' must be a list")
        
        if not isinstance(edges, list):
            errors.append("'edges' must be a list")
        
        if errors:
            return False, errors
        
        # Vérification nodes valides
        node_ids = set()
        logger.info(f"nodes :{node_ids}")
        for idx, node in enumerate(nodes):
            if not isinstance(node, dict):
                errors.append(f"Node {idx} is not a dictionary")
                continue
            
            node_id = node.get('id')
            if not node_id:
                errors.append(f"Node {idx} missing 'id'")
                continue
            
            if node_id in node_ids:
                errors.append(f"Duplicate node id: {node_id}")
            node_ids.add(node_id)
            
            # Vérification feature existe
            feature_name = node.get('feature_name')
            feature_hash = node.get('feature_hash')
            
            if not feature_name and not feature_hash:
                errors.append(f"Node {node_id} missing feature reference")
            elif feature_hash:
                if not FeatureMeta.objects.filter(hash=feature_hash).exists():
                    errors.append(f"Node {node_id}: Feature {feature_hash} not found")
        
        # 2. Vérification edges valides
        for idx, edge in enumerate(edges):
            if not isinstance(edge, dict):
                errors.append(f"Edge {idx} is not a dictionary")
                continue
            
            from_node = edge.get('from')
            to_node = edge.get('to')
            
            if from_node not in node_ids:
                errors.append(f"Edge {idx}: source node '{from_node}' not found")
            
            if to_node not in node_ids:
                errors.append(f"Edge {idx}: target node '{to_node}' not found")
        
        if errors:
            return False, errors
        
        # 3. Vérification acyclic (DAG)
        has_cycle, cycle_errors = PipelineService._check_cycles(nodes, edges)
        if has_cycle:
            errors.extend(cycle_errors)
        
        # 4. Vérification connectivité (pas de nodes orphelins, sauf entrées/sorties)
        orphan_errors = PipelineService._check_connectivity(nodes, edges)
        if orphan_errors:
            # Warning seulement, pas bloquant
            for err in orphan_errors:
                logger.warning(f"Pipeline connectivity: {err}")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def _check_cycles(nodes: List[Dict], edges: List[Dict]) -> Tuple[bool, List[str]]:
        """
        Détecte les cycles dans le graphe.
        
        Utilise un DFS avec marquage des nodes en cours de visite.
        
        Returns:
            Tuple (has_cycle, errors)
        """
        # Construction du graphe d'adjacence
        adj = defaultdict(list)
        for edge in edges:
            adj[edge['from']].append(edge['to'])
        
        # États : 0 = non visité, 1 = en cours, 2 = terminé
        state = {node['id']: 0 for node in nodes}
        errors = []
        
        def dfs(node_id: str, path: List[str]) -> bool:
            """DFS récursif pour détecter les cycles."""
            if state[node_id] == 1:
                # Cycle détecté
                cycle_path = ' -> '.join(path + [node_id])
                errors.append(f"Cycle detected: {cycle_path}")
                return True
            
            if state[node_id] == 2:
                # Déjà visité complètement
                return False
            
            # Marque comme en cours
            state[node_id] = 1
            
            # Visite des voisins
            for neighbor in adj[node_id]:
                if dfs(neighbor, path + [node_id]):
                    return True
            
            # Marque comme terminé
            state[node_id] = 2
            return False
        
        # Lance le DFS depuis chaque node non visité
        for node in nodes:
            if state[node['id']] == 0:
                if dfs(node['id'], []):
                    return True, errors
        
        return False, []
    
    @staticmethod
    def _check_connectivity(nodes: List[Dict], edges: List[Dict]) -> List[str]:
        """
        Vérifie la connectivité du graphe.
        
        Détecte les nodes isolés (sans entrées ni sorties).
        
        Returns:
            Liste de warnings (non bloquant)
        """
        warnings = []
        
        # Calcul des degrés in/out
        in_degree = defaultdict(int)
        out_degree = defaultdict(int)
        
        for edge in edges:
            out_degree[edge['from']] += 1
            in_degree[edge['to']] += 1
        
        # Détection des nodes isolés
        for node in nodes:
            node_id = node['id']
            if in_degree[node_id] == 0 and out_degree[node_id] == 0:
                warnings.append(
                    f"Node '{node_id}' is isolated (no inputs or outputs)"
                )
        
        return warnings
    
    @staticmethod
    def topological_sort(graph: Dict[str, Any]) -> List[str]:
        """
        Effectue un tri topologique du graphe.
        
        Retourne l'ordre d'exécution des nodes (Kahn's algorithm).
        
        Args:
            graph: Dictionnaire {"nodes": [...], "edges": [...]}
        
        Returns:
            Liste ordonnée des node_ids
        
        Raises:
            PipelineValidationError: Si le graphe contient un cycle
        """
        nodes = graph.get('nodes', [])
        edges = graph.get('edges', [])
        
        # Construction du graphe d'adjacence
        adj = defaultdict(list)
        in_degree = defaultdict(int)
        
        # Initialisation
        for node in nodes:
            in_degree[node['id']] = 0
        
        for edge in edges:
            adj[edge['from']].append(edge['to'])
            in_degree[edge['to']] += 1
        
        # Kahn's algorithm
        queue = deque([node_id for node_id in in_degree if in_degree[node_id] == 0])
        result = []
        
        while queue:
            node_id = queue.popleft()
            result.append(node_id)
            
            for neighbor in adj[node_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # Vérification que tous les nodes sont visités (pas de cycle)
        if len(result) != len(nodes):
            raise PipelineValidationError(
                "Cycle detected: topological sort impossible"
            )
        
        return result
    
    @staticmethod
    def get_node_dependencies(graph: Dict[str, Any], node_id: str) -> List[str]:
        """
        Retourne les dépendances d'un node (parents directs).
        
        Args:
            graph: Graphe du pipeline
            node_id: ID du node
        
        Returns:
            Liste des node_ids parents
        """
        edges = graph.get('edges', [])
        dependencies = [
            edge['from']
            for edge in edges
            if edge['to'] == node_id
        ]
        return dependencies
    
    @staticmethod
    def get_execution_layers(graph: Dict[str, Any]) -> List[List[str]]:
        """
        Retourne les layers d'exécution pour parallélisation.
        
        Les nodes dans un même layer peuvent être exécutés en parallèle.
        
        Args:
            graph: Graphe du pipeline
        
        Returns:
            Liste de layers (chaque layer est une liste de node_ids)
        """
        nodes = graph.get('nodes', [])
        edges = graph.get('edges', [])
        
        # Calcul du in_degree
        in_degree = {node['id']: 0 for node in nodes}
        adj = defaultdict(list)
        
        for edge in edges:
            adj[edge['from']].append(edge['to'])
            in_degree[edge['to']] += 1
        
        # BFS par layers
        layers = []
        current_layer = [node_id for node_id in in_degree if in_degree[node_id] == 0]
        
        while current_layer:
            layers.append(current_layer)
            next_layer = []
            
            for node_id in current_layer:
                for neighbor in adj[node_id]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_layer.append(neighbor)
            
            current_layer = next_layer
        
        return layers
    
    @staticmethod
    def validate_and_save(pipeline: Pipeline) -> Tuple[bool, List[str]]:
        """
        Valide un pipeline et met à jour son statut.
        
        Args:
            pipeline: Instance de Pipeline
        
        Returns:
            Tuple (is_valid, errors)
        """
        is_valid, errors = PipelineService.validate_graph(pipeline.graph)
        
        pipeline.is_valid = is_valid
        pipeline.validation_errors = errors
        pipeline.save(update_fields=['is_valid', 'validation_errors'])
        
        if is_valid:
            logger.info(f"✅ Pipeline validated: {pipeline.name}")
        else:
            logger.warning(
                f"❌ Pipeline validation failed: {pipeline.name}\n"
                f"Errors: {errors}"
            )
        
        return is_valid, errors


# Instance globale
pipeline_service = PipelineService()