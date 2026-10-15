#!/usr/bin/env python3
"""Backend adapters for chat mode - each AI provider's CLI mapped to a
uniform interface."""
from chat.backends.base import BackendAdapter, ChatMessage, ChatResponse
from chat.backends.claude import ClaudeBackend
from chat.backends.agy import AgyBackend


def get_backend(name: str) -> BackendAdapter:
    """Get backend adapter by name.
    
    Args:
        name: Backend identifier ('claude', 'agy', etc.)
        
    Returns:
        Backend adapter instance
        
    Raises:
        ValueError: If backend name is unknown
    """
    backends = {
        "claude": ClaudeBackend,
        "agy": AgyBackend,
    }
    
    if name not in backends:
        available = ", ".join(sorted(backends.keys()))
        raise ValueError(f"Unknown backend: {name!r} (available: {available})")
    
    return backends[name]()


__all__ = [
    "BackendAdapter",
    "ChatMessage",
    "ChatResponse",
    "ClaudeBackend",
    "AgyBackend",
    "get_backend",
]
