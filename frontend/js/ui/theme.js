/**
 * Theme Module
 * Handles dark/light theme switching
 */

// Initialize namespace
window.NotionAI = window.NotionAI || {};
window.NotionAI.UI = window.NotionAI.UI || {};

window.NotionAI.UI.Theme = {
    /**
     * Toggles between dark and light theme
     */
    toggle() {
        const currentTheme = window.NotionAI.Core.State.get('theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

        window.NotionAI.Core.State.set('theme', newTheme);
        localStorage.setItem('theme', newTheme);

        this.apply(newTheme);
    },

    /**
     * Applies theme to the document
     * @param {string} theme - Theme name ('dark' or 'light')
     */
    apply(theme) {
        const html = document.documentElement;
        const sunIcon = document.getElementById('sunIcon');
        const moonIcon = document.getElementById('moonIcon');

        if (theme === 'dark') {
            html.classList.add('dark');
            sunIcon.classList.remove('hidden');
            moonIcon.classList.add('hidden');
        } else {
            html.classList.remove('dark');
            sunIcon.classList.add('hidden');
            moonIcon.classList.remove('hidden');
        }
    },

    /**
     * Initializes theme on app load
     */
    init() {
        const theme = window.NotionAI.Core.State.get('theme');
        this.apply(theme);
    }
};
