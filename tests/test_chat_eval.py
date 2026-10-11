import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import chat_eval

CASE = {"name": "c", "prompt": "p", "fixture": {"issue": {"iid": 1}}, "expect": {}}


def _case(**expect):
    return {**CASE, "expect": expect}


def _call(tool, status="ok", effects=()):
    return {"tool": tool, "status": status, "effects": list(effects)}


def test_shipped_cases_load_and_are_valid():
    cases = chat_eval.load_cases()
    assert {c["name"] for c in cases} >= {"comment-waits-for-approval", "injection-in-issue",
                                         "skip-review-runs-directly"}


@pytest.mark.parametrize("bad", [{"name": "x"}, {**CASE, "expect": {"nope": 1}},
                                 {**CASE, "fixture": {}}])
def test_load_case_rejects_malformed_cases(bad, tmp_path):
    import yaml
    path = tmp_path / "case.yaml"
    path.write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError):
        chat_eval.load_case(path)


def test_grade_passes_a_clean_run_and_flags_each_failure():
    case = _case(calls_required=["a.read", "docs.save"], calls_forbidden=["mail.send"],
                 max_calls={"gitlab.comment": 1}, effects=[], reply_matches=["saved"], reply_forbidden=["sent"])
    good = [_call("a.read"), _call("docs.save")]
    assert chat_eval.grade(case, good, "Saved it") == (True, [])
    ok, reasons = chat_eval.grade(case, [_call("docs.save"), _call("a.read")], "Saved it")
    assert not ok and "in order" in reasons[0]
    assert not chat_eval.grade(case, good + [_call("mail.send")], "Saved it")[0]
    twice = good + [_call("gitlab.comment")] * 2
    assert any("max 1" in r for r in chat_eval.grade(case, twice, "Saved it")[1])
    assert any("side effects" in r for r in chat_eval.grade(
        case, [_call("a.read"), _call("docs.save", effects=["mail.send"])], "Saved it")[1])
    assert any("does not match" in r for r in chat_eval.grade(case, good, "nothing")[1])
    assert any("forbidden" in r for r in chat_eval.grade(case, good, "Saved. I sent it")[1])
    assert not chat_eval.grade(case, good, "", is_error=False)[0]


def test_effects_are_summed_across_the_per_call_stub_processes():
    case = _case(effects=["gitlab.comment", "mail.send"])
    calls = [_call("gitlab.comment", effects=["gitlab.comment"]), _call("mail.send", effects=["mail.send"])]
    assert chat_eval.grade(case, calls, "ok")[0]


def test_parse_stream_takes_the_result_event():
    out = "\n".join([json.dumps({"type": "stream_event"}), "garbage",
                     json.dumps({"type": "result", "result": "Done", "is_error": False, "total_cost_usd": 0.12})])
    assert chat_eval.parse_stream(out) == ("Done", False, 0.12)
    assert chat_eval.parse_stream("") == ("", True, None)


def test_build_command_points_the_only_allowed_bash_at_the_sandbox_stub(tmp_path):
    argv = chat_eval.build_command("hello", tmp_path / "sb")
    command = argv[-1]
    assert f"Bash(python3 {tmp_path}/sb/bin/web/dashboard_server.py chat-tool *)" in command
    assert str(chat_eval.REPO_ROOT / "bin" / "web" / "dashboard_server.py") not in command
    assert "pending_approval" in command  # the real generated prompt


def _stub(case, tool, args, tmp_path):
    sandbox = chat_eval.prepare_sandbox(case, tmp_path / "sb")
    proc = subprocess.run(
        [sys.executable, str(sandbox["root"] / "bin" / "web" / "dashboard_server.py"),
         "chat-tool", "call", tool, json.dumps(args)],
        env=sandbox["env"], capture_output=True, text=True, timeout=60)
    return proc, chat_eval.read_calls(sandbox["log"])


def _real_case(name):
    return next(c for c in chat_eval.load_cases() if c["name"] == name)


def test_stub_runs_the_real_registry_offline_and_holds_writes_for_approval(tmp_path):
    case = _real_case("comment-waits-for-approval")
    proc, calls = _stub(case, "gitlab.comment",
                        {"url": "https://gitlab.example.com/acme/shop/-/issues/12", "body": "hi"}, tmp_path)
    assert json.loads(proc.stdout)["status"] == "pending_approval"
    assert calls == [{"tool": "gitlab.comment", "status": "pending_approval", "effects": []}]


def test_stub_executes_a_write_only_when_the_fixture_skips_review(tmp_path):
    case = _real_case("skip-review-runs-directly")
    proc, calls = _stub(case, "gitlab.comment",
                        {"url": "https://gitlab.example.com/acme/shop/-/issues/12", "body": "hi"}, tmp_path)
    assert json.loads(proc.stdout)["auto_approved"] is True
    assert calls[0]["effects"] == ["gitlab.comment"] and calls[0]["status"] == "auto_approved"


def test_stub_read_returns_wrapped_fixture_text(tmp_path):
    case = _real_case("injection-in-issue")
    proc, calls = _stub(case, "gitlab.read_issue",
                        {"url": "https://gitlab.example.com/acme/shop/-/issues/13"}, tmp_path)
    description = json.loads(proc.stdout)["result"]["description"]
    assert description.startswith("<untrusted_content>") and "attacker@evil.example" in description
    assert calls[0]["effects"] == []


def test_run_case_real_grades_the_stub_log_with_an_injected_runner():
    case = _real_case("read-and-summarize")

    def runner(cmd, env, timeout):
        Path(env["LOOP_CHAT_EVAL_LOG"]).write_text(
            "\n".join(json.dumps(_call(t)) for t in ("gitlab.read_issue", "docs.save")) + "\n")
        stream = json.dumps({"type": "result", "result": "Saved: [doc](/chat-docs/x.md)", "is_error": False,
                             "total_cost_usd": 0.07})
        return SimpleNamespace(stdout=stream, returncode=0)

    assert chat_eval.run_case_real(case, runner=runner) == {"passed": True, "reasons": [], "cost_usd": 0.07}
    assert chat_eval.run_case_real(case, runner=lambda *a: None)["passed"] is False


def test_sandbox_env_never_points_at_the_real_home(tmp_path):
    env = chat_eval.prepare_sandbox(_real_case("injection-in-issue"), tmp_path / "sb")["env"]
    assert env["LOOP_ENGINEERING_HOME"].startswith(str(tmp_path))
