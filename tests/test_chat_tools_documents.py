import json

from chat_tools import documents, registry


def test_save_writes_markdown_and_returns_a_download_url(tmp_path, monkeypatch):
    monkeypatch.setattr(documents, "DOCS_DIR", tmp_path)
    result = registry.run("docs.save", json.dumps(
        {"title": "Issue #482 summary", "content": "# Summary\nhello"}))
    name = result["result"]["name"]
    assert name.startswith("issue-482-summary") and name.endswith(".md")
    assert result["result"]["url"] == f"/chat-docs/{name}"
    assert (tmp_path / name).read_text() == "# Summary\nhello"


def test_save_never_overwrites_an_existing_document(tmp_path, monkeypatch):
    monkeypatch.setattr(documents, "DOCS_DIR", tmp_path)
    args = json.dumps({"title": "Same", "content": "one"})
    first = registry.run("docs.save", args)["result"]["name"]
    second = registry.run("docs.save", args)["result"]["name"]
    assert first != second and len(list(tmp_path.iterdir())) == 2


def test_title_with_path_tricks_cannot_escape_the_docs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(documents, "DOCS_DIR", tmp_path / "docs")
    result = registry.run("docs.save", json.dumps(
        {"title": "../../etc/passwd", "content": "x"}))
    assert (tmp_path / "docs" / result["result"]["name"]).exists()
    assert not (tmp_path / "etc").exists()


def test_safe_doc_name_accepts_only_generated_names():
    assert documents.safe_doc_name("a-b-1.md") == "a-b-1.md"
    for bad in ("../x.md", "a/b.md", "A.md", "a.txt", ".md", "a" * 90 + ".md"):
        assert documents.safe_doc_name(bad) is None
