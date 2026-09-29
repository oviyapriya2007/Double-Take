import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DEFAULT_MODEL = "claude-sonnet-5"
MAX_TOKENS = 1024


class Evidence(BaseModel):
    document: str
    section: str | None = None
    page: int | None = None
    quote: str


class ContradictionVerdict(BaseModel):
    verdict: Literal["CONTRADICTION", "CONSISTENT", "UNCERTAIN"]
    topic: str
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[Evidence]


@dataclass
class Statement:
    """One side of a comparison sent to Claude.

    In the current implementation a statement is a chunk: text is the full text of one
    stored chunk (not a sentence extracted from it), and document/page/section are that
    chunk's source metadata.
    """

    text: str
    document: str
    page: int | None
    section: str | None = None


SYSTEM_PROMPT = """You are a careful technical-documentation reviewer. You compare two \
statements taken from technical documents and decide whether they contradict each other.

Rules:
- Compare the actual claims (values, ranges, conditions, requirements), not how similar \
the wording is. Similar statements are not automatically contradictory.
- CONTRADICTION: both statements make claims about the same subject that cannot both be true.
- CONSISTENT: the statements are about the same subject and agree, or are compatible.
- UNCERTAIN: the supplied text is insufficient, or it is not clear both statements are \
about the same subject.
- Use ONLY the two statements supplied. Do not use outside knowledge and do not invent \
facts, values, documents, or page numbers.
- Every evidence "quote" must be copied verbatim from one of the supplied statements, and \
its document/section/page must be that statement's metadata.
- confidence is a number between 0.0 and 1.0.

Respond with ONLY a JSON object, no markdown fences and no other text, in exactly this shape:
{
  "verdict": "CONTRADICTION" | "CONSISTENT" | "UNCERTAIN",
  "topic": "<short topic of the compared claim>",
  "reasoning": "<concise explanation comparing the claims>",
  "confidence": <number 0.0-1.0>,
  "evidence": [
    {"document": "<document>", "section": "<section>", "page": <page>, "quote": "<verbatim quote>"}
  ]
}"""


def _format_statement(label: str, statement: Statement) -> str:
    return (
        f"Statement {label}\n"
        f"document: {statement.document}\n"
        f"section: {statement.section}\n"
        f"page: {statement.page}\n"
        f"text:\n<<<\n{statement.text}\n>>>"
    )


def _extract_json(raw: str) -> dict:
    text = raw.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    return json.loads(text)


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _check_evidence_is_supplied(result: ContradictionVerdict, a: Statement, b: Statement) -> None:
    supplied = [_normalize(a.text), _normalize(b.text)]
    for item in result.evidence:
        quote = _normalize(item.quote)
        if not any(quote in source for source in supplied):
            raise ValueError(f"Evidence quote not found in the supplied statements: {item.quote!r}")


def compare_statements(a: Statement, b: Statement) -> ContradictionVerdict:
    """Ask Claude whether two statements contradict each other and return a validated verdict.

    Raises pydantic.ValidationError for a malformed response, ValueError if the response is
    not JSON or cites evidence that was not supplied.
    """
    result, _ = compare_statements_with_raw(a, b)
    return result


def compare_statements_with_raw(
    a: Statement, b: Statement
) -> tuple[ContradictionVerdict, dict]:
    """Same as compare_statements, but also returns Claude's full API response as a dict."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set in backend/.env")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL),
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"{_format_statement('A', a)}\n\n{_format_statement('B', b)}",
            }
        ],
    )
    raw = "".join(block.text for block in message.content if block.type == "text")

    try:
        data = _extract_json(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Claude did not return valid JSON: {raw[:200]!r}") from exc

    result = ContradictionVerdict.model_validate(data)
    _check_evidence_is_supplied(result, a, b)
    return result, message.model_dump(mode="json")
