"""The never-happens invariant, as tests: hook entry points never crash a session, and the
API key never reaches the decision log."""

import io
import json
import sys

import pytest

from skill_router import hook


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(hook, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setenv("SKILL_ROUTER_MOCK", "1")


def _run_hook_main(stdin_text: str, capsys) -> tuple[int, str]:
    sys.stdin = io.StringIO(stdin_text)
    try:
        code = hook.main()
    finally:
        sys.stdin = sys.__stdin__
    return code, capsys.readouterr().out


def test_hook_survives_garbage_stdin(capsys):
    code, out = _run_hook_main("this is not json {", capsys)
    assert code == 0 and out == ""


def test_hook_survives_router_crash(monkeypatch, capsys, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(hook, "route", boom)
    payload = json.dumps({"prompt": "review my diff for bugs before I commit", "cwd": str(tmp_path)})
    code, out = _run_hook_main(payload, capsys)
    assert code == 0 and out == ""
    assert "network down" in (tmp_path / "log.jsonl").read_text()


def test_hook_output_is_valid_json_when_it_speaks(capsys, tmp_path):
    payload = json.dumps({"prompt": "review my diff for bugs before I commit", "cwd": str(tmp_path)})
    code, out = _run_hook_main(payload, capsys)
    assert code == 0
    if out:
        assert json.loads(out)["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"


def test_key_never_written_to_decision_log(monkeypatch, tmp_path):
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts_FAKEKEY_do_not_log_1234567890")
    monkeypatch.setenv("SKILL_ROUTER_MOCK", "1")
    hook.run({"prompt": "draft a cold outreach email sequence", "cwd": str(tmp_path)}, search_remote=False)
    assert "FAKEKEY" not in (tmp_path / "log.jsonl").read_text()
