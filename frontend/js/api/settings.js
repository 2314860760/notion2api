/**
 * Settings Module
 * Handles API configuration and settings management
 */

// Initialize namespace
window.NotionAI = window.NotionAI || {};
window.NotionAI.API = window.NotionAI.API || {};

window.NotionAI.API.Settings = {
    /**
     * Opens the settings modal
     */
    open() {
        const baseUrl = window.NotionAI.Core.State.get('baseUrl');
        const apiKey = window.NotionAI.Core.State.get('apiKey');

        document.getElementById('baseUrlInput').value = baseUrl;
        document.getElementById('apiKeyInput').value = apiKey;

        const modal = document.getElementById('settingsModal');
        const content = document.getElementById('settingsModalContent');

        modal.classList.remove('pointer-events-none');
        modal.classList.add('opacity-100');
        content.classList.remove('scale-95');
        content.classList.add('scale-100');
    },

    /**
     * Closes the settings modal
     */
    close() {
        const modal = document.getElementById('settingsModal');
        const content = document.getElementById('settingsModalContent');

        modal.classList.remove('opacity-100');
        content.classList.remove('scale-100');
        content.classList.add('scale-95');

        setTimeout(() => {
            modal.classList.add('pointer-events-none');
        }, 200);
    },

    /**
     * Saves settings from modal inputs
     */
    save() {
        const baseUrlInput = document.getElementById('baseUrlInput');
        const apiKeyInput = document.getElementById('apiKeyInput');

        const baseUrl = baseUrlInput.value.trim().replace(/\/$/, "");
        const apiKey = apiKeyInput.value.trim();

        window.NotionAI.Core.State.set('baseUrl', baseUrl);
        window.NotionAI.Core.State.set('apiKey', apiKey);

        localStorage.setItem('claude_base_url', baseUrl);
        window.NotionAI.Core.State.persistApiKey(apiKey);

        this.close();
        window.NotionAI.API.Models.loadModels();
    }
};
