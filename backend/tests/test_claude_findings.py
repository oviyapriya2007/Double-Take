"""Offline tests for multi-finding Claude analysis and how the pipeline stores findings.

    python -m unittest discover -s tests

Claude, the database and the NLP/retrieval steps are replaced by fakes, so no API key,
database or network is needed.
"""

import json
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import claude_analysis, pipeline  # noqa: E402
from app.services.claude_analysis import (  # noqa: E402
    RETRY_INSTRUCTION,
    ClaudeResponseError,
    ContradictionVerdict,
    Statement,
    compare_statements_with_raw,
)

A = Statement(
    text="XR-500 supply voltage: 26 V. Maximum ambient temperature: 45°C. "
    "Service interval: every 1,000 operating hours.",
    document="A.pdf",
    page=1,
)
B = Statement(
    text="XR-500 supply voltage: 28 V. Maximum ambient temperature: 50°C. "
    "Service interval: every 500 operating hours.",
    document="B.pdf",
    page=2,
)


def finding(topic: str, quote_a: str, quote_b: str, verdict: str = "CONTRADICTION") -> dict:
    return {
        "topic": topic,
        "verdict": verdict,
        "reasoning": f"{quote_a} and {quote_b} cannot both be true.",
        "confidence": 0.9,
        "evidence": [
            {"document": "A.pdf", "section": None, "page": 1, "quote": quote_a},
            {"document": "B.pdf", "section": None, "page": 2, "quote": quote_b},
        ],
    }


VOLTAGE = finding("supply voltage", "26 V", "28 V")
TEMPERATURE = finding("maximum ambient temperature", "45°C", "50°C")
SERVICE = finding("service interval", "1,000 operating hours", "500 operating hours")


def reply(*findings: dict) -> str:
    return json.dumps({"findings": list(findings)})


class FakeClaude:
    """Stands in for _ask_claude: returns canned replies and records the prompts sent."""

    def __init__(self, *replies: str):
        self.pending = list(replies)
        self.prompts: list[str] = []

    def __call__(self, content: str) -> tuple[str, dict]:
        self.prompts.append(content)
        return self.pending.pop(0), {"id": f"fake-{len(self.prompts)}"}


class ClaudeFindingsTest(unittest.TestCase):
    def compare(self, *replies: str):
        fake = FakeClaude(*replies)
        with mock.patch.object(claude_analysis, "_ask_claude", fake):
            try:
                return compare_statements_with_raw(A, B), fake.prompts
            except ValueError as exc:
                return exc, fake.prompts

    def test_zero_findings(self):
        (findings, raw), prompts = self.compare(reply())
        self.assertEqual(findings, [])
        self.assertEqual(raw, {"id": "fake-1"})
        self.assertEqual(len(prompts), 1)

    def test_one_finding(self):
        (findings, _), prompts = self.compare(reply(VOLTAGE))
        self.assertEqual(len(prompts), 1)
        [only] = findings
        self.assertIsInstance(only, ContradictionVerdict)
        self.assertEqual((only.topic, only.verdict), ("supply voltage", "CONTRADICTION"))
        self.assertEqual([e.quote for e in only.evidence], ["26 V", "28 V"])

    def test_multiple_findings_keep_order_and_evidence(self):
        (findings, _), prompts = self.compare(reply(VOLTAGE, TEMPERATURE, SERVICE))
        self.assertEqual(len(prompts), 1)
        self.assertEqual(
            [f.topic for f in findings],
            ["supply voltage", "maximum ambient temperature", "service interval"],
        )
        self.assertEqual(
            [f.model_dump() for f in findings],
            [ContradictionVerdict.model_validate(f).model_dump()
             for f in (VOLTAGE, TEMPERATURE, SERVICE)],
        )

    def test_mixed_verdicts_are_kept(self):
        consistent = finding("product name", "XR-500", "XR-500", verdict="CONSISTENT")
        (findings, _), _ = self.compare(reply(VOLTAGE, consistent))
        self.assertEqual([f.verdict for f in findings], ["CONTRADICTION", "CONSISTENT"])

    def test_invalid_finding_is_retried_once(self):
        bad_verdict = reply(VOLTAGE, {**TEMPERATURE, "verdict": "MAYBE"})
        missing_field = reply({k: v for k, v in VOLTAGE.items() if k != "reasoning"})
        bad_confidence = reply({**VOLTAGE, "confidence": 1.5})
        old_single_shape = json.dumps(VOLTAGE)
        not_a_list = json.dumps({"findings": VOLTAGE})
        for label, bad in (
            ("invalid verdict", bad_verdict),
            ("missing field", missing_field),
            ("confidence out of range", bad_confidence),
            ("single verdict without findings", old_single_shape),
            ("findings not a list", not_a_list),
            ("not JSON", "The statements contradict each other."),
        ):
            with self.subTest(label):
                (findings, raw), prompts = self.compare(bad, reply(VOLTAGE, TEMPERATURE))
                self.assertEqual(len(prompts), 2)
                self.assertNotIn(RETRY_INSTRUCTION, prompts[0])
                self.assertTrue(prompts[1].endswith(RETRY_INSTRUCTION))
                self.assertEqual(len(findings), 2)
                self.assertEqual(raw, {"id": "fake-2"})

    def test_second_invalid_reply_raises(self):
        bad = reply({**VOLTAGE, "verdict": "MAYBE"})
        outcome, prompts = self.compare(bad, bad)
        self.assertEqual(len(prompts), 2)
        self.assertIsInstance(outcome, ClaudeResponseError)

    def test_fabricated_evidence_in_any_finding_is_rejected_without_retry(self):
        fabricated = finding("maximum ambient temperature", "45°C", "55°C")
        outcome, prompts = self.compare(reply(VOLTAGE, fabricated))
        self.assertEqual(len(prompts), 1)
        self.assertIsInstance(outcome, ValueError)
        self.assertNotIsInstance(outcome, ClaudeResponseError)
        self.assertIn("55°C", str(outcome))

    def test_prompt_asks_for_findings_list(self):
        self.assertIn('"findings"', claude_analysis.SYSTEM_PROMPT)
        prompt = claude_analysis.build_user_prompt(A, B)
        self.assertIn("every independently comparable technical claim", prompt)
        self.assertIn("Do not stop after the first", prompt)


