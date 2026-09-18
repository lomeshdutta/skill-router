"""Offline tests. They force MOCK mode so no API key or network is needed."""

import json
import os
from pathlib import Path

import pytest

from skill_router import catalog, hook, skills_sh
from skill_router.catalog import SkillInfo
from skill_router.context import build_state
from skill_router.router import route


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch):
    monkeypatch.setenv("SKILL_ROUTER_MOCK", "1")
    monkeypatch.delenv("SKILL_ROUTER_DISABLE", raising=False)


SKILLS = [
    SkillInfo("cold-email", "Write cold outreach emails and sequences for sales prospecting", "project", "x"),
    SkillInfo("seo-audit", "Audit a website's SEO: metadata, headings, sitemap, keywords", "project", "x"),
    SkillInfo("code-review", "Review the current diff for correctness bugs and cleanups", "user", "x"),
    SkillInfo("pptx", "Create or edit PowerPoint .pptx slide decks", "plugin", "x"),
]


def test_parse_frontmatter_handles_block_scalars():
    text = "---\nname: demo\ndescription: >\n  Line one\n  line two\n---\n# Body\n"
    fm = catalog.parse_frontmatter(text)
    assert fm == {"name": "demo", "description": "Line one line two"}


def test_discover_reads_project_and_respects_off_override(tmp_path, monkeypatch):
    proj = tmp_path / "proj" / ".claude" / "skills"
    (proj / "alpha").mkdir(parents=True)
    (proj / "alpha" / "SKILL.md").write_text("---\nname: alpha\ndescription: Alpha skill\n---\n")
    (proj / "beta").mkdir()
    (proj / "beta" / "SKILL.md").write_text("---\nname: beta\ndescription: Beta skill\n---\n")
    home = tmp_path / "home"
    (home / "skills").mkdir(parents=True)
    (home / "settings.json").write_text(json.dumps({"skillOverrides": {"beta": "off"}}))
    monkeypatch.setattr(catalog, "CLAUDE_HOME", home)
    names = [s.name for s in catalog.discover(tmp_path / "proj")]
    assert names == ["alpha"]


def test_mock_route_picks_obvious_skill():
    state = build_state("draft a cold email sequence for sales prospecting", cwd=os.getcwd())
    rec = route(state, SKILLS)
    assert rec.source == "mock"
    assert rec.skill == "cold-email"
    assert rec.should_suggest
    assert abs(sum(rec.skill_probabilities.values())) <= 1.0001


def test_mock_route_returns_none_for_generic_prompt():
    rec = route({"user_prompt": "what time is it"}, SKILLS)
    assert rec.skill is None
    assert not rec.should_suggest


def test_hook_skips_slash_commands_and_short_prompts():
    assert hook.should_skip("/cto review") == "already_a_skill_invocation"
    assert hook.should_skip("hi") == "too_short"
    assert hook.should_skip("please audit the SEO of my landing page") is None


def test_hook_run_emits_valid_userpromptsubmit_json(tmp_path, monkeypatch):
    monkeypatch.setattr(hook, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(catalog, "discover", lambda cwd=None: SKILLS)
    out = hook.run({"prompt": "review this diff for bugs before I commit", "cwd": str(tmp_path)}, search_remote=False)
    assert out is not None
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "UserPromptSubmit"
    assert "code-review" in hso["additionalContext"]
    assert (tmp_path / "log.jsonl").exists()


def test_hook_run_returns_none_when_disabled(monkeypatch):
    monkeypatch.setenv("SKILL_ROUTER_DISABLE", "1")
    assert hook.run({"prompt": "review this diff for bugs before I commit"}) is None


def test_parse_skills_sh_find_output():
    sample = (
        "\x1b[38;5;102mInstall with\x1b[0m npx skills add <owner/repo@skill>\n\n"
        "\x1b[38;5;145maffaan-m/ecc@react-testing\x1b[0m \x1b[36m4.7K installs\x1b[0m\n"
        "\x1b[38;5;102m└ https://skills.sh/affaan-m/ecc/react-testing\x1b[0m\n\n"
        "\x1b[38;5;145mtrungdo9/claukit@seo-schema\x1b[0m \x1b[36m1 install\x1b[0m\n"
    )
    res = skills_sh.parse_find_output(sample)
    assert [(r.package, r.skill, r.installs) for r in res] == [("affaan-m/ecc", "react-testing", "4.7K"), ("trungdo9/claukit", "seo-schema", "1")]
    assert res[0].install_command == "npx skills add affaan-m/ecc@react-testing"
    assert res[0].url.endswith("/react-testing")
