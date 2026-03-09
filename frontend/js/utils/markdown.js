/**
 * Markdown Module
 * Handles safe markdown rendering using Marked.js and DOMPurify
 */

// Initialize namespace
window.NotionAI = window.NotionAI || {};
window.NotionAI.Utils = window.NotionAI.Utils || {};

window.NotionAI.Utils.Markdown = {
    /**
     * Renders markdown to safe HTML
     * @param {string} markdown - Raw markdown string
     * @returns {string} Sanitized HTML
     */
    renderToSafeHtml(markdown) {
        const renderedHtml = marked.parse(markdown || '');
        return DOMPurify.sanitize(renderedHtml, {
            USE_PROFILES: { html: true },
            ADD_ATTR: ['target', 'rel']
        });
    },

    /**
     * Sets safe markdown content to a container element
     * @param {HTMLElement} container - Target DOM element
     * @param {string} markdown - Raw markdown string
     */
    setSafeMarkdown(container, markdown) {
        container.innerHTML = this.renderToSafeHtml(markdown);
    }
};
