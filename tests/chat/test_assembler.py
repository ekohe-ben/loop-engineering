#!/usr/bin/env python3
"""Tests for context assembler - replay package construction and token budgets."""
import pytest

from chat.assembler import AssemblerConfig, ContextAssembler


class TestContextAssembler:
    """Test replay package assembly and token budgeting."""

    @pytest.fixture
    def assembler(self):
        """Standard assembler with default config."""
        return ContextAssembler()

    @pytest.fixture
    def tight_budget_assembler(self):
        """Assembler with tight token budget for testing limits."""
        config = AssemblerConfig(
            summary_max_tokens=100,
            recent_turns=3,
            recent_max_tokens=500,
        )
        return ContextAssembler(config)

    def test_assemble_fresh_chat(self, assembler):
        """First message has no summary or recent messages."""
        replay = assembler.assemble_replay(
            summary=None,
            recent_messages=[],
            current_input="Hello, how are you?",
            is_continuation=False,
        )
        
        assert "Hello, how are you?" in replay.prompt
        assert "Loop X's chat assistant" in replay.prompt
        assert replay.summary_tokens == 0
        assert replay.recent_tokens == 0
        assert "NOTE: This is a continued conversation" not in replay.prompt

    def test_assemble_with_continuation(self, assembler):
        """Cross-seat switch includes continuation instruction."""
        replay = assembler.assemble_replay(
            summary=None,
            recent_messages=[("user", "Hi"), ("assistant", "Hello")],
            current_input="Tell me more",
            is_continuation=True,
        )
        
        assert "NOTE: This is a continued conversation" in replay.prompt
        assert "different AI model" in replay.prompt

    def test_assemble_with_summary(self, assembler):
        """Summary is included in replay package."""
        summary = "Previously discussed: Python basics, loops, functions."
        
        replay = assembler.assemble_replay(
            summary=summary,
            recent_messages=[],
            current_input="What about classes?",
            is_continuation=False,
        )
        
        assert "Python basics" in replay.prompt
        assert "Conversation Summary" in replay.prompt
        assert replay.summary_tokens > 0

    def test_assemble_with_recent_messages(self, assembler):
        """Recent messages are formatted in replay package."""
        recent = [
            ("user", "What is Python?"),
            ("assistant", "Python is a programming language."),
            ("user", "Is it easy?"),
            ("assistant", "Yes, it's beginner-friendly."),
        ]
        
        replay = assembler.assemble_replay(
            summary=None,
            recent_messages=recent,
            current_input="Tell me about loops",
            is_continuation=False,
        )
        
        assert "What is Python?" in replay.prompt
        assert "programming language" in replay.prompt
        assert "Recent Messages" in replay.prompt
        assert replay.recent_tokens > 0

    def test_token_estimation(self, assembler):
        """Token estimation is roughly 4 chars per token."""
        # ~100 characters should be ~25 tokens
        text = "x" * 100
        tokens = assembler._estimate_tokens(text)
        
        assert 20 <= tokens <= 30  # Allow some variance

    def test_summary_truncation(self, tight_budget_assembler):
        """Long summary is truncated to fit budget."""
        # Create a summary much longer than budget
        long_summary = "Summary paragraph. " * 100  # ~2000 chars
        
        replay = tight_budget_assembler.assemble_replay(
            summary=long_summary,
            recent_messages=[],
            current_input="Test",
            is_continuation=False,
        )
        
        # Summary should be truncated
        assert replay.summary_tokens <= tight_budget_assembler.config.summary_max_tokens
        assert "[Summary truncated...]" in replay.prompt or replay.summary_tokens < 100

    def test_recent_messages_respect_turn_limit(self, tight_budget_assembler):
        """Only last N turns are included."""
        # Create more messages than turn limit
        messages = [
            (f"user" if i % 2 == 0 else "assistant", f"Message {i}")
            for i in range(10)
        ]
        
        replay = tight_budget_assembler.assemble_replay(
            summary=None,
            recent_messages=messages,
            current_input="Latest",
            is_continuation=False,
        )
        
        # Config has recent_turns=3, so at most 3 messages
        # Check that early messages are excluded
        assert "Message 0" not in replay.prompt
        assert "Message 1" not in replay.prompt
        # Later messages should be included
        assert "Message 7" in replay.prompt or "Message 8" in replay.prompt

    def test_recent_messages_respect_token_limit(self, tight_budget_assembler):
        """Recent messages layer respects token budget."""
        # Create messages that exceed token budget
        big_messages = [
            ("user", "x" * 1000),  # ~250 tokens each
            ("assistant", "y" * 1000),
            ("user", "z" * 1000),
        ]
        
        replay = tight_budget_assembler.assemble_replay(
            summary=None,
            recent_messages=big_messages,
            current_input="Test",
            is_continuation=False,
        )
        
        # Should be under budget
        assert replay.recent_tokens <= tight_budget_assembler.config.recent_max_tokens

    def test_complete_replay_structure(self, assembler):
        """Full replay has all sections in correct order."""
        replay = assembler.assemble_replay(
            summary="Previous context",
            recent_messages=[("user", "Hi"), ("assistant", "Hello")],
            current_input="How are you?",
            is_continuation=True,
        )
        
        # Check structure
        prompt_lower = replay.prompt.lower()
        
        # Persona should be first
        persona_pos = prompt_lower.find("loop x")
        assert persona_pos >= 0
        
        # Continuation instruction
        continuation_pos = prompt_lower.find("continued conversation")
        assert continuation_pos > persona_pos
        
        # Summary
        summary_pos = prompt_lower.find("conversation summary")
        assert summary_pos > continuation_pos
        
        # Recent messages
        recent_pos = prompt_lower.find("recent messages")
        assert recent_pos > summary_pos
        
        # Current input
        current_pos = prompt_lower.find("how are you")
        assert current_pos > recent_pos

    def test_empty_summary_skipped(self, assembler):
        """Empty or None summary doesn't add summary section."""
        replay = assembler.assemble_replay(
            summary="",
            recent_messages=[],
            current_input="Test",
            is_continuation=False,
        )
        
        assert "Conversation Summary" not in replay.prompt
        assert replay.summary_tokens == 0
