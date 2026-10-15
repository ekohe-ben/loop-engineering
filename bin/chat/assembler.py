#!/usr/bin/env python3
"""Context assembler for chat mode - builds replay packages with
summary + recent messages + current input, respecting token budgets.
See design PDF section 5."""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AssemblerConfig:
    """Token budget configuration for context assembly."""
    summary_max_tokens: int = 3000  # Max summary layer size
    recent_turns: int = 12  # How many recent turns to include
    recent_max_tokens: int = 12000  # Max recent messages layer size


@dataclass
class ReplayPackage:
    """Assembled context for cross-seat replay."""
    prompt: str  # Complete prompt ready for backend.invoke()
    summary_tokens: int  # Estimated tokens in summary
    recent_tokens: int  # Estimated tokens in recent messages
    total_tokens: int  # Estimated total


class ContextAssembler:
    """Assembles replay packages for cross-seat/cold resume."""

    # Chat persona injected into every prompt (design PDF section 7.3)
    CHAT_PERSONA = """You are Loop X's chat assistant. This is a discussion session, not a task execution.

Your role:
- Answer questions directly and concisely
- Explain mechanisms and tradeoffs when asked
- Follow the user's language (English/Chinese/etc.)
- Stay focused on providing information, not executing tasks

When in chat mode, you have no access to file writing or task tools.
"""

    # Cross-seat continuation instruction (design PDF section 7.1)
    CONTINUATION_INSTRUCTION = """NOTE: This is a continued conversation. Earlier messages were handled by a different AI model. The summary below represents conclusions already reached - treat them as agreed facts, not external references."""

    def __init__(self, config: AssemblerConfig | None = None):
        """Initialize assembler with token budget config.
        
        Args:
            config: Token budget configuration. Uses defaults if None.
        """
        self.config = config or AssemblerConfig()

    def assemble_replay(
        self,
        summary: str | None,
        recent_messages: list[tuple[str, str]],  # [(role, text), ...]
        current_input: str,
        is_continuation: bool = False,
    ) -> ReplayPackage:
        """Build complete replay package for invoke().
        
        Args:
            summary: Condensed summary of earlier conversation (or None)
            recent_messages: Recent message pairs (role, text) to include verbatim
            current_input: User's current message
            is_continuation: True if switching seats (adds continuation instruction)
            
        Returns:
            ReplayPackage with assembled prompt and token estimates
        """
        parts = []
        
        # 1. Chat persona (always first)
        parts.append(self.CHAT_PERSONA.strip())
        
        # 2. Continuation instruction (if switching seats)
        if is_continuation:
            parts.append(self.CONTINUATION_INSTRUCTION.strip())
        
        # 3. Summary layer (if available)
        summary_tokens = 0
        if summary:
            truncated_summary = self._truncate_summary(summary)
            if truncated_summary:
                parts.append("## Conversation Summary")
                parts.append(truncated_summary)
                summary_tokens = self._estimate_tokens(truncated_summary)
        
        # 4. Recent messages layer
        recent_tokens = 0
        if recent_messages:
            recent_text = self._format_recent_messages(recent_messages)
            parts.append("## Recent Messages")
            parts.append(recent_text)
            recent_tokens = self._estimate_tokens(recent_text)
        
        # 5. Current user input
        parts.append("## Current Message")
        parts.append(f"User: {current_input}")
        
        prompt = "\n\n".join(parts)
        total_tokens = (
            self._estimate_tokens(self.CHAT_PERSONA)
            + (self._estimate_tokens(self.CONTINUATION_INSTRUCTION) if is_continuation else 0)
            + summary_tokens
            + recent_tokens
            + self._estimate_tokens(current_input)
        )
        
        return ReplayPackage(
            prompt=prompt,
            summary_tokens=summary_tokens,
            recent_tokens=recent_tokens,
            total_tokens=total_tokens,
        )

    def _truncate_summary(self, summary: str) -> str:
        """Truncate summary to fit token budget.
        
        Args:
            summary: Raw summary text
            
        Returns:
            Truncated summary (or empty if over budget)
        """
        estimated = self._estimate_tokens(summary)
        if estimated <= self.config.summary_max_tokens:
            return summary
        
        # Rough truncation: cut proportionally
        ratio = self.config.summary_max_tokens / estimated
        target_chars = int(len(summary) * ratio * 0.9)  # 90% safety margin
        
        truncated = summary[:target_chars]
        if truncated:
            truncated += "\n[Summary truncated...]"
        
        return truncated

    def _format_recent_messages(self, messages: list[tuple[str, str]]) -> str:
        """Format recent messages for inclusion in replay package.
        
        Args:
            messages: List of (role, text) tuples
            
        Returns:
            Formatted message history
        """
        # Take last N turns respecting BOTH turn and token budgets
        # First limit by turn count, then by token budget
        recent_limited = messages[-self.config.recent_turns:]
        
        included = []
        accumulated_tokens = 0
        
        # Iterate backwards to get most recent first, respecting token budget
        for role, text in reversed(recent_limited):
            # Estimate tokens for the FORMATTED message (including prefix and separator)
            prefix = "User:" if role == "user" else "Assistant:"
            formatted_msg = f"{prefix} {text}"
            msg_tokens = self._estimate_tokens(formatted_msg)
            
            # Add separator tokens if this isn't the first message
            if included:
                msg_tokens += self._estimate_tokens("\n\n")
            
            # Stop if adding this message would exceed token budget
            if accumulated_tokens + msg_tokens > self.config.recent_max_tokens:
                break
            
            included.insert(0, (role, text))
            accumulated_tokens += msg_tokens
        
        # Format as readable exchange
        formatted = []
        for role, text in included:
            prefix = "User:" if role == "user" else "Assistant:"
            formatted.append(f"{prefix} {text}")
        
        return "\n\n".join(formatted)

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (design PDF: 4 chars ≈ 1 token).
        
        Args:
            text: Input text
            
        Returns:
            Estimated token count
        """
        # Simple heuristic: ~4 characters per token for English/mixed text
        # This is rough but sufficient for budget enforcement
        return len(text) // 4
