"""LLM-as-judge for groundedness: is each claim in an answer supported by context?

The judge is asked for strict JSON; parsing is tolerant of markdown code
fences (models add them) but strict about shape and verdict vocabulary —
anything else is a parse_error, counted separately rather than guessed at.
The phrase "Return ONLY JSON" is load-bearing: FakeAIClient detects it to
return parseable JSON, keeping the eval harness runnable offline.
"""
import json
import re
from dataclasses import dataclass, field

JUDGE_SYSTEM_PROMPT = (
    "You are a strict grading assistant. The user gives you an ANSWER and the "
    "CONTEXT excerpts it was generated from. Split the answer into its factual "
    "claims and judge each claim strictly against the context alone: a claim "
    'is "supported" only if the context states it. Return ONLY JSON matching '
    'this schema, with no other text: {"claims": [{"text": "<claim>", '
    '"verdict": "supported" | "unsupported"}]}'
)


def build_judge_user_prompt(answer: str, context_block: str) -> str:
    return f"ANSWER:\n{answer}\n\nCONTEXT:\n{context_block}"


@dataclass(frozen=True)
class ClaimVerdict:
    text: str
    supported: bool


@dataclass(frozen=True)
class JudgeResult:
    claims: list[ClaimVerdict] = field(default_factory=list)
    parse_error: bool = False


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")


def parse_judge_output(raw: str) -> JudgeResult:
    cleaned = _FENCE_RE.sub("", raw.strip())
    try:
        payload = json.loads(cleaned)
        claims = []
        for item in payload["claims"]:
            verdict = item["verdict"]
            if verdict not in ("supported", "unsupported"):
                raise ValueError(f"unknown verdict: {verdict}")
            claims.append(ClaimVerdict(text=item["text"], supported=verdict == "supported"))
        return JudgeResult(claims=claims)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return JudgeResult(parse_error=True)


def unsupported_rate(results: list[JudgeResult]) -> float | None:
    claims = [c for r in results if not r.parse_error for c in r.claims]
    if not claims:
        return None
    return sum(1 for c in claims if not c.supported) / len(claims)