def fake_chunk(document_id: uuid.UUID, filename: str, text: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        document_id=document_id,
        document=SimpleNamespace(filename=filename),
        text=text,
        page_number=1,
        section=None,
        embedding=[0.0],
    )


class PipelineStoresFindingsTest(unittest.TestCase):
    """run_pipeline with every collaborator faked except the per-pair analysis loop."""

    def setUp(self):
        self.chunk_a = fake_chunk(uuid.uuid4(), "A.pdf", A.text)
        self.chunk_b = fake_chunk(uuid.uuid4(), "B.pdf", B.text)
        self.pair = SimpleNamespace(
            id=uuid.uuid4(), chunk_a_id=self.chunk_a.id, chunk_b_id=self.chunk_b.id
        )
        self.db = mock.MagicMock(name="db")
        self.raw_response = {"id": "fake-raw"}

    def run_with(self, compare_side_effect, store_side_effect=None):
        retriever = mock.MagicMock()
        retriever.retrieve_for_chunk.return_value = []
        store = mock.MagicMock(name="store_contradiction_result", side_effect=store_side_effect)
        patches = {
            "_load_chunks": mock.MagicMock(return_value=[self.chunk_a, self.chunk_b]),
            "_ensure_entities_and_embeddings": mock.MagicMock(),
            "load_entity_types": mock.MagicMock(return_value={}),
            "generate_candidates": mock.MagicMock(),
            "store_candidates": mock.MagicMock(return_value=[self.pair]),
            "_load_entities": mock.MagicMock(return_value={}),
            "_pairs_with_results": mock.MagicMock(return_value=set()),
            "CrossDocumentRetriever": mock.MagicMock(return_value=retriever),
            "compare_statements_with_raw": mock.MagicMock(side_effect=compare_side_effect),
            "store_contradiction_result": store,
        }
        with mock.patch.multiple(pipeline, **patches):
            summary = pipeline.run_pipeline(self.db, [self.chunk_a.document_id, self.chunk_b.document_id])
        return summary, store, patches["compare_statements_with_raw"]

    def test_each_finding_is_stored_individually(self):
        findings = [ContradictionVerdict.model_validate(f) for f in (VOLTAGE, TEMPERATURE, SERVICE)]
        summary, store, compare = self.run_with(lambda a, b: (findings, self.raw_response))

        compare.assert_called_once()
        self.assertEqual(
            store.call_args_list,
            [mock.call(self.db, self.pair.id, f, self.raw_response) for f in findings],
        )
        self.assertEqual(summary.candidates_processed, 1)
        self.assertEqual(summary.results_stored, 3)
        self.assertEqual(summary.errors, 0)
        self.db.rollback.assert_not_called()

    def test_zero_findings_store_nothing(self):
        summary, store, compare = self.run_with(lambda a, b: ([], self.raw_response))

        compare.assert_called_once()
        store.assert_not_called()
        self.assertEqual((summary.results_stored, summary.errors), (0, 0))

    def test_storage_failure_rolls_back_the_whole_pair(self):
        findings = [ContradictionVerdict.model_validate(f) for f in (VOLTAGE, TEMPERATURE)]
        summary, store, _ = self.run_with(
            lambda a, b: (findings, self.raw_response),
            store_side_effect=[None, RuntimeError("database down")],
        )

        self.assertEqual(store.call_count, 2)
        self.assertEqual((summary.results_stored, summary.errors), (0, 1))
        self.db.rollback.assert_called_once()

    def test_claude_failure_is_counted_as_error(self):
        def fail(a, b):
            raise ClaudeResponseError("still invalid")

        summary, store, _ = self.run_with(fail)

        store.assert_not_called()
        self.assertEqual((summary.results_stored, summary.errors), (0, 1))


if __name__ == "__main__":
    unittest.main()
