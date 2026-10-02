"""Tests for finding-level deduplication across overlapping candidate pairs.

    python -m unittest discover -s tests

The key and pipeline tests are offline (Claude, retrieval and storage are faked). The
stored-key test uses the Docker PostgreSQL database and rolls back everything it adds.
"""

import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.models import CandidatePair, Chunk, ContradictionResult, Document  # noqa: E402
from app.services import pipeline  # noqa: E402
from app.services.claude_analysis import ContradictionVerdict  # noqa: E402
from app.services.finding_deduplication import finding_key, normalize_text  # noqa: E402
from app.services.result_storage import store_contradiction_result  # noqa: E402

DOC_A, DOC_B = uuid.uuid4(), uuid.uuid4()
DOCUMENTS = (DOC_A, DOC_B)


def finding(
    topic: str, quote_a: str, quote_b: str, verdict: str = "CONTRADICTION", **changes
) -> ContradictionVerdict:
    data = {
        "topic": topic,
        "verdict": verdict,
        "reasoning": f"{quote_a} and {quote_b} cannot both be true.",
        "confidence": 0.9,
        "evidence": [
            {"document": "A.pdf", "section": None, "page": 1, "quote": quote_a},
            {"document": "B.pdf", "section": None, "page": 2, "quote": quote_b},
        ],
    }
    return ContradictionVerdict.model_validate({**data, **changes})


MAINTENANCE = finding(
    "inspection interval",
    "inspect every 1,000 operating hours",
    "inspect every 500 operating hours",
)
VOLTAGE = finding("supply voltage", "26 V", "28 V")
TEMPERATURE = finding("maximum ambient temperature", "45°C", "50°C")
XR500_MAINTENANCE_TOPICS = [
    "maintenance inspection interval for cooling fan/ventilation openings",
    "maintenance inspection interval for cooling fan and ventilation openings",
    "inspection interval for cooling fan and ventilation openings",
    "maintenance inspection interval",
]


class NormalizationTest(unittest.TestCase):
    def test_whitespace_case_quotes_and_edge_punctuation(self):
        self.assertEqual(
            normalize_text("  “Inspect   every\n1,000 Operating Hours.”  "),
            "inspect every 1,000 operating hours",
        )
        self.assertEqual(normalize_text("‘26\u00a0V’"), "26 v")
        self.assertEqual(normalize_text("4 – 20 mA"), normalize_text("4 - 20 mA"))

    def test_keeps_meaningful_differences(self):
        self.assertNotEqual(normalize_text("1,000 hours"), normalize_text("1000 hours"))
        self.assertNotEqual(normalize_text("1.5 MPa"), normalize_text("15 MPa"))


