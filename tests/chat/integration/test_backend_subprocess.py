#!/usr/bin/env python3
"""Integration tests for backend subprocess execution.

Tests real subprocess.run() boundaries with a fake claude binary,
not just argv generation."""
import pytest

from chat.backends.claude import ClaudeBackend


pytestmark = pytest.mark.integration


class TestClaudeBackendSubprocess:
    """Test ClaudeBackend through real subprocess execution."""

    def test_invoke_executes_real_subprocess(self, integration_env):
        """ClaudeBackend.invoke() runs real subprocess and parses response."""
        fake_claude = integration_env["fake_claude"]
        sandbox_dir = integration_env["sandbox_dir"]
        
        # Set up fake claude to return a specific message
        fake_claude.set_response(
            text="Hello from fake Claude!",
            session_id="session-abc-123",
            tokens_in=150,
            tokens_out=30,
        )
        
        backend = ClaudeBackend()
        response = backend.invoke(
            prompt="Test prompt",
            mode="chat",
            cwd=str(sandbox_dir),
        )
        
        # Assert response was parsed correctly
        assert response is not None
        assert response.text == "Hello from fake Claude!"
        assert response.native_id == "session-abc-123"
        assert response.tokens_in == 150
        assert response.tokens_out == 30
        
        # Verify subprocess was actually called
        calls = fake_claude.get_calls()
        assert len(calls) == 1
        assert calls[0]["argv"][0].endswith("claude")
        assert "-p" in calls[0]["argv"]
        # Prompt comes after -- separator
        assert "--" in calls[0]["argv"]
        assert "Test prompt" in calls[0]["argv"]

    def test_resume_with_native_id_uses_resume_flag(self, integration_env):
        """ClaudeBackend.resume() uses --resume (not --continue) for session ID."""
        fake_claude = integration_env["fake_claude"]
        sandbox_dir = integration_env["sandbox_dir"]
        
        fake_claude.set_response(
            text="Resumed conversation",
            session_id="session-abc-123",
        )
        
        backend = ClaudeBackend()
        response = backend.resume(
            native_id="session-abc-123",
            prompt="Follow-up question",
            mode="chat",
            cwd=str(sandbox_dir),
        )
        
        assert response is not None
        assert response.text == "Resumed conversation"
        
        # Verify --resume was passed (not --continue)
        # --continue is boolean (latest conversation in cwd)
        # --resume <id> resumes specific session
        calls = fake_claude.get_calls()
        assert len(calls) == 1
        assert "--resume" in calls[0]["argv"]
        assert "session-abc-123" in calls[0]["argv"]
        assert "--continue" not in calls[0]["argv"]

    def test_chat_mode_disallows_all_tools(self, integration_env):
        """Chat mode denies all tools with --disallowedTools all."""
        fake_claude = integration_env["fake_claude"]
        sandbox_dir = integration_env["sandbox_dir"]
        
        fake_claude.set_response(text="Chat response")
        
        backend = ClaudeBackend()
        backend.invoke(
            prompt="Test",
            mode="chat",
            cwd=str(sandbox_dir),
        )
        
        calls = fake_claude.get_calls()
        argv = calls[0]["argv"]
        
        # Should use --disallowedTools all (not --allowedTools "")
        assert "--disallowedTools" in argv
        idx = argv.index("--disallowedTools")
        assert argv[idx + 1] == "all"
        
        # Should NOT have --permission-mode acceptEdits (auto-accepts writes)
        assert "--permission-mode" not in argv or "acceptEdits" not in argv

    def test_task_mode_enables_tools_with_accept_edits(self, integration_env):
        """Task mode allows specific tools and uses acceptEdits for unattended operation."""
        fake_claude = integration_env["fake_claude"]
        sandbox_dir = integration_env["sandbox_dir"]
        
        fake_claude.set_response(text="Task response")
        
        backend = ClaudeBackend()
        backend.invoke(
            prompt="Test",
            mode="task",
            cwd=str(sandbox_dir),
        )
        
        calls = fake_claude.get_calls()
        argv = calls[0]["argv"]
        
        # Should have --allowedTools with specific tools
        assert "--allowedTools" in argv
        idx = argv.index("--allowedTools")
        tools = argv[idx + 1]
        assert tools != ""
        assert "read_file" in tools or "write_file" in tools
        
        # Task mode SHOULD use --permission-mode acceptEdits
        assert "--permission-mode" in argv
        perm_idx = argv.index("--permission-mode")
        assert argv[perm_idx + 1] == "acceptEdits"

    def test_failed_subprocess_returns_none(self, integration_env, tmp_path, monkeypatch):
        """Backend gracefully handles subprocess failure."""
        # Create a failing fake claude with correct name
        failing_dir = tmp_path / "failing_bin"
        failing_dir.mkdir()
        failing_bin = failing_dir / "claude"
        failing_bin.write_text("#!/bin/bash\nexit 1\n")
        failing_bin.chmod(0o755)
        
        # Temporarily replace PATH to use failing binary
        monkeypatch.setenv("PATH", f"{failing_dir}")
        
        backend = ClaudeBackend()
        response = backend.invoke(
            prompt="Test",
            mode="chat",
            cwd=str(integration_env["sandbox_dir"]),
        )
        
        # Should return None, not raise
        assert response is None

    def test_malformed_json_returns_none(self, integration_env, tmp_path, monkeypatch):
        """Backend handles malformed JSON output."""
        # Create fake claude that returns invalid JSON with correct name
        bad_dir = tmp_path / "bad_bin"
        bad_dir.mkdir()
        bad_bin = bad_dir / "claude"
        bad_bin.write_text("#!/bin/bash\necho 'not json'\n")
        bad_bin.chmod(0o755)
        
        monkeypatch.setenv("PATH", f"{bad_dir}")
        
        backend = ClaudeBackend()
        response = backend.invoke(
            prompt="Test",
            mode="chat",
            cwd=str(integration_env["sandbox_dir"]),
        )
        
        assert response is None

    def test_multiple_invocations_work(self, integration_env):
        """Backend can be called multiple times."""
        fake_claude = integration_env["fake_claude"]
        sandbox_dir = integration_env["sandbox_dir"]
        
        # First call
        fake_claude.set_response(text="First response", response_num=0)
        
        backend = ClaudeBackend()
        response1 = backend.invoke("First prompt", "chat", str(sandbox_dir))
        assert response1 is not None
        assert response1.text == "First response"
        
        # Verify first call was made
        calls1 = fake_claude.get_calls()
        assert len(calls1) >= 1
        
        # Second call with fresh setup
        # (Note: fake binary reads response_0.json each time, so we can just
        # update it and the next call will get the new response)
        fake_claude.set_response(text="Second response", response_num=0)
        
        response2 = backend.invoke("Second prompt", "chat", str(sandbox_dir))
        assert response2 is not None
        assert response2.text == "Second response"
        
        # Verify second call was also made
        calls2 = fake_claude.get_calls()
        assert len(calls2) >= 2
