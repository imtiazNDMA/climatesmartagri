"""Kept for one release: the assistant now lives in csa_portal.ai.agents.assistant."""

from .ai.agents.assistant import (
    MAX_TOOL_ROUNDS,
    AssistantChatRequest,
    AssistantClient,
    AssistantError,
    AssistantService,
    AssistantView,
    LmStudioClient,
    add_assistant_routes,
)

__all__ = [
    "MAX_TOOL_ROUNDS", "AssistantChatRequest", "AssistantClient", "AssistantError", "AssistantService",
    "AssistantView", "LmStudioClient", "add_assistant_routes",
]
