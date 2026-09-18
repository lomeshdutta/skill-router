"""Ask Jev which skill fits, and turn its probabilities into a recommendation.

Jev is called ONCE per prompt with three or four questions evaluated in parallel:
  needs_skill      (Noul)   should we even suggest a skill?
  task_kind        (Choice) what sort of work is this?
  installed_skill  (Choice) which installed skill, if any?
  skills_sh_topic  (Choice) where to look on skills.sh if nothing local fits

Without a TYPESAFE_API_KEY (or with SKILL_ROUTER_MOCK=1) a keyword-overlap stand-in runs
instead, so the whole pipeline can be exercised offline. Mock output is clearly labelled.
"""

from __future__ import annotations

import math
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from skill_router import questions as Q
from skill_router.catalog import SkillInfo

MOCK_ENV = "SKILL_ROUTER_MOCK"
API_KEY_ENV = "TYPESAFE_API_KEY"
DEFAULT_TIMEOUT_SECONDS = 8.0

# Where the key may live when it is not already in the environment. The hook inherits
# Claude Code's environment, which often lacks shell-profile exports, so we read these.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOTENV_CANDIDATES = [_PROJECT_ROOT / ".env", Path.home() / ".config" / "skill-router" / ".env"]


def load_dotenv() -> None:
    """Minimal .env reader: KEY=value lines, no expansion. Never overrides existing vars."""
    for path in DOTENV_CANDIDATES:
        try:
            lines = path.read_text().splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip("\"'")
            if key and val and key not in os.environ:
                os.environ[key] = val


