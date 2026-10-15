"""Shared fixtures for chat integration tests."""
import json
import os
import stat
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def fake_claude_bin(tmp_path, monkeypatch):
    """Create a fake 'claude' binary on PATH that speaks the protocol.
    
    Returns a FakeClaudeBin helper that lets tests control responses.
    """
    bin_dir = tmp_path / "fake_bin"
    bin_dir.mkdir()
    
    # Prepend to PATH so our fake claude is found first
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    
    # Create state dir for the fake binary to communicate
    state_dir = tmp_path / "claude_state"
    state_dir.mkdir()
    
    helper = FakeClaudeBin(bin_dir, state_dir)
    helper.install()
    return helper


class FakeClaudeBin:
    """Helper to install and control a fake claude binary."""
    
    def __init__(self, bin_dir: Path, state_dir: Path):
        self.bin_dir = bin_dir
        self.state_dir = state_dir
        self.claude_path = bin_dir / "claude"
        self.call_count = 0
    
    def install(self):
        """Install the fake claude binary."""
        # Python script that reads response from state dir
        script = f'''#!/usr/bin/env python3
import json
import sys
from pathlib import Path

state_dir = Path("{self.state_dir}")
call_file = state_dir / "calls.jsonl"

# Record this invocation
with open(call_file, "a") as f:
    call_data = {{
        "argv": sys.argv,
        "cwd": str(Path.cwd()),
    }}
    json.dump(call_data, f)
    f.write("\\n")

# Determine which response to return based on call count
calls_file = state_dir / "calls.jsonl"
call_count = 0
if calls_file.exists():
    with open(calls_file) as cf:
        for _ in cf:
            call_count += 1

# Look for response_0.json (default for single response tests)
response_file = state_dir / "response_0.json"
if not response_file.exists():
    response_file = None

if response_file is None:
    # Default response
    response = {{
        "result": {{"text": "Default response from fake claude"}},
        "usage": {{"input_tokens": 100, "output_tokens": 50}},
        "session_id": "fake-session-123"
    }}
else:
    with open(response_file) as f:
        response = json.load(f)

print(json.dumps(response))
sys.exit(0)
'''
        self.claude_path.write_text(script)
        self.claude_path.chmod(self.claude_path.stat().st_mode | stat.S_IEXEC)
    
    def set_response(self, text: str, session_id: str | None = None, 
                     tokens_in: int = 100, tokens_out: int = 50, response_num: int = 0):
        """Set the response the fake claude will return.
        
        Matches real Claude CLI format:
        - result is a string (not dict with text)
        - session_id at top level
        - usage dict with input_tokens/output_tokens
        """
        response = {
            "result": text,  # String, not {"text": ...}
            "usage": {"input_tokens": tokens_in, "output_tokens": tokens_out},
        }
        if session_id:
            response["session_id"] = session_id
        
        response_file = self.state_dir / f"response_{response_num}.json"
        with open(response_file, "w") as f:
            json.dump(response, f)
    
    def get_calls(self) -> list[dict]:
        """Get all recorded calls to the fake claude binary."""
        calls_file = self.state_dir / "calls.jsonl"
        if not calls_file.exists():
            return []
        
        calls = []
        with open(calls_file) as f:
            for line in f:
                if line.strip():
                    calls.append(json.loads(line))
        return calls
    
    def clear_calls(self):
        """Clear recorded calls."""
        calls_file = self.state_dir / "calls.jsonl"
        if calls_file.exists():
            calls_file.unlink()
        
        # Clear response files
        for response_file in self.state_dir.glob("response_*.json"):
            response_file.unlink()


@pytest.fixture
def temp_loop_home(tmp_path, monkeypatch):
    """Set up a temporary LOOP_ENGINEERING_HOME."""
    loop_home = tmp_path / "loop_home"
    loop_home.mkdir()
    
    # Create expected directories
    sessions_dir = loop_home / "sessions"
    sessions_dir.mkdir()
    
    sandbox_dir = loop_home / "chat-sandbox"
    sandbox_dir.mkdir()
    
    # Point LOOP_ENGINEERING_HOME at temp dir
    monkeypatch.setenv("LOOP_ENGINEERING_HOME", str(loop_home))
    
    return loop_home


@pytest.fixture
def integration_env(fake_claude_bin, temp_loop_home):
    """Combined fixture for full integration environment."""
    return {
        "fake_claude": fake_claude_bin,
        "loop_home": temp_loop_home,
        "sessions_dir": temp_loop_home / "sessions",
        "sandbox_dir": temp_loop_home / "chat-sandbox",
    }
