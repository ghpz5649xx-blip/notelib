// static/js/pipelines.js
/**
 * Gestion des pipelines frontend
 */

const PipelinesManager = (function() {
    'use strict';

    let pipelines = [];
    let currentPipeline = null;

    /**
     * Charge la liste des pipelines
     */
    async function loadPipelines() {
        const data = await NoteLibAPI.get('/api/pipelines/');
        if (data) {
            pipelines = data.results || data;
            renderPipelineList();
        }
    }

    /**
     * Affiche la liste des pipelines
     */
    function renderPipelineList() {
        const container = document.getElementById('pipelines-list');
        if (!container) return;

        if (pipelines.length === 0) {
            container.innerHTML = `
                <div class="text-center py-5">
                    <i class="bi bi-inbox" style="font-size: 3rem; color: #6c757d;"></i>
                    <p class="text-muted mt-3">Aucun pipeline</p>
                    <button class="btn btn-primary" onclick="PipelinesManager.showCreateModal()">
                        <i class="bi bi-plus-lg"></i> Créer un pipeline
                    </button>
                </div>
            `;
            return;
        }

        const searchInput = document.getElementById('search-pipeline');
        const searchTerm = searchInput ? searchInput.value.toLowerCase() : '';

        const filtered = pipelines.filter(p => 
            p.name.toLowerCase().includes(searchTerm) ||
            (p.description && p.description.toLowerCase().includes(searchTerm))
        );

        container.innerHTML = `
            <table class="table table-striped table-hover">
                <thead>
                    <tr>
                        <th>Nom</th>
                        <th>Description</th>
                        <th>Nodes</th>
                        <th>Statut</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${filtered.map(p => `
                        <tr>
                            <td><strong>${escapeHTML(p.name)}</strong></td>
                            <td><small class="text-muted">${escapeHTML(p.description || '-')}</small></td>
                            <td><span class="badge bg-info">${p.node_count || 0}</span></td>
                            <td>
                                ${p.is_valid 
                                    ? '<span class="badge bg-success">Valide</span>' 
                                    : '<span class="badge bg-danger">Invalide</span>'}
                                ${p.is_active 
                                    ? '<span class="badge bg-primary">Actif</span>' 
                                    : '<span class="badge bg-secondary">Inactif</span>'}
                            </td>
                            <td>
                                <div class="btn-group btn-group-sm">
                                    <a href="/pipelines/${p.id}/" class="btn btn-outline-primary" title="Voir">
                                        <i class="bi bi-eye"></i>
                                    </a>
                                    <a href="/pipelines/${p.id}/edit/" class="btn btn-outline-secondary" title="Éditer">
                                        <i class="bi bi-pencil"></i>
                                    </a>
                                    <button class="btn btn-outline-success" onclick="PipelinesManager.executePipeline('${p.id}')" title="Exécuter">
                                        <i class="bi bi-play"></i>
                                    </button>
                                    <button class="btn btn-outline-info" onclick="PipelinesManager.duplicatePipeline('${p.id}')" title="Dupliquer">
                                        <i class="bi bi-files"></i>
                                    </button>
                                    <button class="btn btn-outline-danger" onclick="PipelinesManager.deletePipeline('${p.id}')" title="Supprimer">
                                        <i class="bi bi-trash"></i>
                                    </button>
                                </div>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    }

    /**
     * Affiche la modale de création
     */
    function showCreateModal() {
        const modal = new bootstrap.Modal(document.getElementById('createPipelineModal'));
        modal.show();
    }

    /**
     * Crée un nouveau pipeline
     */
    async function createPipeline(event) {
        event.preventDefault();
        
        const form = event.target;
        const data = {
            name: form.name.value,
            description: form.description.value,
            graph: { nodes: [], edges: [] }
        };

        const result = await NoteLibAPI.post('/api/pipelines/', data);
        if (result) {
            bootstrap.Modal.getInstance(document.getElementById('createPipelineModal')).hide();
            form.reset();
            window.location.href = `/pipelines/${result.id}/edit/`;
        }
    }

    /**
     * Exécute un pipeline
     */
    async function executePipeline(pipelineId) {
        if (!confirm('Lancer l\'exécution de ce pipeline ?')) return;

        const result = await NoteLibAPI.post(`/api/pipelines/${pipelineId}/runs/`, {
            input_manifest: {},
            execution_mode: 'async'
        });

        if (result) {
            alert('Exécution lancée avec succès');
            window.location.href = `/runs/${result.id}/`;
        }
    }

    /**
     * Duplique un pipeline
     */
    async function duplicatePipeline(pipelineId) {
        const name = prompt('Nom de la copie:');
        if (!name) return;

        const result = await NoteLibAPI.post(`/api/pipelines/${pipelineId}/duplicate/`, { name });
        if (result) {
            alert('Pipeline dupliqué');
            loadPipelines();
        }
    }

    /**
     * Supprime un pipeline
     */
    async function deletePipeline(pipelineId) {
        if (!confirm('Supprimer ce pipeline ?')) return;

        const result = await NoteLibAPI.del(`/api/pipelines/${pipelineId}/`);
        if (result !== null) {
            alert('Pipeline supprimé');
            loadPipelines();
        }
    }

    /**
     * Échappe le HTML
     */
    function escapeHTML(str) {
        const div = document.createElement('div');
        div.textContent = str || '';
        return div.innerHTML;
    }

    // API publique
    return {
        init() {
            loadPipelines();

            // Recherche
            const searchInput = document.getElementById('search-pipeline');
            if (searchInput) {
                searchInput.addEventListener('input', renderPipelineList);
            }

            // Form création
            const createForm = document.getElementById('create-pipeline-form');
            if (createForm) {
                createForm.addEventListener('submit', createPipeline);
            }
        },
        showCreateModal,
        executePipeline,
        duplicatePipeline,
        deletePipeline,
        loadPipelines
    };
})();

// Auto-init si on est sur la page liste
if (document.getElementById('pipelines-list')) {
    document.addEventListener('DOMContentLoaded', () => PipelinesManager.init());
}