@dataclass
class Recommendation:
    source: str  # "jev" | "mock"
    model: str
    latency_ms: int
    needs_skill: float
    task_kind: str
    task_kind_confidence: float
    skill: str | None  # best installed skill, or None when Jev picked "none"
    skill_confidence: float
    skill_probabilities: dict[str, float]  # top few, descending
    topic: str | None
    topic_confidence: float
    usage: dict[str, int | None] = field(default_factory=dict)

    @property
    def should_suggest(self) -> bool:
        return (
            self.needs_skill >= Q.NEEDS_SKILL_MIN
            and self.skill is not None
            and self.skill_confidence >= Q.SUGGEST_MIN_CONFIDENCE
        )

    @property
    def runners_up(self) -> list[tuple[str, float]]:
        return [
            (name, p)
            for name, p in self.skill_probabilities.items()
            if name != self.skill and name != Q.NONE_OPTION and p >= Q.RUNNER_UP_MIN_PROB
        ][:3]

    @property
    def should_search_skills_sh(self) -> bool:
        best_local = max((p for n, p in self.skill_probabilities.items() if n != Q.NONE_OPTION), default=0.0)
        return (
            self.needs_skill >= Q.SEARCH_SKILLS_SH_MIN_NEEDS
            and best_local < Q.SEARCH_SKILLS_SH_MAX_LOCAL_PROB
            and self.topic not in (None, Q.NONE_OPTION)
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["should_suggest"] = self.should_suggest
        d["should_search_skills_sh"] = self.should_search_skills_sh
        return d


def use_mock() -> bool:
    load_dotenv()
    return os.environ.get(MOCK_ENV) == "1" or not os.environ.get(API_KEY_ENV)


def route(state: dict[str, Any], skills: list[SkillInfo], *, top_k: int = 5) -> Recommendation:
    if use_mock():
        return _route_mock(state, skills, top_k=top_k)
    return _route_jev(state, skills, top_k=top_k)


# ----------------------------------------------------------------------------- Jev path
def _route_jev(state: dict[str, Any], skills: list[SkillInfo], *, top_k: int) -> Recommendation:
    from typesafe_sdk import RetryPolicy, TypeSafeClient

    qs = {
        "needs_skill": Q.NEEDS_SKILL,
        "task_kind": Q.TASK_KIND,
        "skills_sh_topic": Q.SKILLS_SH_TOPIC,
    }
    if skills:
        qs["installed_skill"] = Q.build_installed_skill_choice(skills)

    t0 = time.perf_counter()
    with TypeSafeClient(timeout=DEFAULT_TIMEOUT_SECONDS, retry=RetryPolicy(max_retries=1)) as client:
        resp = client.system_one(state=state, questions=qs)
    latency = int((time.perf_counter() - t0) * 1000)

    nouls, choices = resp.nouls, resp.choices
    skill_ans = choices.get("installed_skill")
    probs = dict(sorted(skill_ans.probabilities.items(), key=lambda kv: -kv[1])[:top_k]) if skill_ans else {}
    best = skill_ans.choice if skill_ans else Q.NONE_OPTION
    topic = choices["skills_sh_topic"]
    return Recommendation(
        source="jev",
        model=resp.model,
        latency_ms=latency,
        needs_skill=nouls["needs_skill"].noul,
        task_kind=choices["task_kind"].choice,
        task_kind_confidence=choices["task_kind"].confidence,
        skill=None if best == Q.NONE_OPTION else best,
        skill_confidence=skill_ans.confidence if skill_ans else 0.0,
        skill_probabilities=probs,
        topic=None if topic.choice == Q.NONE_OPTION else topic.choice,
        topic_confidence=topic.confidence,
        usage={"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens},
    )


# ---------------------------------------------------------------------------- mock path
_WORD = re.compile(r"[a-z][a-z0-9+#-]{2,}")
_STOP = {"the", "and", "for", "with", "this", "that", "from", "into", "your", "you", "use", "when", "what", "how", "can", "please", "help", "make", "want", "need", "like", "about", "using", "should", "will"}


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP}


def _softmax(scores: dict[str, float], temperature: float = 0.6) -> dict[str, float]:
    if not scores:
        return {}
    m = max(scores.values())
    exp = {k: math.exp((v - m) / temperature) for k, v in scores.items()}
    z = sum(exp.values())
    return {k: v / z for k, v in exp.items()}


def _confidence(probs: dict[str, float]) -> float:
    """Peakedness of a distribution: 1 when all mass is on one option, 0 when flat."""
    if len(probs) < 2:
        return 1.0 if probs else 0.0
    top = sorted(probs.values(), reverse=True)
    return max(0.0, min(1.0, top[0] - top[1]))


def _route_mock(state: dict[str, Any], skills: list[SkillInfo], *, top_k: int) -> Recommendation:
    t0 = time.perf_counter()
    prompt_tokens = _tokens(state.get("user_prompt", ""))
    scores: dict[str, float] = {}
    for s in skills:
        name_tokens = _tokens(s.name.replace("-", " "))
        desc_tokens = _tokens(s.description)
        hit = 3.0 * len(prompt_tokens & name_tokens) + 1.0 * len(prompt_tokens & desc_tokens)
        scores[s.name] = hit
    best_hit = max(scores.values(), default=0.0)
    scores[Q.NONE_OPTION] = 1.5  # a fixed prior so weak overlaps lose to "none"
    probs = _softmax(scores)
    ranked = dict(sorted(probs.items(), key=lambda kv: -kv[1]))
    best = next(iter(ranked)) if ranked else Q.NONE_OPTION

    kind_scores = {k: len(prompt_tokens & _tokens(v)) for k, v in Q.TASK_KIND.criteria.items()}
    kind_probs = _softmax({k: float(v) for k, v in kind_scores.items()}, temperature=0.8)
    kind = max(kind_probs, key=kind_probs.get)
    topic_scores = {k: len(prompt_tokens & _tokens(v or "")) for k, v in Q.SKILLS_SH_TOPIC.criteria.items()}
    topic_probs = _softmax({k: float(v) for k, v in topic_scores.items()}, temperature=0.8)
    topic = max(topic_probs, key=topic_probs.get)

    return Recommendation(
        source="mock",
        model="keyword-overlap-mock",
        latency_ms=int((time.perf_counter() - t0) * 1000),
        needs_skill=0.75 if best_hit >= 3 else (0.55 if best_hit >= 1 else 0.25),
        task_kind=kind,
        task_kind_confidence=_confidence(kind_probs),
        skill=None if best == Q.NONE_OPTION else best,
        skill_confidence=_confidence(ranked),
        skill_probabilities=dict(list(ranked.items())[:top_k]),
        topic=None if topic == Q.NONE_OPTION else topic,
        topic_confidence=_confidence(topic_probs),
    )
