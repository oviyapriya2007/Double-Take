"""Deterministic keys for recognising the same finding returned by different candidate pairs.

Overlapping chunks mean one factual comparison can reach Claude through several candidate
pairs. Two findings are the same when they compare the same two documents, have the same
verdict, and quote the same normalised evidence from each document. The topic is left out
because Claude words it differently for the same claim; the evidence identifies the claim.
There is no similarity scoring: evidence that still differs after normalisation makes a
different finding.
"""

import unicodedata
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping

from app.services.claude_analysis import ContradictionVerdict

FindingKey = tuple

_CHAR_REPLACEMENTS = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'", "\u2032": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"', "\u2033": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2212": "-",
})
_EDGE_CHARACTERS = " \"'`.,;:"


def normalize_text(text: str | None) -> str:
    """Casefolded text with typographic quotes/dashes made plain, whitespace collapsed and
    surrounding quote marks and punctuation removed."""
    text = unicodedata.normalize("NFKC", (text or "").translate(_CHAR_REPLACEMENTS))
    return " ".join(text.casefold().split()).strip(_EDGE_CHARACTERS)


def _key(
    document_ids: Iterable[uuid.UUID | None],
    verdict: str | None,
    evidence: Iterable[Mapping] | None,
) -> FindingKey:
    quotes_by_document: dict[str, set[str]] = defaultdict(set)
    for item in evidence or []:
        quote = normalize_text(item.get("quote"))
        if quote:
            quotes_by_document[normalize_text(item.get("document"))].add(quote)
    return (
        tuple(sorted(str(document_id) for document_id in set(document_ids))),
        verdict,
        tuple(sorted((document, tuple(sorted(quotes)))
                     for document, quotes in quotes_by_document.items())),
    )


def finding_key(
    document_ids: Iterable[uuid.UUID | None], finding: ContradictionVerdict
) -> FindingKey:
    """Key of a finding Claude returned for a pair of chunks from these two documents."""
    return _key(document_ids, finding.verdict, [e.model_dump() for e in finding.evidence])


def stored_result_key(
    document_ids: Iterable[uuid.UUID | None],
    verdict: str | None,
    evidence: list[dict] | None,
) -> FindingKey:
    """Key of a stored contradiction_results row; equal to finding_key of the finding it holds."""
    return _key(document_ids, verdict, evidence)
