"""Day 1: compare a manually chosen pair with Claude, store the result, and read it back.

Takes the same --a/--b/--phrase/--phrase-a/--phrase-b options as verify_claude_comparison.py.
Each run adds a new contradiction_results row; the candidate pair is reused if it exists.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.models import CandidatePair, ContradictionResult  # noqa: E402
from app.services.claude_analysis import compare_statements_with_raw  # noqa: E402
from app.services.result_storage import (  # noqa: E402
    get_or_create_candidate_pair,
    store_contradiction_result,
)
from verify_claude_comparison import load_pair, parse_pair_args, to_statement  # noqa: E402

# The Day 1 pair is chosen by hand, not by a retrieval method.
PAIR_METHOD = "manual"


def main() -> None:
    args = parse_pair_args()
    with SessionLocal() as db:
        (chunk_a, doc_a), (chunk_b, doc_b) = load_pair(db, args)
        a, b = to_statement(chunk_a, doc_a), to_statement(chunk_b, doc_b)
        print(f"Pair: chunk A {chunk_a.id} ({a.document}, p.{a.page})")
        print(f"      chunk B {chunk_b.id} ({b.document}, p.{b.page})")

        print("Calling Claude...")
        findings, raw_response = compare_statements_with_raw(a, b)
        print(f"Claude findings (validated): {[f.verdict for f in findings]}\n")
        if not findings:
            raise SystemExit("Claude returned no findings for this pair; nothing to store.")

        pair = get_or_create_candidate_pair(db, chunk_a.id, chunk_b.id, PAIR_METHOD)
        result_ids = [
            store_contradiction_result(db, pair.id, finding, raw_response).id
            for finding in findings
        ]
        db.commit()
        pair_id = pair.id

    # Fresh session, so everything below is read back from PostgreSQL.
    with SessionLocal() as db:
        for result, result_id in zip(findings, result_ids):
            row = db.get(ContradictionResult, result_id)
            stored_pair = db.get(CandidatePair, row.candidate_pair_id)

            print(f"candidate_pair id : {stored_pair.id} (method={stored_pair.method})")
            print(f"  chunk_a_id      : {stored_pair.chunk_a_id}")
            print(f"  chunk_b_id      : {stored_pair.chunk_b_id}")
            print(f"result id         : {row.id}")
            print(f"created_at        : {row.created_at}")
            print(f"verdict           : {row.verdict}")
            print(f"topic             : {row.topic}")
            print(f"confidence        : {row.confidence}")
            print(f"reasoning         : {row.reasoning}")
            print(f"evidence          : {json.dumps(row.evidence, indent=2, ensure_ascii=False)}")
            raw = row.llm_raw_response or {}
            print(f"llm_raw_response  : id={raw.get('id')}, model={raw.get('model')}, "
                  f"stop_reason={raw.get('stop_reason')}, "
                  f"usage={raw.get('usage', {}).get('output_tokens')} output tokens\n")

            assert row.candidate_pair_id == pair_id
            assert (stored_pair.chunk_a_id, stored_pair.chunk_b_id) == (chunk_a.id, chunk_b.id)
            assert row.verdict == result.verdict and row.topic == result.topic
            assert row.confidence == result.confidence
            assert row.evidence == [e.model_dump() for e in result.evidence]
            assert raw.get("content"), "llm_raw_response was not stored"

    print(f"OK: {len(result_ids)} contradiction results written to and read back from "
          "PostgreSQL, linked to their candidate pair")


if __name__ == "__main__":
    main()