class FindingKeyTest(unittest.TestCase):
    def test_exact_duplicate_has_same_key(self):
        copy = ContradictionVerdict.model_validate(MAINTENANCE.model_dump())
        self.assertEqual(finding_key(DOCUMENTS, MAINTENANCE), finding_key(DOCUMENTS, copy))

    def test_formatting_differences_have_same_key(self):
        reformatted = finding(
            "  Inspection   INTERVAL ",
            "“Inspect every 1,000  operating hours.”",
            "inspect every\n500 operating hours",
            reasoning="Different wording of the reasoning does not matter.",
            confidence=0.7,
        )
        self.assertEqual(finding_key(DOCUMENTS, MAINTENANCE), finding_key(DOCUMENTS, reformatted))

    def test_document_and_evidence_order_do_not_matter(self):
        reversed_evidence = MAINTENANCE.model_copy(
            update={"evidence": list(reversed(MAINTENANCE.evidence))}
        )
        self.assertEqual(
            finding_key(DOCUMENTS, MAINTENANCE), finding_key((DOC_B, DOC_A), reversed_evidence)
        )

    def test_page_and_section_do_not_matter(self):
        moved = MAINTENANCE.model_copy(update={"evidence": [
            item.model_copy(update={"page": 7, "section": "4.2 Maintenance"})
            for item in MAINTENANCE.evidence
        ]})
        self.assertEqual(finding_key(DOCUMENTS, MAINTENANCE), finding_key(DOCUMENTS, moved))

    def test_same_topic_different_evidence_differs(self):
        other = finding(
            "inspection interval",
            "inspect every 1,000 operating hours",
            "inspect every 250 operating hours",
        )
        self.assertNotEqual(finding_key(DOCUMENTS, MAINTENANCE), finding_key(DOCUMENTS, other))

    def test_extra_evidence_quote_differs(self):
        extended = MAINTENANCE.model_copy(update={"evidence": [
            *MAINTENANCE.evidence,
            MAINTENANCE.evidence[0].model_copy(update={"quote": "replace the filter"}),
        ]})
        self.assertNotEqual(finding_key(DOCUMENTS, MAINTENANCE), finding_key(DOCUMENTS, extended))

    def test_same_quotes_attributed_to_other_document_differ(self):
        swapped = MAINTENANCE.model_copy(update={"evidence": [
            MAINTENANCE.evidence[0].model_copy(update={"quote": MAINTENANCE.evidence[1].quote}),
            MAINTENANCE.evidence[1].model_copy(update={"quote": MAINTENANCE.evidence[0].quote}),
        ]})
        self.assertNotEqual(finding_key(DOCUMENTS, MAINTENANCE), finding_key(DOCUMENTS, swapped))

    def test_same_evidence_different_topic_has_same_key(self):
        keys = {
            finding_key(DOCUMENTS, MAINTENANCE.model_copy(update={"topic": topic}))
            for topic in XR500_MAINTENANCE_TOPICS
        }
        self.assertEqual(keys, {finding_key(DOCUMENTS, MAINTENANCE)})

    def test_verdict_and_documents_are_part_of_the_key(self):
        base = finding_key(DOCUMENTS, MAINTENANCE)
        self.assertNotEqual(
            base, finding_key(DOCUMENTS, MAINTENANCE.model_copy(update={"verdict": "UNCERTAIN"}))
        )
        self.assertNotEqual(base, finding_key((DOC_A, uuid.uuid4()), MAINTENANCE))

    def test_different_claims_from_same_chunks_differ(self):
        keys = {finding_key(DOCUMENTS, f) for f in (VOLTAGE, TEMPERATURE, MAINTENANCE)}
        self.assertEqual(len(keys), 3)


def fake_chunk(document_id: uuid.UUID, filename: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(), document_id=document_id, document=SimpleNamespace(filename=filename),
        text="chunk text", page_number=1, section=None, embedding=[0.0],
    )


