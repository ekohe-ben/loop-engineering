# Loop X Chat Mode

**Status**: Phase 1 MVP (Claude-first implementation)

Chat mode adds a stateful conversation layer to Loop X, allowing interactive chat sessions with context owned by the orchestrator. Switch between AI providers (Claude, Gemini via Antigravity) while maintaining conversation continuity—all using subscription seats via official CLIs, not API keys.

## Quick Start

```bash
# Start chat mode
python3 bin/loop_chat.py

# Create/open a session
python3 bin/loop_chat.py "my-session-name"
python3 bin/loop_chat.py "Discussion about Python"
```

## Architecture

Chat mode consists of four main components:

### 1. Session Archive (`bin/chat/session.py`)

Sessions are stored under `~/.loop-engineering/sessions/<slug>/`:
- `meta.json` - Session metadata (title, active seat, native IDs, mode)
- `transcript.jsonl` - Complete conversation history (append-only)
- `summary.md` - Rolling summary (Phase 2)
- `attachments/` - Optional file attachments (Phase 2)

### 2. Backend Adapters (`bin/chat/backends/`)

Uniform interface for AI provider CLIs:
- `ClaudeBackend` - Uses `claude -p` headless mode (implemented)
- `AgyBackend` - Uses `agy -p` for Gemini via Antigravity (stub)

Each adapter supports:
- `invoke()` - Fresh call with full context
- `resume()` - Native session continuation (if supported)
- `argv_for()` - Pure function for testing (snapshot tests)

### 3. Context Assembler (`bin/chat/assembler.py`)

Builds replay packages for cross-seat switching:
- Chat persona injection
- Summary layer (3K token budget)
- Recent messages (12 turns / 12K tokens)
- Continuation instructions for seat switches

### 4. REPL Interface (`bin/chat/repl.py`)

Interactive chat with commands:
- `/seat <backend>` - Switch AI provider (triggers replay)
- `/mode <chat|task>` - Switch tool permissions
- `/replay` - Force full context replay
- `/summary` - View/generate summary (Phase 2)
- `/end` - End session

## Modes

### Chat Mode (default)
- No file/shell tools (empty allowlist)
- Sandbox working directory (`~/.loop-engineering/chat-sandbox/`)
- Safe for open-ended discussion

### Task Mode
- Full tool access (same boundaries as GitLab loop)
- Real working directory
- Requires explicit `/mode task` switch

## Native Resume vs. Replay

Two code paths for efficiency:

**Native Resume** (fast path):
- Same seat, valid native session ID → just send current user input
- Uses provider's `--continue` or equivalent
- Automatic fallback to replay if resume fails

**Cross-Seat Replay** (compatibility path):
- Different seat, or native ID expired → assemble full context
- Summary + recent messages + current input
- Enables seamless seat switching

## Configuration

Add to `~/.loop-engineering/config.yaml` (or use `config/chat.json.template`):

```json
{
  "default_seat": "claude",
  "seats": ["claude", "agy"],
  "summary": {
    "trigger_turns": 20,
    "trigger_tokens": 16000,
    "max_tokens": 3000
  },
  "replay": {
    "recent_turns": 12,
    "recent_max_tokens": 12000
  },
  "sandbox_dir": "~/.loop-engineering/chat-sandbox"
}
```

## Testing

Chat mode has two test layers: **unit tests** (fast, no subprocess) and **integration tests** (real process boundaries, file I/O).

### Unit Tests (Fast)

Unit tests cover pure functions and isolated components:

```bash
# Run all unit tests
pytest tests/chat/test_*.py -v

# Specific unit test suites
pytest tests/chat/test_backends_argv.py      # Backend argv generation (snapshot tests)
pytest tests/chat/test_session.py             # Session manager (in-memory)
pytest tests/chat/test_assembler.py           # Context assembly and token budgets
```

### Integration Tests (With Fake Claude)

Integration tests exercise real subprocess boundaries and file persistence using a fake `claude` stub:

```bash
# Run all integration tests
pytest tests/chat/integration/ -v -m integration

# Run all chat tests (unit + integration)
pytest tests/chat/ -v

# Specific integration test suites
pytest tests/chat/integration/test_backend_subprocess.py  # Real subprocess.run() with stub
pytest tests/chat/integration/test_session_persistence.py # E2E file persistence
pytest tests/chat/integration/test_resume_and_replay.py   # Resume vs replay paths
pytest tests/chat/integration/test_repl_smoke.py          # REPL/CLI entry smoke tests
pytest tests/chat/integration/test_sandbox_redline.py     # Sandbox safety boundaries
```

