"""Day 3 Task 3: check the one-retry behaviour of the Claude comparison, offline.

    python scripts/verify_claude_retry.py

Claude is replaced by canned replies, so no API key, database or network is needed. Checks:
a valid reply is not retried, an unparseable or schema-invalid reply is retried once, a
second failure raises ClaudeResponseError, and fabricated evidence is still rejected
without a retry.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import claude_analysis  # noqa: E402
from app.services.claude_analysis import (  # noqa: E402
    RETRY_INSTRUCTION,
    ClaudeResponseError,
    Statement,
    compare_statements_with_raw,
)

A = Statement(text="Maximum System Operating Pressure: 3.5 MPa (35 bar)", document="C.pdf", page=1)
B = Statement(text="Fluid System Maximum Pressure Rating: 1.8 MPa (18 bar)", document="D.pdf", page=1)


def verdict_json(quote_b: str = "1.8 MPa (18 bar)") -> str:
    return json.dumps({
        "topic": "maximum operating pressure",
        "verdict": "CONTRADICTION",
        "reasoning": "3.5 MPa and 1.8 MPa cannot both be the maximum pressure.",
        "confidence": 0.9,
        "evidence": [
            {"document": "C.pdf", "section": None, "page": 1, "quote": "3.5 MPa (35 bar)"},
            {"document": "D.pdf", "section": None, "page": 1, "quote": quote_b},
        ],
    })


VALID = verdict_json()
NOT_JSON = "The statements contradict each other."
BAD_SCHEMA = VALID.replace('"CONTRADICTION"', '"MAYBE"')
FABRICATED = verdict_json(quote_b="2.0 MPa (20 bar)")


def run(replies: list[str]) -> tuple[object, list[str]]:
    """Run one comparison against the canned replies; return the outcome and the prompts sent."""
    prompts: list[str] = []
    pending = list(replies)

    def fake_ask_claude(content: str) -> tuple[str, dict]:
        prompts.append(content)
        return pending.pop(0), {"id": f"fake-{len(prompts)}"}

    claude_analysis._ask_claude = fake_ask_claude
    try:
        outcome = compare_statements_with_raw(A, B)
    except ValueError as exc:
        outcome = exc
    return outcome, prompts


def main() -> None:
    outcome, prompts = run([VALID])
    assert len(prompts) == 1 and outcome[0].verdict == "CONTRADICTION"
    print("OK: valid reply accepted without a retry")

    for label, bad in (("invalid JSON", NOT_JSON), ("schema-invalid", BAD_SCHEMA)):
        outcome, prompts = run([bad, VALID])
        assert len(prompts) == 2, f"{label}: expected one retry"
        assert RETRY_INSTRUCTION not in prompts[0] and prompts[1].endswith(RETRY_INSTRUCTION)
        assert outcome[0].verdict == "CONTRADICTION" and outcome[1]["id"] == "fake-2"
        print(f"OK: {label} reply retried once, retry result returned")

    outcome, prompts = run([NOT_JSON, BAD_SCHEMA])
    assert len(prompts) == 2 and isinstance(outcome, ClaudeResponseError)
    print(f"OK: second failure raises ClaudeResponseError: {outcome}")

    outcome, prompts = run([FABRICATED])
    assert len(prompts) == 1
    assert isinstance(outcome, ValueError) and not isinstance(outcome, ClaudeResponseError)
    print(f"OK: fabricated evidence rejected without a retry: {outcome}")

    print("\nOK: one retry for unparseable replies, none for valid ones")


if __name__ == "__main__":
    main()
