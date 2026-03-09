/**
 * Input Module
 * Manages chat input field behavior
 */

// Initialize namespace
window.NotionAI = window.NotionAI || {};
window.NotionAI.UI = window.NotionAI.UI || {};

window.NotionAI.UI.Input = {
    /**
     * Auto-resizes textarea based on content
     */
    autoResize() {
        const input = document.getElementById('chatInput');
        input.style.height = '56px'; // Reset to default
        const scrollHeight = input.scrollHeight;
        // Max height approx 6 lines (144px)
        input.style.height = Math.min(scrollHeight, 144) + 'px';
    },

    /**
     * Handles keyboard input
     * @param {KeyboardEvent} e - Keyboard event
     * @param {Function} onSend - Callback when send is triggered
     */
    handleKeydown(e, onSend) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            onSend();
        }
    },

    /**
     * Clears input and resets height
     */
    clear() {
        const input = document.getElementById('chatInput');
        input.value = '';
        this.autoResize();
    },

    /**
     * Focuses input field
     */
    focus() {
        const input = document.getElementById('chatInput');
        input.focus();
    },

    /**
     * Gets input value
     * @returns {string} Input text
     */
    getValue() {
        const input = document.getElementById('chatInput');
        return input.value.trim();
    },

    /**
     * Enables input
     */
    enable() {
        const input = document.getElementById('chatInput');
        const sendBtn = document.getElementById('sendBtn');
        input.disabled = false;
        sendBtn.disabled = false;
    },

    /**
     * Disables input
     */
    disable() {
        const input = document.getElementById('chatInput');
        const sendBtn = document.getElementById('sendBtn');
        input.disabled = true;
        sendBtn.disabled = true;
    }
};
