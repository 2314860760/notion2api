/**
 * Constants Module
 * Defines all constants used across the application
 */

// Initialize namespace
window.NotionAI = window.NotionAI || {};
window.NotionAI.Core = window.NotionAI.Core || {};

window.NotionAI.Core.Constants = {
    // Storage Keys
    STORAGE_KEYS: {
        API_KEY: 'claude_api_key',
        BASE_URL: 'claude_base_url',
        CHATS: 'claude_chats',
        THEME: 'theme'
    },

    // API Endpoints
    API: {
        CHAT_COMPLETIONS: '/v1/chat/completions',
        DELETE_CONVERSATION: (id) => `/v1/conversations/${encodeURIComponent(id)}`
    },

    // Model Definitions
    MODELS: [
        { id: "claude-sonnet4.6", label: "Claude Sonnet 4.6" },
        { id: "claude-opus4.6", label: "Claude Opus 4.6" },
        { id: "gemini-3.1pro", label: "Gemini 3.1 Pro" },
        { id: "gpt-5.2", label: "GPT-5.2" },
        { id: "gpt-5.4", label: "GPT-5.4" },
    ],

    // Default Model
    DEFAULT_MODEL: "claude-sonnet4.6",

    // Display Name Mappings
    MODEL_DISPLAY_NAMES: {
        "claude-sonnet4.6": "Claude Sonnet 4.6",
        "claude-opus4.6": "Claude Opus 4.6",
        "gemini-3.1pro": "Gemini 3.1 Pro",
        "gpt-5.2": "GPT-5.2",
        "gpt-5.4": "GPT-5.4"
    },

    // Time-based Greetings
    GREETINGS: {
        EARLY_MORNING: "Early bird thinking",      // 5:00 - 9:00
        MORNING: "Morning clarity",                // 9:00 - 11:30
        MIDDAY: "Midday focus",                    // 11:30 - 13:30
        AFTERNOON: "Afternoon momentum",           // 13:30 - 17:00
        GOLDEN_HOUR: "Golden hour thinking",       // 17:00 - 19:00
        EVENING: "Evening deep work",              // 19:00 - 22:00
        NIGHT_OWL: "Night owl mode",               // 22:00 - 1:00
        LATE_NIGHT: "Late night thinking"          // 1:00 - 5:00
    },

    // Client Type Header
    CLIENT_TYPE: 'Web'
};
