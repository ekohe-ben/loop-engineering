#!/usr/bin/env python3
"""Backend adapter interface for chat mode - maps each AI provider's CLI
to a uniform interface (invoke/resume/argv_for). See loop-engineering
redesign PDF section 6."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator


@dataclass
class ChatMessage:
    """One exchange in the chat transcript."""
    role: str  # "user" | "assistant" | "tool"
    text: str
    seat: str | None = None  # Which backend produced this (for assistant messages)
    native_id: str | None = None  # Provider's session ID for resume
    tokens_in: int | None = None
    tokens_out: int | None = None


@dataclass
class ChatResponse:
    """Result from invoke() or resume()."""
    text: str
    native_id: str | None  # Session ID for future resume calls
    tokens_in: int | None = None
    tokens_out: int | None = None


class BackendAdapter(ABC):
    """Interface every AI provider CLI adapter must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identifier: 'claude' | 'agy' | 'codex' | 'pi'"""
        ...

    @abstractmethod
    def invoke(self, prompt: str, mode: str, cwd: str) -> ChatResponse | None:
        """Fresh invocation with no prior session context.
        
        Args:
            prompt: Complete prompt including chat persona + context
            mode: 'chat' (no tools) or 'task' (full tools)
            cwd: Working directory (sandbox for chat mode)
            
        Returns:
            ChatResponse with the reply, or None on failure
        """
        ...

    @abstractmethod
    def resume(self, native_id: str, prompt: str, mode: str, cwd: str) -> ChatResponse | None:
        """Native resume using provider's session continuation.
        
        Args:
            native_id: Session ID from a previous invoke/resume
            prompt: Just the current user input (not full context)
            mode: 'chat' or 'task'
            cwd: Working directory
            
        Returns:
            ChatResponse with the reply, or None if resume fails/unsupported
            (None triggers automatic fallback to invoke with full replay)
        """
        ...

    @abstractmethod
    def argv_for(self, prompt: str, mode: str, native_id: str | None = None) -> list[str]:
        """Build command-line arguments for this backend.
        
        Pure function for snapshot testing - does not execute anything.
        
        Args:
            prompt: The prompt text
            mode: 'chat' or 'task'
            native_id: Session ID for resume, None for fresh invoke
            
        Returns:
            Complete argv list ready for subprocess.run()
        """
        ...
