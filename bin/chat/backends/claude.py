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
        
        Chat mode: no tools + sandbox workdir (set by caller via cwd)
        Task mode: controlled tools (uses existing Loop X tool boundaries)
        """
        cmd = ["claude", "-p"]
        
        if native_id:
            # Native resume by session ID - use --resume (not --continue)
            # --continue is boolean (latest conversation in cwd)
            cmd += ["--resume", native_id]
        
        # Tool restrictions based on mode
        if mode == "chat":
            # Chat mode: deny all tools for safety
            # Don't use --permission-mode acceptEdits (auto-accepts writes)
            cmd += ["--disallowedTools", "all"]
        elif mode == "task":
            # Task mode: use Loop X's existing tool boundaries
            # Allow specific tools, use acceptEdits for unattended operation
            cmd += ["--permission-mode", "acceptEdits"]
            cmd += ["--allowedTools", "read_file,write_file,run_shell_command"]
        
        cmd += ["--output-format", "json"]
        
        # Use -- to prevent prompt starting with - from being parsed as flags
        cmd += ["--", prompt]
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
        except FileNotFoundError:
            # Claude CLI not found on PATH
            print("claude: command not found. Install Claude Code CLI first.", file=sys.stderr)
            return None
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

        # Extract result text using same pattern as cost.extract_result_text
        # Real Claude CLI returns result as a string, not a dict
        result_text = self._extract_result_text(parsed)
        
        # Extract session ID for future --resume calls
        native_id = self._extract_session_id(parsed)
        
        # Extract usage/tokens if available
        usage = parsed.get("usage", {})
        tokens_in = usage.get("input_tokens")
        tokens_out = usage.get("output_tokens")

        return ChatResponse(
            text=result_text,
            native_id=native_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    def _extract_result_text(self, parsed: dict) -> str:
        """Extract the assistant's response text from Claude JSON output.
        
        Matches cost.extract_result_text pattern: result is a string, not a dict.
        Real Claude CLI format: {"result": "text response here", ...}
        """
        result = parsed.get("result")
        return result if isinstance(result, str) else "(no result text in CLI output)"

    def _extract_session_id(self, parsed: dict) -> str | None:
        """Extract session ID for future --resume calls.
        
        Real Claude CLI format: {"session_id": "uuid-here", ...}
        """
        return parsed.get("session_id")
