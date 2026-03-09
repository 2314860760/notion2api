/**
 * Chat Manager Module
 * Manages chat sessions (create, select, delete, rename)
 */

// Initialize namespace
window.NotionAI = window.NotionAI || {};
window.NotionAI.Chat = window.NotionAI.Chat || {};

window.NotionAI.Chat.Manager = {
    /**
     * Starts a new chat session
     */
    startNewChat() {
        if (window.NotionAI.Core.State.get('isGenerating')) return;

        const currentChatId = Date.now().toString();
        window.NotionAI.Core.State.set('currentChatId', currentChatId);

        // Reset UI
        document.getElementById('headerTitle').classList.add('opacity-0');
        document.getElementById('chatContainer').innerHTML = '';
        window.NotionAI.UI.Input.clear();

        // Show welcome screen
        const welcomeScreen = document.getElementById('welcomeScreen');
        welcomeScreen.classList.remove('hidden');
        void welcomeScreen.offsetWidth; // Force reflow

        // Adjust input wrapper
        const inputWrapper = document.getElementById('inputAreaWrapper');
        inputWrapper.classList.remove('chat-state-container');
        inputWrapper.classList.add('initial-state-container');

        document.getElementById('inputBgMask').classList.add('opacity-0');
        document.getElementById('inputGradientMask').classList.add('opacity-0');

        // Close sidebar on mobile
        if (window.innerWidth < 768) {
            window.NotionAI.UI.Sidebar.close();
        }

        window.NotionAI.UI.Input.focus();
        this.renderChatList();
    },

    /**
     * Selects an existing chat
     * @param {string} chatId - Chat ID to select
     */
    selectChat(chatId) {
        if (window.NotionAI.Core.State.get('isGenerating')) return;

        const chats = window.NotionAI.Core.State.get('chats');
        const chat = chats.find(c => c.id === chatId);
        if (!chat) return;

        window.NotionAI.Core.State.set('currentChatId', chatId);

        // Hide welcome, show chat
        document.getElementById('welcomeScreen').classList.add('hidden');
        document.getElementById('chatContainer').innerHTML = '';

        // Adjust input wrapper
        const inputWrapper = document.getElementById('inputAreaWrapper');
        inputWrapper.classList.remove('initial-state-container');
        inputWrapper.classList.add('chat-state-container');

        document.getElementById('inputBgMask').classList.remove('opacity-0');
        document.getElementById('inputGradientMask').classList.remove('opacity-0');

        // Set header title
        document.getElementById('headerTitle').textContent = chat.title;
        document.getElementById('headerTitle').classList.remove('opacity-0');

        // Restore messages
        chat.messages.forEach(msg => {
            const wrapper = window.NotionAI.Chat.Renderer.appendMessage(
                msg.role,
                msg.content,
                true,
                msg.modelDisplayName || null
            );

            if (msg.role === 'assistant') {
                const restoredThinking = typeof msg.thinking === 'string' ? msg.thinking : '';
                const restoredSearch = window.NotionAI.Utils.Validation.normalizeSearchPayload(msg.search);

                if (restoredThinking.trim()) {
                    wrapper.thinkingText = restoredThinking;
                    window.NotionAI.Chat.Renderer.updateThinkingPanel(wrapper);
                }

                if ((restoredSearch.queries.length + restoredSearch.sources.length) > 0) {
                    wrapper.searchData = restoredSearch;
                    window.NotionAI.Chat.Renderer.updateSearchPanel(wrapper);
                }
            }
        });

        // Close sidebar on mobile
        if (window.innerWidth < 768) {
            window.NotionAI.UI.Sidebar.close();
        }

        window.NotionAI.Utils.DOM.scrollToBottom();
        this.renderChatList();
    },

    /**
     * Deletes a chat
     * @param {string} chatId - Chat ID to delete
     */
    async deleteChat(chatId) {
        if (window.NotionAI.Core.State.get('isGenerating')) return;

        const chats = window.NotionAI.Core.State.get('chats');
        const chat = chats.find(c => c.id === chatId);
        if (!chat) return;

        // Delete from backend
        if (chat.conversationId) {
            const deleted = await window.NotionAI.API.Client.deleteConversation(chat.conversationId);
            if (!deleted) return;
        }

        // Delete from local storage
        window.NotionAI.Chat.Storage.deleteChat(chatId);

        // Reset if current chat was deleted
        const currentChatId = window.NotionAI.Core.State.get('currentChatId');
        if (currentChatId === chatId) {
            this.startNewChat();
        }

        this.renderChatList();
    },

    /**
     * Renames a chat
     * @param {string} chatId - Chat ID to rename
     * @param {string} newTitle - New title
     */
    renameChat(chatId, newTitle) {
        window.NotionAI.Chat.Storage.updateChatTitle(chatId, newTitle);

        const currentChatId = window.NotionAI.Core.State.get('currentChatId');
        if (currentChatId === chatId) {
            document.getElementById('headerTitle').textContent = newTitle;
        }

        this.renderChatList();
    },

    /**
     * Toggles star status on a chat
     * @param {string} chatId - Chat ID
     */
    toggleStar(chatId) {
        window.NotionAI.Chat.Storage.toggleStar(chatId);
        this.renderChatList();
    },

    /**
     * Renders the chat list sidebar
     */
    renderChatList() {
        const chatList = document.getElementById('chatList');
        chatList.innerHTML = '';

        const chats = window.NotionAI.Core.State.get('chats');
        const currentChatId = window.NotionAI.Core.State.get('currentChatId');

        const starredChats = chats.filter(c => c.starred).sort((a, b) => b.id - a.id);
        const recentChats = chats.filter(c => !c.starred).sort((a, b) => b.id - a.id);

        const generateItems = (chats) => {
            chats.forEach(chat => {
                const btn = document.createElement('div');
                btn.className = `chat-item group flex items-center justify-between p-2 hover:bg-black/5 dark:hover:bg-white/5 rounded-lg cursor-pointer transition-colors ${chat.id === currentChatId ? 'bg-black/5 dark:bg-white/5' : ''}`;
                btn.onclick = () => this.selectChat(chat.id);

                const titleSpan = document.createElement('span');
                titleSpan.className = 'text-sm font-medium truncate flex-1 leading-snug';
                titleSpan.textContent = chat.title;

                const menuContainer = this.createChatMenu(chat);

                btn.appendChild(titleSpan);
                btn.appendChild(menuContainer);
                chatList.appendChild(btn);
            });
        };

        if (starredChats.length > 0) {
            this.addSectionHeader('Starred');
            generateItems(starredChats);
        }

        if (recentChats.length > 0) {
            this.addSectionHeader('Recents');
            generateItems(recentChats);
        }
    },

    /**
     * Creates the three-dot menu for a chat item
     * @param {Object} chat - Chat object
     * @returns {HTMLElement} Menu container element
     */
    createChatMenu(chat) {
        const menuContainer = document.createElement('div');
        menuContainer.className = 'chat-dropdown-container relative flex items-center ml-2';

        const moreBtn = document.createElement('button');
        moreBtn.className = 'opacity-0 group-hover:opacity-100 p-1 text-gray-500 hover:text-black dark:text-gray-400 dark:hover:text-white rounded transition-opacity';
        moreBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="1.5"></circle><circle cx="6" cy="12" r="1.5"></circle><circle cx="18" cy="12" r="1.5"></circle></svg>';
        moreBtn.onclick = (e) => {
            e.stopPropagation();
            window.NotionAI.Chat.Manager.toggleChatDropdown(e, chat.id);
        };

        const dropdown = this.createDropdownMenu(chat);

        menuContainer.appendChild(moreBtn);
        menuContainer.appendChild(dropdown);

        return menuContainer;
    },

    /**
     * Creates dropdown menu for chat
     * @param {Object} chat - Chat object
     * @returns {HTMLElement} Dropdown element
     */
    createDropdownMenu(chat) {
        const dropdown = document.createElement('div');
        dropdown.id = `dropdown-${chat.id}`;
        dropdown.className = 'absolute right-0 top-6 w-36 bg-white dark:bg-[#2a2825] border border-black/10 dark:border-white/10 rounded-xl p-1.5 z-[100] shadow-[0_4px_20px_rgba(0,0,0,0.1)] custom-dropdown flex-col gap-0.5';

        dropdown.innerHTML = `
            <button data-action="star" class="w-full text-left px-2 py-1.5 text-sm hover:bg-black/5 dark:hover:bg-white/10 rounded-md flex items-center gap-2 text-gray-700 dark:text-gray-300 transition-colors">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
                </svg>
                ${chat.starred ? 'Unstar' : 'Star'}
            </button>
            <button data-action="rename" class="w-full text-left px-2 py-1.5 text-sm hover:bg-black/5 dark:hover:bg-white/10 rounded-md flex items-center gap-2 text-gray-700 dark:text-gray-300 transition-colors">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 20h9"></path>
                    <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
                </svg>
                Rename
            </button>
            <div class="h-px bg-black/10 dark:border-white/10 my-1 mx-1"></div>
            <button data-action="delete" class="w-full text-left px-2 py-1.5 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md flex items-center gap-2 transition-colors">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"></path>
                </svg>
                Delete
            </button>
        `;

        // Add event listeners
        dropdown.querySelectorAll('button').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const action = btn.dataset.action;
                this.handleMenuAction(action, chat.id);
            });
        });

        return dropdown;
    },

    /**
     * Handles dropdown menu action
     * @param {string} action - Action name
     * @param {string} chatId - Chat ID
     */
    handleMenuAction(action, chatId) {
        this.closeChatDropdown();

        switch (action) {
            case 'star':
                this.toggleStar(chatId);
                break;
            case 'rename':
                window.NotionAI.UI.Modal.openRenameModal(chatId);
                break;
            case 'delete':
                this.deleteChat(chatId);
                break;
        }
    },

    /**
     * Toggles chat dropdown visibility
     * @param {Event} e - Event object
     * @param {string} chatId - Chat ID
     */
    toggleChatDropdown(e, chatId) {
        e.stopPropagation();

        if (this._activeDropdownId && this._activeDropdownId !== chatId) {
            this.closeChatDropdown();
        }

        const menu = document.getElementById(`dropdown-${chatId}`);
        if (menu) {
            if (menu.classList.contains('open')) {
                menu.classList.remove('open');
                this._activeDropdownId = null;
            } else {
                menu.classList.add('open');
                this._activeDropdownId = chatId;
            }
        }
    },

    /**
     * Closes open chat dropdown
     */
    closeChatDropdown() {
        if (this._activeDropdownId) {
            const menu = document.getElementById(`dropdown-${this._activeDropdownId}`);
            if (menu) {
                menu.classList.remove('open');
            }
            this._activeDropdownId = null;
        }
    },

    /**
     * Adds section header to chat list
     * @param {string} text - Header text
     */
    addSectionHeader(text) {
        const chatList = document.getElementById('chatList');
        const header = document.createElement('div');
        header.className = 'text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1 mt-4 px-2 tracking-wider';
        header.textContent = text;
        chatList.appendChild(header);
    }
};

// Global click handler to close dropdowns
document.addEventListener('click', (e) => {
    if (!e.target.closest('.chat-dropdown-container')) {
        window.NotionAI.Chat.Manager.closeChatDropdown();
    }
});
