#!/usr/bin/env python3
"""Chat eval suite: runs the dashboard chat's real `claude -p` command (same
flags, same generated system prompt) against canned connectors and grades what
it did - which tools it called, whether any write took effect, and what it told
the user. Cases live in evals/chat/<name>/case.yaml. Like bin/golden_eval.py,
every real case costs money, so the suite has a hard budget.

The model's only allowed command is pointed at evals/chat/stub_dashboard.py (a
copy in a throwaway sandbox), so nothing here can reach GitLab, mail or the
calendar. Grading and suite control are pure; `run_case_real` is the paid path."""
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

import golden_eval

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES_DIR = REPO_ROOT / "evals" / "chat"
STUB_PATH = DEFAULT_CASES_DIR / "stub_dashboard.py"
DEFAULT_LAST_RUN_PATH = REPO_ROOT / "outputs" / "evals" / "chat-last.json"
_REPO_LAST_RUN_PATH = DEFAULT_LAST_RUN_PATH
DEFAULT_TIMEOUT_SECONDS = 300
_EXPECT_KEYS = {"calls_required", "calls_forbidden", "max_calls", "effects", "reply_matches", "reply_forbidden"}


def load_case(path):
    case = yaml.safe_load(Path(path).read_text())
    if not isinstance(case, dict):
        raise ValueError(f"{path}: case must be a mapping")
    for key in ("name", "prompt", "fixture", "expect"):
        if key not in case:
            raise ValueError(f"{path}: missing {key!r}")
    unknown = set(case["expect"]) - _EXPECT_KEYS
    if unknown:
        raise ValueError(f"{path}: unknown expect key(s): {', '.join(sorted(unknown))}")
    if "issue" not in case["fixture"]:
        raise ValueError(f"{path}: fixture.issue is required")
    return case


def load_cases(cases_dir=None, names=None):
    if cases_dir is None:
        cases_dir = DEFAULT_CASES_DIR
    cases = [load_case(p) for p in sorted(Path(cases_dir).glob("*/case.yaml"))]
    if names:
        unknown = [n for n in names if n not in {c["name"] for c in cases}]
        if unknown:
            raise ValueError(f"unknown chat case(s): {', '.join(unknown)}")
        cases = [c for c in cases if c["name"] in names]
    return cases


def grade(case, calls, reply, is_error=False):
    """(passed, reasons). `calls` is the stub's log: [{"tool", "status", "effects"}]."""
    expect, reasons = case["expect"], []
    if is_error or not (reply or "").strip():
        reasons.append("the chat produced no reply")
    names = [c["tool"] for c in calls]
    remaining = iter(names)
    for tool in expect.get("calls_required", []):
        if not any(tool == name for name in remaining):
            reasons.append(f"expected a call to {tool} (in order); calls were {names}")
            break
    for tool in expect.get("calls_forbidden", []):
        if tool in names:
            reasons.append(f"called forbidden tool {tool}")
    for tool, limit in (expect.get("max_calls") or {}).items():
        if names.count(tool) > limit:
            reasons.append(f"called {tool} {names.count(tool)} times (max {limit})")
    if "effects" in expect:
        done = [e for c in calls for e in c["effects"]]  # one stub process per call
        if sorted(done) != sorted(expect["effects"]):
            reasons.append(f"side effects were {done}, expected {expect['effects']}")
    for pattern in expect.get("reply_matches", []):
        if not re.search(pattern, reply or "", re.IGNORECASE):
            reasons.append(f"reply does not match /{pattern}/")
    for pattern in expect.get("reply_forbidden", []):
        if re.search(pattern, reply or "", re.IGNORECASE):
            reasons.append(f"reply matches forbidden /{pattern}/")
    return (not reasons), reasons


def run_suite(cases, budget_usd=3.0, run_case=None):
    """Same control as the golden suite: stop launching once the budget is spent."""
    if run_case is None:
        def run_case(case):
            return run_case_real(case)
    return golden_eval.run_suite(cases, budget_usd=budget_usd, run_case=run_case)


exit_code = golden_eval.exit_code


def _resolve_last_run_path(path):
    if path is not None:
        return Path(path)
    if DEFAULT_LAST_RUN_PATH != _REPO_LAST_RUN_PATH:
        return Path(DEFAULT_LAST_RUN_PATH)
    env = os.environ.get(golden_eval.EVALS_DIR_ENV)
    return Path(env) / "chat-last.json" if env else Path(DEFAULT_LAST_RUN_PATH)


def write_last_run(summary, budget_usd, path=None):
    path = _resolve_last_run_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "budget_usd": budget_usd,
            "spent_usd": summary.get("spent_usd", 0.0), "results": summary.get("results", []),
            "not_run": summary.get("not_run", [])}
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path


# --- the real (paid) path ----------------------------------------------------

def prepare_sandbox(case, root):
    """Stub tree + fixture under `root`; returns the paths and the child env."""
    root = Path(root)
    (root / "bin" / "web").mkdir(parents=True)
    shutil.copy(STUB_PATH, root / "bin" / "web" / "dashboard_server.py")
    fixture = root / "fixture.json"
    fixture.write_text(json.dumps(case["fixture"]))
    log = root / "calls.jsonl"
    env = {**os.environ,
           "LOOP_ENGINEERING_HOME": str(root / "home"),  # never the real ~/.loop-engineering
           "LOOP_EVENTS_DIR": str(root / "events"),
           "LOOP_CHAT_EVAL_DIR": str(root), "LOOP_CHAT_EVAL_REPO_BIN": str(REPO_ROOT / "bin"),
           "LOOP_CHAT_EVAL_FIXTURE": str(fixture), "LOOP_CHAT_EVAL_LOG": str(log)}
    return {"root": root, "log": log, "env": env}


def build_command(prompt, root):
    """The dashboard's real chat command, with its one allowed Bash command
    (and the prompt's tool instructions) pointing at the sandbox stub."""
    sys.path.insert(0, str(REPO_ROOT / "bin" / "web"))
    import dashboard_server as ds
    original = ds.LOOP_DIR
    ds.LOOP_DIR = Path(root)
    try:
        argv = ds.build_chat_command(prompt)
    finally:
        ds.LOOP_DIR = original
    # The base prompt bakes the real checkout path in at import time; point it
    # at the stub too so the model is never told about the real dashboard script.
    return [part.replace(str(original), str(root)) for part in argv]


def parse_stream(stdout):
    """(reply text, is_error, cost_usd) from claude's stream-json output."""
    reply, is_error, cost = "", True, None
    for line in (stdout or "").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            reply, is_error = event.get("result") or "", bool(event.get("is_error"))
            cost = event.get("total_cost_usd")
    return reply, is_error, cost


def read_calls(log):
    try:
        return [json.loads(line) for line in Path(log).read_text().splitlines() if line.strip()]
    except OSError:
        return []


def run_case_real(case, timeout_seconds=DEFAULT_TIMEOUT_SECONDS, runner=None):
    runner = runner or golden_eval._run_killing_group_on_timeout
    with tempfile.TemporaryDirectory(prefix="chat-eval-") as tmp:
        sandbox = prepare_sandbox(case, Path(tmp) / "sandbox")
        proc = runner(build_command(case["prompt"], sandbox["root"]), sandbox["env"], timeout_seconds)
        if proc is None:
            return {"passed": False, "reasons": [f"timed out after {timeout_seconds}s"], "cost_usd": None}
        reply, is_error, cost = parse_stream(proc.stdout)
        passed, reasons = grade(case, read_calls(sandbox["log"]), reply, is_error)
        return {"passed": passed, "reasons": reasons, "cost_usd": cost}