**What the fake claude stub covers:**
- Real subprocess invocation (`subprocess.run`)
- Correct argv passing (`-p`, `--continue`, `--allowedTools`, etc.)
- JSON protocol (stub returns proper JSON response structure)
- Native session IDs for resume testing
- Failure modes (non-zero exit, malformed JSON)

**No real Claude login required** for default integration tests — the stub handles all subprocess interaction.

### Live Tests (Opt-In, Real Claude CLI)

For end-to-end verification with the real Claude CLI:

```bash
# Requires: claude CLI installed and logged in
LOOP_CHAT_LIVE=1 pytest tests/chat/integration/test_sandbox_redline.py::TestLiveSandboxBoundary -v
```

Live tests are **skipped by default** — they need:
- Real `claude` binary on PATH
- Active Claude subscription login
- Manual verification of tool restrictions

### Running All Tests

```bash
# All tests (unit + integration, no live)
pytest tests/chat/ -v

# Quick check (unit only, no subprocess)
pytest tests/chat/ -v -m "not integration"

# Full suite including integration
pytest tests/chat/ -v -m "integration or not integration"
```

### CI/Cloud Agent Testing

Integration tests run in CI with the fake stub (no authentication required). The `integration_env` fixture:
- Sets `LOOP_ENGINEERING_HOME` to temp directory
- Creates fake `claude` binary on PATH
- Provides isolated sandbox and sessions directories

## Phase 1 MVP Scope

**Implemented**:
- ✅ Session archive (file-based, no database)
- ✅ Claude backend via `claude -p`
- ✅ Native resume + replay fallback
- ✅ Chat/task mode switching
- ✅ REPL with core commands
- ✅ Context assembler with token budgets
- ✅ Sandbox directory for chat mode

**Stub/Incomplete**:
- ⚠️ Agy backend (interface defined, needs CLI testing)
- ⚠️ Summarizer (trigger logic defined, generation is Phase 2)

**Explicitly Out of Scope** (Phase 2+):
- Full 60-turn summarization
- Dashboard UI integration
- Codex/pi adapters
- Attachment handling

## Design Authority

Full design spec: `uploads/<hash>.pdf` (Muse redesign for loop-engineering chat sessions)

Key design decisions:
1. **Context owned by orchestrator**, not providers
2. **File-based archive** for auditability
3. **Native resume as optimization**, replay as truth
4. **Subscription seats only**, never API keys
5. **Dual-mode safety** (chat sandbox vs. task tools)

## Safety Boundaries

### Chat Mode
- Empty tool allowlist → no file/shell access
- Sandbox working directory → isolated from real files
- Read-only discussion only

### Task Mode
- Same tool boundaries as GitLab loop
- Explicit `/mode task` required
- Warning displayed on switch

### Credentials
- All auth stays in official CLIs (Claude Code, Antigravity)
- No API keys in config or environment
- Never extracts or proxies credentials

## Troubleshooting

### "agy backend not yet implemented"
The Antigravity adapter is a Phase 1 stub. Use Claude seat for MVP testing:
```
/seat claude
```

### Session not resuming (using replay every time)
Check native session ID in meta.json:
```bash
cat ~/.loop-engineering/sessions/<session-id>/meta.json | grep native
```
If empty or invalid, next message will replay. This is expected after seat switches.

### Tool access denied in chat mode
By design. Switch to task mode for file/shell tools:
```
/mode task
```

## Implementation Checklist

See `PROGRESS.md` for detailed acceptance criteria. Core requirements:

- [x] Sessions persist under `~/.loop-engineering/sessions/`
- [x] User can start chat, see messages persisted
- [x] Same-seat resume path implemented
- [x] Cross-seat replay path implemented  
- [x] Chat mode restricts tools to sandbox
- [x] Existing task loops still work
- [ ] Tests pass (pending pytest run)
- [ ] Branch pushed and PR opened

## Next Steps (Phase 2)

1. Full summarizer implementation with structured prompts
2. Agy backend completion (requires local agy CLI + test samples)
3. 60-turn acceptance test
4. Dashboard integration (reuse existing message panel)
5. Optional: Codex/pi adapters