class PipelineDeduplicationTest(unittest.TestCase):
    """run_pipeline over overlapping pairs, with Claude replies chosen per pair."""

    def setUp(self):
        # Two overlapping chunks per document, as produced by chunk overlap.
        self.a1, self.a2 = fake_chunk(DOC_A, "A.pdf"), fake_chunk(DOC_A, "A.pdf")
        self.b1, self.b2 = fake_chunk(DOC_B, "B.pdf"), fake_chunk(DOC_B, "B.pdf")
        self.db = mock.MagicMock(name="db")

    def pair(self, chunk_a, chunk_b) -> SimpleNamespace:
        return SimpleNamespace(id=uuid.uuid4(), chunk_a_id=chunk_a.id, chunk_b_id=chunk_b.id)

    def run_with(self, replies: dict, stored_keys=(), store_side_effect=None):
        """replies maps each pair id in self.pairs to the findings Claude returns for it."""
        pairs_by_chunk = {(p.chunk_a_id, p.chunk_b_id): p for p in self.pairs}
        # Each chunk has distinct text, so compare() can tell which pair it is called for.
        chunk_for_text = {}
        for chunk in (self.a1, self.a2, self.b1, self.b2):
            chunk.text = f"text of {chunk.id}"
            chunk_for_text[chunk.text] = chunk.id

        def compare(a, b):
            pair = pairs_by_chunk[(chunk_for_text[a.text], chunk_for_text[b.text])]
            return replies[pair.id], {"id": f"raw-{pair.id}"}

        retriever = mock.MagicMock()
        retriever.retrieve_for_chunk.return_value = []
        store = mock.MagicMock(name="store_contradiction_result", side_effect=store_side_effect)
        patches = {
            "_load_chunks": mock.MagicMock(return_value=[self.a1, self.a2, self.b1, self.b2]),
            "_ensure_entities_and_embeddings": mock.MagicMock(),
            "load_entity_types": mock.MagicMock(return_value={}),
            "generate_candidates": mock.MagicMock(),
            "store_candidates": mock.MagicMock(return_value=self.pairs),
            "_load_entities": mock.MagicMock(return_value={}),
            "_pairs_with_results": mock.MagicMock(return_value=set()),
            "_stored_finding_keys": mock.MagicMock(return_value=set(stored_keys)),
            "CrossDocumentRetriever": mock.MagicMock(return_value=retriever),
            "compare_statements_with_raw": mock.MagicMock(side_effect=compare),
            "store_contradiction_result": store,
        }
        with mock.patch.multiple(pipeline, **patches):
            summary = pipeline.run_pipeline(self.db, list(DOCUMENTS))
        return summary, store

    def stored(self, store) -> list[tuple[uuid.UUID, str]]:
        return [(c.args[1], c.args[2].topic) for c in store.call_args_list]

    def test_exact_duplicate_from_another_pair_is_skipped(self):
        p1, p2 = self.pair(self.a1, self.b1), self.pair(self.a2, self.b1)
        self.pairs = [p1, p2]
        copy = ContradictionVerdict.model_validate(MAINTENANCE.model_dump())
        summary, store = self.run_with({p1.id: [MAINTENANCE], p2.id: [copy]})

        self.assertEqual(self.stored(store), [(p1.id, "inspection interval")])
        self.assertEqual((summary.results_stored, summary.duplicates_skipped), (1, 1))

    def test_normalized_duplicate_is_skipped(self):
        p1, p2 = self.pair(self.a1, self.b1), self.pair(self.a1, self.b2)
        self.pairs = [p1, p2]
        reformatted = finding(
            "Inspection Interval",
            "Inspect every 1,000 operating  hours.",
            "“inspect every 500\noperating hours”",
        )
        summary, store = self.run_with({p1.id: [MAINTENANCE], p2.id: [reformatted]})

        self.assertEqual(self.stored(store), [(p1.id, "inspection interval")])
        self.assertEqual(summary.duplicates_skipped, 1)

    def test_same_evidence_different_topic_is_skipped(self):
        p1, p2 = self.pair(self.a1, self.b1), self.pair(self.a2, self.b2)
        self.pairs = [p1, p2]
        renamed = MAINTENANCE.model_copy(update={"topic": "maintenance inspection interval"})
        summary, store = self.run_with({p1.id: [MAINTENANCE], p2.id: [renamed]})

        self.assertEqual(self.stored(store), [(p1.id, "inspection interval")])
        self.assertEqual((summary.results_stored, summary.duplicates_skipped), (1, 1))

    def test_same_topic_different_evidence_is_stored(self):
        p1, p2 = self.pair(self.a1, self.b1), self.pair(self.a2, self.b2)
        self.pairs = [p1, p2]
        other = finding(
            "inspection interval",
            "inspect every 1,000 operating hours",
            "inspect every 250 operating hours",
        )
        summary, store = self.run_with({p1.id: [MAINTENANCE], p2.id: [other]})

        self.assertEqual(store.call_count, 2)
        self.assertEqual((summary.results_stored, summary.duplicates_skipped), (2, 0))

    def test_different_claims_from_same_pair_are_all_stored(self):
        p1 = self.pair(self.a1, self.b1)
        self.pairs = [p1]
        summary, store = self.run_with({p1.id: [VOLTAGE, TEMPERATURE, MAINTENANCE]})

        self.assertEqual(
            [topic for _, topic in self.stored(store)],
            ["supply voltage", "maximum ambient temperature", "inspection interval"],
        )
        self.assertEqual((summary.results_stored, summary.duplicates_skipped), (3, 0))

    def test_repeated_finding_within_one_reply_is_stored_once(self):
        p1 = self.pair(self.a1, self.b1)
        self.pairs = [p1]
        summary, store = self.run_with({p1.id: [MAINTENANCE, VOLTAGE, MAINTENANCE]})

        self.assertEqual(store.call_count, 2)
        self.assertEqual((summary.results_stored, summary.duplicates_skipped), (2, 1))

    def test_xr500_maintenance_through_overlapping_pairs_is_stored_once(self):
        pairs = [
            self.pair(self.a1, self.b1),
            self.pair(self.a2, self.b1),
            self.pair(self.a1, self.b2),
            self.pair(self.a2, self.b2),
        ]
        self.pairs = pairs
        first, second, third, fourth = XR500_MAINTENANCE_TOPICS
        variants = [
            finding(first, "inspect every 1,000 operating hours",
                    "inspect every 500 operating hours"),
            finding(second, "Inspect every 1,000 operating hours.",
                    "Inspect every 500 operating hours."),
            finding(third, "“inspect every 1,000 operating hours”",
                    "inspect every 500 operating hours"),
            finding(fourth, "inspect every\n1,000 operating hours",
                    "inspect  every 500 operating hours"),
        ]
        replies = {
            pairs[0].id: [VOLTAGE, variants[0]],
            pairs[1].id: [variants[1], TEMPERATURE],
            pairs[2].id: [variants[2]],
            pairs[3].id: [variants[3], VOLTAGE],
        }
        summary, store = self.run_with(replies)

        self.assertEqual(
            self.stored(store),
            [
                (pairs[0].id, "supply voltage"),
                (pairs[0].id, first),
                (pairs[1].id, "maximum ambient temperature"),
            ],
        )
        self.assertEqual(summary.candidates_processed, 4)
        self.assertEqual((summary.results_stored, summary.duplicates_skipped), (3, 4))
        self.assertEqual(summary.errors, 0)

    def test_previously_stored_finding_is_skipped_and_others_are_stored(self):
        p1 = self.pair(self.a1, self.b1)
        self.pairs = [p1]
        summary, store = self.run_with(
            {p1.id: [MAINTENANCE, VOLTAGE]},
            stored_keys={finding_key(DOCUMENTS, MAINTENANCE)},
        )

        self.assertEqual(self.stored(store), [(p1.id, "supply voltage")])
        self.assertEqual((summary.results_stored, summary.duplicates_skipped), (1, 1))

    def test_rolled_back_pair_does_not_block_later_duplicates(self):
        p1, p2 = self.pair(self.a1, self.b1), self.pair(self.a2, self.b1)
        self.pairs = [p1, p2]
        summary, store = self.run_with(
            {p1.id: [MAINTENANCE, VOLTAGE], p2.id: [MAINTENANCE]},
            store_side_effect=[None, RuntimeError("database down"), None],
        )

        self.assertEqual(
            self.stored(store),
            [(p1.id, "inspection interval"), (p1.id, "supply voltage"),
             (p2.id, "inspection interval")],
        )
        self.db.rollback.assert_called_once()
        self.assertEqual((summary.results_stored, summary.duplicates_skipped), (1, 0))
        self.assertEqual(summary.errors, 1)


