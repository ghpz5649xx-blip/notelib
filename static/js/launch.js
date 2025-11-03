/**
 * Gestion de la page de lancement d’un pipeline
 */

const LaunchManager = (function() {
    'use strict';

    let pipelines = [];
    let selectedPipeline = null;
    let inputNodes = [];

    // === INIT ===
    async function init() {
        await loadPipelines();
        setupListeners();

        if (window.preselectedPipelineId) {
            console.log("Pré-sélection du pipeline:", window.preselectedPipelineId);
            document.getElementById('pipeline-select').value = window.preselectedPipelineId;
            await onPipelineSelect({ target: { value: window.preselectedPipelineId } });
        }
    }

    async function loadPipelines() {
        const data = await NoteLibAPI.get('/api/pipelines/', { is_valid: 'true', is_active: 'true' });
        if (data) {
            pipelines = data.results || data;
            renderSelect();
        }
    }

    function renderSelect() {
        const select = document.getElementById('pipeline-select');
        if (!select) return;

        if (pipelines.length === 0) {
            select.innerHTML = '<option value="">Aucun pipeline disponible</option>';
            select.disabled = true;
            return;
        }

        select.innerHTML =
            '<option value="">-- Choisir un pipeline --</option>' +
            pipelines.map(p => `<option value="${p.id}">${p.name} (v${p.version}) - ${p.node_count} nodes</option>`).join('');
    }

    function setupListeners() {
        document.getElementById('pipeline-select').addEventListener('change', onPipelineSelect);
        document.getElementById('preview-btn').addEventListener('click', previewManifest);
        document.getElementById('launch-btn').addEventListener('click', launchRun);
        document.getElementById('confirm-launch').addEventListener('click', launchRunFromPreview);
    }

    // === Sélection du pipeline ===
    async function onPipelineSelect(event) {
        const id = event.target.value;
        if (!id) return hideSections();

        selectedPipeline = await NoteLibAPI.get(`/api/pipelines/${id}/`);
        if (!selectedPipeline) {
            alert('Erreur lors du chargement du pipeline');
            return;
        }

        displayPipelineInfo();
        analyzeInputs();
        renderManifestForm();
        showSections();
    }

    function displayPipelineInfo() {
        document.getElementById('pipeline-info').classList.remove('d-none');
        document.getElementById('pipeline-description').textContent = selectedPipeline.description || '-';
        document.getElementById('pipeline-nodes').textContent = selectedPipeline.node_count;
        document.getElementById('pipeline-status').innerHTML = selectedPipeline.is_valid
            ? '<span class="badge bg-success">Valide</span>'
            : '<span class="badge bg-danger">Invalide</span>';
    }

    // === Inputs externes ===
    function analyzeInputs() {
        const nodes = selectedPipeline.graph?.nodes || [];
        const edges = selectedPipeline.graph?.edges || [];
        const targetNodes = new Set(edges.map(e => e.to));

        inputNodes = nodes.filter(n => n.ports_in && n.ports_in.length > 0 && !targetNodes.has(n.id));
    }

    function renderManifestForm() {
        const container = document.getElementById('manifest-inputs-container');
        if (inputNodes.length === 0) {
            container.innerHTML = `<div class="alert alert-success"><i class="bi bi-check-circle"></i> Aucun paramètre requis.</div>`;
            return;
        }

        container.innerHTML = inputNodes.map(node => `
            <div class="card mb-3">
                <div class="card-header"><h6 class="mb-0"><i class="bi bi-node-plus"></i> Node: <strong>${node.id}</strong></h6></div>
                <div class="card-body">
                    ${node.ports_in.map(port => `
                        <div class="mb-3">
                            <label class="form-label fw-bold">${port}</label>
                            <input type="text" class="form-control" id="input-${node.id}-${port}" required placeholder="Valeur pour ${port}">
                        </div>
                    `).join('')}
                </div>
            </div>
        `).join('');
    }

    // === Manifest ===
    function buildManifest() {
        const manifest = {};
        inputNodes.forEach(node => {
            const nodeManifest = {};
            node.ports_in.forEach(port => {
                const el = document.getElementById(`input-${node.id}-${port}`);
                if (el?.value.trim()) nodeManifest[port] = el.value.trim();
            });
            if (Object.keys(nodeManifest).length) manifest[node.id] = nodeManifest;
        });
        return manifest;
    }

    function validateManifest(m) {
        const errors = [];
        inputNodes.forEach(node => {
            node.ports_in.forEach(port => {
                if (!m[node.id]?.[port]) errors.push(`Node ${node.id}: paramètre '${port}' manquant`);
            });
        });
        return errors;
    }

    // === Preview ===
    function previewManifest() {
        const manifest = buildManifest();
        const errors = validateManifest(manifest);
        if (errors.length) return alert(errors.join('\n'));

        const payload = {
            pipeline: selectedPipeline.id,
            input_manifest: manifest,
            execution_mode: document.querySelector('input[name="execution_mode"]:checked').value,
            description: document.getElementById('run-description').value.trim() // <-- ajout
        };

        document.getElementById('preview-content').textContent = JSON.stringify(payload, null, 2);
        new bootstrap.Modal(document.getElementById('previewModal')).show();
    }

    // === Lancement ===
    async function launchRun() {
        const manifest = buildManifest();
        const errors = validateManifest(manifest);
        if (errors.length) return alert(errors.join('\n'));

        const btn = document.getElementById('launch-btn');
        btn.disabled = true;
        btn.innerHTML = '<i class="bi bi-hourglass-split"></i> Lancement...';

        try {
            const payload = {
                pipeline: selectedPipeline.id,
                input_manifest: manifest,
                execution_mode: document.querySelector('input[name="execution_mode"]:checked').value,
                description: document.getElementById('run-description').value.trim(),
            };
            const res = await NoteLibAPI.post('/api/runs/', payload);
            if (res?.id) window.location.href = `/runs/${res.id}/`;
            else throw new Error('Erreur de réponse');
        } catch (e) {
            console.error(e);
            alert("Erreur lors du lancement");
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-rocket"></i> Lancer l’exécution';
        }
    }

    async function launchRunFromPreview() {
        bootstrap.Modal.getInstance(document.getElementById('previewModal')).hide();
        await launchRun();
    }

    // === UI helpers ===
    function showSections() {
        ['manifest-section', 'execution-options-section', 'action-buttons-section'].forEach(id => document.getElementById(id).style.display = 'block');
    }

    function hideSections() {
        document.getElementById('pipeline-info').classList.add('d-none');
        ['manifest-section', 'execution-options-section', 'action-buttons-section'].forEach(id => document.getElementById(id).style.display = 'none');
        selectedPipeline = null;
        inputNodes = [];
    }

    return { init };
})();

document.addEventListener('DOMContentLoaded', LaunchManager.init);
