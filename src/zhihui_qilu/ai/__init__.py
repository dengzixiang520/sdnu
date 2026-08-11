"""Provider-neutral language-model adapters and conversation orchestration."""

from zhihui_qilu.ai.provider import ChatMessage, DeepSeekProvider, LanguageModelProvider, OfflineProvider
from zhihui_qilu.ai.service import CampusConversationService, ConversationResult

__all__ = [
    "CampusConversationService",
    "ChatMessage",
    "ConversationResult",
    "DeepSeekProvider",
    "LanguageModelProvider",
    "OfflineProvider",
]
