#!/usr/bin/env python3
"""Claude backend adapter for chat mode using `claude -p` headless mode.
Adapts existing agent pattern to the chat session interface."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from chat.backends.base import BackendAdapter, ChatResponse


class ClaudeBackend(BackendAdapter):
    """Claude CLI adapter - uses subscription seat via `claude -p`."""

    @property
    def name(self) -> str:
        return "claude"

    def invoke(self, prompt: str, mode: str, cwd: str) -> ChatResponse | None:
        """Fresh Claude invocation."""
        cmd = self.argv_for(prompt, mode, native_id=None)
        return self._execute(cmd, cwd)

    def resume(self, native_id: str, prompt: str, mode: str, cwd: str) -> ChatResponse | None:
        """Resume existing Claude session with --continue."""
        if not native_id:
            return None
        cmd = self.argv_for(prompt, mode, native_id=native_id)
        result = self._execute(cmd, cwd)
        # If resume fails, return None to trigger replay fallback
        return result

    def argv_for(self, prompt: str, mode: str, native_id: str | None = None) -> list[str]:
        """Build Claude CLI command line.
        
        Chat mode: empty tool allowlist + sandbox workdir (set by caller via cwd)
        Task mode: full tools (uses existing Loop X tool boundaries)
        """
        cmd = ["claude", "-p"]
        
        if native_id:
            # Native resume - only send current user input
            cmd += ["--continue", native_id]
        
        # Permission mode for edits
        cmd += ["--permission-mode", "acceptEdits"]
        
        # Tool restrictions based on mode
        if mode == "chat":
            # Chat mode: no tools or read-only tools only
            # For MVP, use empty allowlist to prevent any tool use
            cmd += ["--allowedTools", ""]
        elif mode == "task":
            # Task mode: use Loop X's existing tool allowlist
            # For now, keep it restrictive - can expand later
            cmd += ["--allowedTools", "read_file,write_file,run_shell_command"]
        
        cmd += ["--output-format", "json", prompt]
        return cmd

    def _execute(self, cmd: list[str], cwd: str) -> ChatResponse | None:
        """Execute Claude CLI and parse response."""
        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout for chat
                check=True,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            # Log the error but don't crash - return None for graceful degradation
            stderr = getattr(exc, 'stderr', '') or ''
            if stderr:
                print(f"Claude CLI error: {stderr}", file=sys.stderr)
            return None

        # Parse JSON response
        try:
            if not proc.stdout:
                return None
            parsed = json.loads(proc.stdout)
            if not isinstance(parsed, dict):
                return None
        except json.JSONDecodeError:
            return None

        # Extract result text and session ID
        result_text = self._extract_result_text(parsed)
        native_id = self._extract_session_id(parsed)
        
        # Extract usage/tokens if available
        usage = parsed.get("usage", {})
        tokens_in = usage.get("input_tokens")
        tokens_out = usage.get("output_tokens")

        return ChatResponse(
            text=result_text or "(no response text)",
            native_id=native_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    def _extract_result_text(self, parsed: dict) -> str:
        """Extract the assistant's response text from Claude JSON output."""
        # Try various paths in Claude CLI output structure
        if "result" in parsed and isinstance(parsed["result"], dict):
            if "text" in parsed["result"]:
                return parsed["result"]["text"]
        if "text" in parsed:
            return parsed["text"]
        if "message" in parsed:
            return str(parsed["message"])
        return ""

    def _extract_session_id(self, parsed: dict) -> str | None:
        """Extract session ID for future --continue calls."""
        # Claude CLI may return session info in various fields
        if "session" in parsed and isinstance(parsed["session"], dict):
            return parsed["session"].get("id")
        if "session_id" in parsed:
            return parsed["session_id"]
        # If no explicit session ID, return None - resume won't work but that's OK
        return None
