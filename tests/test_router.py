"""Offline tests. They force MOCK mode so no API key or network is needed."""

import json
import os

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
    monkeypatch.setattr(catalog, "APP_SKILLS_GLOB", tmp_path / "no-app")
    found = catalog.discover(tmp_path / "proj")
    assert [s.name for s in found if s.scope != "builtin"] == ["alpha"]
    assert "code-review" in {s.name for s in found if s.scope == "builtin"}


def test_strong_pick_overrides_lukewarm_needs_skill():
    from skill_router.router import Recommendation

    base = dict(
        source="jev",
        model="m",
        latency_ms=1,
        task_kind="test",
        task_kind_confidence=1.0,
        topic=None,
        topic_confidence=0.0,
    )
    strong = Recommendation(
        needs_skill=0.34,
        skill="xlsx",
        skill_confidence=0.97,
        skill_probabilities={"xlsx": 0.97, "dataviz": 0.02},
        **base,
    )
    weak = Recommendation(
        needs_skill=0.34, skill="cto", skill_confidence=0.76, skill_probabilities={"cto": 0.77, "none": 0.23}, **base
    )
    assert strong.should_suggest
    assert not weak.should_suggest


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
    assert [(r.package, r.skill, r.installs) for r in res] == [
        ("affaan-m/ecc", "react-testing", "4.7K"),
        ("trungdo9/claukit", "seo-schema", "1"),
    ]
    assert res[0].install_command == "npx skills add affaan-m/ecc@react-testing"
    assert res[0].url.endswith("/react-testing")


def test_load_dotenv_reads_key_without_overriding(tmp_path, monkeypatch):
    from skill_router import router

    env = tmp_path / ".env"
    env.write_text("# comment\nTYPESAFE_API_KEY='abc123'\nOTHER=x\n")
    monkeypatch.setattr(router, "DOTENV_CANDIDATES", [env])
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("OTHER", "keep")
    router.load_dotenv()
    assert os.environ["TYPESAFE_API_KEY"] == "abc123"
    assert os.environ["OTHER"] == "keep"


def test_build_query_prefers_tech_terms():
    q = skills_sh.build_query(
        "set up row level security policies in my Supabase Postgres database and speed up the slow queries",
        "databases",
        "build_feature",
    )
    assert q.split()[:2] == ["supabase", "postgres"]
    q2 = skills_sh.build_query(
        "build an agent with Google's Agent Development Kit that answers questions over our docs",
        "agent-workflows",
        "build_feature",
    )
    assert "google" in q2 and "agent" in q2
    assert (
        skills_sh.build_query("help me think through this idea", "productivity", "planning_strategy")
        == "productivity planning strategy"
    )


def test_extract_tech_terms_skips_urls():
    assert skills_sh.extract_tech_terms("grab the text of https://stripe.com/pricing as clean markdown") == []
    assert "next.js" in skills_sh.extract_tech_terms("set up Prisma in this next.js app")


def test_session_round_trip(tmp_path, monkeypatch):
    from skill_router import session

    monkeypatch.setattr(session, "SESSIONS_DIR", tmp_path)
    assert session.load("abc") is None
    session.save("abc/../x", {"goal": "ship it"})
    assert session.load("abc/../x")["goal"] == "ship it"
    assert not (tmp_path.parent / "x.json").exists()  # id is sanitised, no path escape
    assert session.clear("abc/../x") and session.load("abc/../x") is None


def test_intent_outcomes_in_mock_mode(tmp_path, monkeypatch, capsys):
    from skill_router import cli, session

    monkeypatch.setattr(session, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(hook, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(catalog, "discover", lambda cwd=None: SKILLS)
    assert (
        cli.main(["intent", "set", "--session", "s1", "--json", "write cold outreach emails for sales prospecting"])
        == 0
    )
    out = json.loads(capsys.readouterr().out)
    assert out["outcome"] == "A" and out["recommendation"]["skill"] == "cold-email"
    assert session.load("s1")["summary"] == "load /cold-email"
    assert cli.main(["intent", "set", "--session", "s2", "--json", "what time is it"]) == 0
    assert json.loads(capsys.readouterr().out)["outcome"] == "C"


def test_session_start_hook_shapes(tmp_path, monkeypatch, capsys):
    import io
    import sys as _sys

    from skill_router import cli, session

    monkeypatch.setattr(session, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(hook, "LOG_PATH", tmp_path / "log.jsonl")
    for stdin_text, expect in [
        (json.dumps({"session_id": "n1", "source": "startup"}), "ask exactly one question"),
        ("not json", None),
    ]:
        monkeypatch.setattr(_sys, "stdin", io.StringIO(stdin_text))
        assert cli.main(["session-start"]) == 0
        out = capsys.readouterr().out
        if expect is None:
            assert out == ""
        else:
            d = json.loads(out)["hookSpecificOutput"]
            assert d["hookEventName"] == "SessionStart" and expect in d["additionalContext"]
    session.save("r1", {"goal": "evaluate the router", "summary": "no skill needed"})
    monkeypatch.setattr(_sys, "stdin", io.StringIO(json.dumps({"session_id": "r1", "source": "resume"})))
    assert cli.main(["session-start"]) == 0
    assert "Session goal on record" in capsys.readouterr().out
