// static/js/notelib_api.js
/**
 * Client API REST pour NoteLib
 * 
 * Wrapper autour de fetch pour faciliter les appels REST.
 * Gère automatiquement :
 * - CSRF token
 * - Authorization header
 * - Affichage des erreurs
 */

window.NoteLibAPI = (function() {
    'use strict';

    // Configuration
    const config = {
        baseURL: window.location.origin,
        authToken: null
    };

    /**
     * Récupère le cookie CSRF
     */
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    /**
     * Affiche un message d'erreur Bootstrap
     */
    function showError(message) {
        // Cherche ou crée le conteneur d'alertes
        let alertContainer = document.getElementById('api-alerts');
        if (!alertContainer) {
            alertContainer = document.createElement('div');
            alertContainer.id = 'api-alerts';
            alertContainer.style.position = 'fixed';
            alertContainer.style.top = '80px';
            alertContainer.style.right = '20px';
            alertContainer.style.zIndex = '9999';
            alertContainer.style.maxWidth = '400px';
            document.body.appendChild(alertContainer);
        }

        const alert = document.createElement('div');
        alert.className = 'alert alert-danger alert-dismissible fade show';
        alert.role = 'alert';
        alert.innerHTML = `
            <strong>Erreur API:</strong> ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        alertContainer.appendChild(alert);

        // Auto-suppression après 5s
        setTimeout(() => {
            alert.classList.remove('show');
            setTimeout(() => alert.remove(), 150);
        }, 5000);

        console.error('[NoteLibAPI]', message);
    }

    /**
     * Construit les headers de la requête
     */
    function buildHeaders(options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        };

        if (config.authToken) {
            headers['Authorization'] = `Bearer ${config.authToken}`;
        }

        return { ...headers, ...options.headers };
    }

    /**
     * Effectue une requête HTTP
     */
    async function request(method, url, options = {}) {
        const fullURL = url.startsWith('http') ? url : `${config.baseURL}${url}`;

        try {
            const response = await fetch(fullURL, {
                method,
                headers: buildHeaders(options),
                body: options.body ? JSON.stringify(options.body) : undefined,
                ...options.fetchOptions
            });

            // Gestion des erreurs HTTP
            if (!response.ok) {
                let errorMessage = `HTTP ${response.status}`;
                try {
                    const errorData = await response.json();
                    errorMessage = errorData.error || errorData.detail || errorMessage;
                } catch (e) {
                    errorMessage = await response.text() || errorMessage;
                }
                
                showError(errorMessage);
                return null;
            }

            // Parse JSON si content-type est JSON
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            }

            return response;

        } catch (error) {
            showError(error.message || 'Erreur réseau');
            console.error('[NoteLibAPI] Request failed:', error);
            return null;
        }
    }

    // API publique
    return {
        /**
         * Configure le token d'authentification
         */
        setAuthToken(token) {
            config.authToken = token;
        },

        /**
         * GET request
         */
        async get(url, params = {}) {
            const queryString = new URLSearchParams(params).toString();
            const fullURL = queryString ? `${url}?${queryString}` : url;
            return request('GET', fullURL);
        },

        /**
         * POST request
         */
        async post(url, data = {}) {
            return request('POST', url, { body: data });
        },

        /**
         * PUT request
         */
        async put(url, data = {}) {
            return request('PUT', url, { body: data });
        },

        /**
         * DELETE request
         */
        async del(url) {
            return request('DELETE', url);
        },

        /**
         * Download file
         */
        async download(url, filename) {
            try {
                const response = await fetch(`${config.baseURL}${url}`, {
                    headers: buildHeaders()
                });

                if (!response.ok) {
                    showError(`Téléchargement échoué: ${response.status}`);
                    return false;
                }

                const blob = await response.blob();
                const downloadURL = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = downloadURL;
                a.download = filename || 'download';
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(downloadURL);

                return true;
            } catch (error) {
                showError('Erreur lors du téléchargement');
                console.error(error);
                return false;
            }
        }
    };
})();