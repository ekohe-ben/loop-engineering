from chat_tools import pending


def test_create_then_claim_returns_the_frozen_record(tmp_path, monkeypatch):
    monkeypatch.setattr(pending, "PENDING_DIR", tmp_path)
    pid = pending.create("gitlab.comment", {"body": "hi"}, "s1", summary="g/p#1", now=1000)
    record = pending.claim(pid, "s1", now=1001)
    assert record["tool"] == "gitlab.comment" and record["args"] == {"body": "hi"}


def test_claim_is_single_use(tmp_path, monkeypatch):
    monkeypatch.setattr(pending, "PENDING_DIR", tmp_path)
    pid = pending.create("t", {}, "s1", now=1000)
    assert pending.claim(pid, "s1", now=1001) is not None
    assert pending.claim(pid, "s1", now=1002) is None


def test_claim_refuses_other_session_and_leaves_it_claimable(tmp_path, monkeypatch):
    monkeypatch.setattr(pending, "PENDING_DIR", tmp_path)
    pid = pending.create("t", {}, "s1", now=1000)
    assert pending.claim(pid, "other", now=1001) is None
    assert pending.claim(pid, "s1", now=1002) is not None


def test_claim_refuses_expired(tmp_path, monkeypatch):
    monkeypatch.setattr(pending, "PENDING_DIR", tmp_path)
    pid = pending.create("t", {}, "s1", now=1000)
    assert pending.claim(pid, "s1", now=1000 + pending.TTL_SECONDS + 1) is None


def test_ids_are_unguessable_and_path_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(pending, "PENDING_DIR", tmp_path)
    assert pending.claim("../../etc/passwd", "s1") is None
    assert len(pending.create("t", {}, "s1")) >= 32


def test_discard_removes_only_own_session(tmp_path, monkeypatch):
    monkeypatch.setattr(pending, "PENDING_DIR", tmp_path)
    pid = pending.create("t", {}, "s1")
    assert pending.discard(pid, "other") is False
    assert pending.discard(pid, "s1") is True
    assert pending.claim(pid, "s1") is None


def test_lookup_returns_the_stored_record_without_consuming_it(tmp_path, monkeypatch):
    monkeypatch.setattr(pending, "PENDING_DIR", tmp_path)
    pid = pending.create("gitlab.comment", {"body": "stored"}, "s1", summary="g/p#1", now=1000)
    record = pending.lookup(pid, "s1", now=1001)
    assert record["args"] == {"body": "stored"} and record["summary"] == "g/p#1"
    assert pending.lookup(pid, "s1", now=1002) is not None
    assert pending.claim(pid, "s1", now=1003) is not None
    assert pending.lookup(pid, "s1", now=1004) is None


def test_lookup_applies_the_same_checks_as_claim(tmp_path, monkeypatch):
    monkeypatch.setattr(pending, "PENDING_DIR", tmp_path)
    pid = pending.create("t", {}, "s1", now=1000)
    assert pending.lookup(pid, "other", now=1001) is None
    assert pending.lookup(pid, "s1", now=1000 + pending.TTL_SECONDS + 1) is None
    assert pending.lookup("../../etc/passwd", "s1") is None
    assert pending.lookup("f" * 32, "s1") is None


def test_an_empty_session_never_matches(tmp_path, monkeypatch):
    monkeypatch.setattr(pending, "PENDING_DIR", tmp_path)
    pid = pending.create("t", {}, "", now=1000)
    assert pending.lookup(pid, "", now=1001) is None
    assert pending.claim(pid, "", now=1001) is None
    assert pending.discard(pid, "") is False


def test_pending_dir_is_resolved_at_call_time(tmp_path, monkeypatch):
    monkeypatch.setattr(pending, "PENDING_DIR", tmp_path / "a")
    pid = pending.create("t", {}, "s1")
    assert (tmp_path / "a" / f"{pid}.json").exists()
