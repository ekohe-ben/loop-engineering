#!/usr/bin/env python3
"""Summarizer for chat sessions - generates rolling summaries to control
replay cost. See design PDF section 5.

Phase 1 MVP: Thin stub with trigger logic defined. Full implementation
(structured prompts, incremental merge, summary.prev.md backup) is Phase 2."""
from pathlib import Path


class Summarizer:
    """Manages rolling summaries for long conversations."""

    def __init__(self, trigger_turns: int = 20, trigger_tokens: int = 16000):
        """Initialize summarizer with trigger thresholds.
        
        Args:
            trigger_turns: Trigger summary after N unsummarized turns
            trigger_tokens: Trigger summary after N unsummarized tokens
        """
        self.trigger_turns = trigger_turns
        self.trigger_tokens = trigger_tokens

    def should_summarize(self, unsummarized_count: int, unsummarized_tokens: int) -> bool:
        """Check if summary should be triggered.
        
        Args:
            unsummarized_count: Number of messages since last summary
            unsummarized_tokens: Estimated tokens since last summary
            
        Returns:
            True if summary should be generated
        """
        return (
            unsummarized_count >= self.trigger_turns
            or unsummarized_tokens >= self.trigger_tokens
        )

    def generate_summary(
        self,
        existing_summary: str | None,
        new_messages: list[tuple[str, str]],  # [(role, text), ...]
        backend,  # BackendAdapter instance
        cwd: str,
    ) -> str | None:
        """Generate or update summary (Phase 2 implementation).
        
        Phase 1 MVP: Returns a placeholder message. Full implementation in Phase 2
        will use the backend to generate structured summaries.
        
        Args:
            existing_summary: Current summary (or None for first summary)
            new_messages: New messages to incorporate
            backend: Backend adapter to use for summarization
            cwd: Working directory for backend execution
            
        Returns:
            Updated summary text, or None on failure
        """
        # Phase 1 stub: indicate summarizer is not yet implemented
        return None  # Triggers REPL to show "Summarizer is Phase 2" message

    def save_summary(self, session_dir: Path, summary: str):
        """Save summary to summary.md and backup previous version.
        
        Args:
            session_dir: Session directory
            summary: Summary text to save
        """
        summary_path = session_dir / "summary.md"
        
        # Backup existing summary
        if summary_path.exists():
            backup_path = session_dir / "summary.prev.md"
            summary_path.rename(backup_path)
        
        # Write new summary
        with open(summary_path, "w") as f:
            f.write(summary)

    def load_summary(self, session_dir: Path) -> str | None:
        """Load existing summary from summary.md.
        
        Args:
            session_dir: Session directory
            
        Returns:
            Summary text or None if not available
        """
        summary_path = session_dir / "summary.md"
        if not summary_path.exists():
            return None
        
        with open(summary_path) as f:
            return f.read()
