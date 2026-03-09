/**
 * Sidebar Module
 * Controls sidebar visibility on mobile and desktop
 */

// Initialize namespace
window.NotionAI = window.NotionAI || {};
window.NotionAI.UI = window.NotionAI.UI || {};

window.NotionAI.UI.Sidebar = {
    /**
     * Toggles sidebar visibility
     * @param {boolean} show - Whether to show or hide sidebar
     */
    toggle(show) {
        const sidebar = document.getElementById('sidebar');
        const backdrop = document.getElementById('mobileBackdrop');

        if (show) {
            sidebar.classList.remove('-translate-x-full');
            backdrop.classList.remove('hidden');
            setTimeout(() => backdrop.classList.add('opacity-100'), 10);
        } else {
            sidebar.classList.add('-translate-x-full');
            backdrop.classList.remove('opacity-100');
            setTimeout(() => backdrop.classList.add('hidden'), 300);
        }
    },

    /**
     * Opens sidebar
     */
    open() {
        this.toggle(true);
    },

    /**
     * Closes sidebar
     */
    close() {
        this.toggle(false);
    }
};
