/**
 * Modal Module
 * Manages modal dialogs (settings, rename, etc.)
 */

// Initialize namespace
window.NotionAI = window.NotionAI || {};
window.NotionAI.UI = window.NotionAI.UI || {};

window.NotionAI.UI.Modal = {
    /**
     * Opens rename modal for a chat
     * @param {string} chatId - ID of chat to rename
     */
    openRenameModal(chatId) {
        const chats = window.NotionAI.Core.State.get('chats');
        const chat = chats.find(c => c.id === chatId);
        if (!chat) return;

        window.NotionAI.Core.State.set('chatToRename', chatId);

        const modal = document.getElementById('renameModal');
        const content = document.getElementById('renameModalContent');
        const input = document.getElementById('renameModalInput');

        input.value = chat.title;
        modal.classList.remove('opacity-0', 'pointer-events-none');
        content.classList.remove('scale-95');
        input.focus();
    },

    /**
     * Closes rename modal
     */
    closeRenameModal() {
        const modal = document.getElementById('renameModal');
        const content = document.getElementById('renameModalContent');

        modal.classList.add('opacity-0', 'pointer-events-none');
        content.classList.add('scale-95');
        window.NotionAI.Core.State.set('chatToRename', null);
    },

    /**
     * Saves chat rename
     */
    saveRename() {
        const chatId = window.NotionAI.Core.State.get('chatToRename');
        if (!chatId) return;

        const input = document.getElementById('renameModalInput');
        const newTitle = input.value.trim();

        if (newTitle) {
            window.NotionAI.Chat.Storage.updateChatTitle(chatId, newTitle);

            const currentChatId = window.NotionAI.Core.State.get('currentChatId');
            if (currentChatId === chatId) {
                document.getElementById('headerTitle').textContent = newTitle;
            }
        }

        this.closeRenameModal();
    }
};
