#!/usr/bin/env python3
"""Antigravity (agy) backend adapter stub for chat mode.
Phase 1 MVP: interface defined, implementation marked as future work.
Before completing this adapter, run agy CLI tests per design PDF section 6.1."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from chat.backends.base import BackendAdapter, ChatResponse


class AgyBackend(BackendAdapter):
    """Antigravity CLI adapter - uses Google AI Pro seat via `agy -p`.
    
    NOTE: This is a Phase 1 stub. Full implementation requires:
    1. Local agy CLI installation and auth verification
    2. Test samples of agy -p output with --output-format json
    3. Verification of --continue / --conversation session resume
    4. Mapping of tool permissions to agy's flag structure
    
    See design PDF section 6.1 for implementation checklist.
    """

    @property
    def name(self) -> str:
        return "agy"

    def invoke(self, prompt: str, mode: str, cwd: str) -> ChatResponse | None:
        """Fresh agy invocation.
        
        TODO: Implement once agy CLI is available and tested locally.
        Expected command structure: agy -p "<prompt>" --output-format json
        """
        # For MVP: return None (unsupported) - session manager will warn user
        print("agy backend not yet implemented - use 'claude' seat", file=sys.stderr)
        return None

    def resume(self, native_id: str, prompt: str, mode: str, cwd: str) -> ChatResponse | None:
        """Resume agy session.
        
        TODO: Implement --conversation <id> or --continue session resume.
        Return None if unsupported - triggers replay path.
        """
        return None

    def argv_for(self, prompt: str, mode: str, native_id: str | None = None) -> list[str]:
        """Build agy CLI command line.
        
        Preliminary structure based on design PDF - verify against actual CLI:
        - agy -p "<prompt>" for invoke
        - agy -p "<prompt>" --continue or --conversation <id> for resume
        - --output-format json for structured output
        - Tool permissions: TBD based on agy's actual flags
        """
        cmd = ["agy", "-p"]
        
        if native_id:
            # Placeholder - actual flag may be --conversation or --continue
            cmd += ["--continue", native_id]
        
        # Output format
        cmd += ["--output-format", "json"]
        
        # Tool restrictions - placeholder, verify actual agy flags
        if mode == "chat":
            # Chat mode: restrict tools (exact flags TBD)
            pass  # TODO: add agy's equivalent of --allowedTools ""
        elif mode == "task":
            # Task mode: allow tools
            pass  # TODO: add agy's tool permission flags
        
        cmd += [prompt]
        return cmd