class StoredFindingKeysTest(unittest.TestCase):
    """_stored_finding_keys against PostgreSQL; nothing is committed."""

    def test_stored_result_key_matches_new_finding_key(self):
        with SessionLocal() as db:
            try:
                doc_a, doc_b = Document(filename="A.pdf"), Document(filename="B.pdf")
                db.add_all([doc_a, doc_b])
                db.flush()
                chunk_a = Chunk(document_id=doc_a.id, text="inspect every 1,000 operating hours")
                chunk_b = Chunk(document_id=doc_b.id, text="inspect every 500 operating hours")
                db.add_all([chunk_a, chunk_b])
                db.flush()
                pair = CandidatePair(chunk_a_id=chunk_a.id, chunk_b_id=chunk_b.id, method="test")
                db.add(pair)
                db.flush()
                store_contradiction_result(db, pair.id, MAINTENANCE)
                store_contradiction_result(db, pair.id, VOLTAGE)

                chunk_by_id = {chunk_a.id: chunk_a, chunk_b.id: chunk_b}
                keys = pipeline._stored_finding_keys(db, chunk_by_id)

                documents = (doc_a.id, doc_b.id)
                reformatted = finding(
                    XR500_MAINTENANCE_TOPICS[0],
                    "Inspect every 1,000 operating hours.",
                    "inspect every 500 operating hours",
                )
                self.assertEqual(
                    keys, {finding_key(documents, MAINTENANCE), finding_key(documents, VOLTAGE)}
                )
                self.assertIn(finding_key(documents, reformatted), keys)
                self.assertNotIn(finding_key(documents, TEMPERATURE), keys)
                self.assertEqual(
                    db.query(ContradictionResult)
                    .filter(ContradictionResult.candidate_pair_id == pair.id)
                    .count(),
                    2,
                )
            finally:
                db.rollback()


if __name__ == "__main__":
    unittest.main()
