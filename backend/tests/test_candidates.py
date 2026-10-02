"""Tests for candidate selection: score floor, per-document-pair limit and coverage fallback.

    python -m unittest tests.test_candidates

Offline: chunks are stand-ins with only the attributes selection and scoring read.
"""

import math
import os
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.retrieval import candidates  # noqa: E402
from app.retrieval.candidates import (  # noqa: E402
    DEFAULT_MIN_COMBINED_SCORE,
    MAX_PAIRS_PER_DOCUMENT_PAIR,
    Candidate,
    combined_score,
    configured_min_combined_score,
    generate_candidates,
    select_with_document_coverage,
)

DOC_A, DOC_B, DOC_C, DOC_D = (uuid.uuid4() for _ in range(4))


def chunk(document_id: uuid.UUID, text: str = "", embedding=None) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), document_id=document_id, text=text, embedding=embedding)


def pair(document_a: uuid.UUID, document_b: uuid.UUID, score: float) -> Candidate:
    return Candidate(chunk(document_a), chunk(document_b), 0.0, 0.0, 0.0, 0.0, score)


def ranked(*pairs: Candidate) -> list[Candidate]:
    return sorted(pairs, key=lambda c: -c.combined_score)


def select(pairs: list[Candidate], max_candidates: int = 60, **kwargs) -> list[Candidate]:
    return select_with_document_coverage(ranked(*pairs), max_candidates, **kwargs)


def scores(selected: list[Candidate]) -> list[float]:
    return [c.combined_score for c in selected]


class ScoreFloorTest(unittest.TestCase):
    def test_pair_at_or_above_floor_survives(self):
        selected = select([pair(DOC_A, DOC_B, 0.40), pair(DOC_A, DOC_B, 0.15)])
        self.assertEqual(scores(selected), [0.40, 0.15])

    def test_pair_below_floor_is_removed(self):
        selected = select([pair(DOC_A, DOC_B, 0.50), pair(DOC_A, DOC_B, 0.149)])
        self.assertEqual(scores(selected), [0.50])

    def test_small_dataset_does_not_readd_weak_pairs(self):
        strong = [pair(DOC_A, DOC_B, 0.6), pair(DOC_A, DOC_C, 0.3)]
        weak = [pair(d1, d2, s) for d1, d2, s in [
            (DOC_A, DOC_B, 0.14), (DOC_A, DOC_C, 0.12), (DOC_B, DOC_C, 0.10),
            (DOC_B, DOC_C, 0.08), (DOC_A, DOC_B, 0.05), (DOC_A, DOC_C, 0.01),
        ]]
        selected = select(strong + weak)
        self.assertEqual(scores(selected), [0.6, 0.3])

    def test_custom_min_score(self):
        selected = select([pair(DOC_A, DOC_B, 0.5), pair(DOC_A, DOC_B, 0.25)], min_score=0.3)
        self.assertEqual(scores(selected), [0.5])


class CoverageFallbackTest(unittest.TestCase):
    def test_document_without_eligible_pair_gets_its_best_original_pair(self):
        best_for_c = pair(DOC_B, DOC_C, 0.12)
        selected = select([
            pair(DOC_A, DOC_B, 0.6), pair(DOC_A, DOC_C, 0.10), best_for_c, pair(DOC_B, DOC_C, 0.05),
        ])
        self.assertEqual(scores(selected), [0.6, 0.12])
        self.assertIs(selected[1], best_for_c)

    def test_fallback_does_not_duplicate_pairs(self):
        shared = pair(DOC_C, DOC_D, 0.10)
        selected = select([
            pair(DOC_A, DOC_B, 0.6), shared, pair(DOC_A, DOC_C, 0.05), pair(DOC_B, DOC_D, 0.04),
        ])
        self.assertEqual(scores(selected), [0.6, 0.10])
        self.assertEqual(len({id(c) for c in selected}), len(selected))

    def test_no_fallback_when_every_document_is_covered(self):
        selected = select([pair(DOC_A, DOC_B, 0.6), pair(DOC_B, DOC_C, 0.2), pair(DOC_A, DOC_C, 0.1)])
        self.assertEqual(scores(selected), [0.6, 0.2])

    def test_fallback_takes_room_from_weakest_redundant_pair_when_budget_is_full(self):
        eligible = [pair(DOC_A, DOC_B, 0.9 - n / 100) for n in range(5)]
        eligible += [pair(DOC_A, DOC_C, 0.5 - n / 100) for n in range(5)]
        fallback = pair(DOC_B, DOC_D, 0.05)
        selected = select(eligible + [fallback], max_candidates=10)
        self.assertEqual(len(selected), 10)
        self.assertIn(fallback, selected)
        self.assertNotIn(eligible[-1], selected)

    def test_fallback_never_exceeds_max_candidates(self):
        selected = select([pair(DOC_A, DOC_B, 0.6), pair(DOC_C, DOC_D, 0.1)], max_candidates=1)
        self.assertEqual(scores(selected), [0.6])


class BudgetAndLimitTest(unittest.TestCase):
    def test_max_candidates_is_respected(self):
        documents = [uuid.uuid4() for _ in range(6)]
        pairs = [
            pair(documents[i], documents[j], 0.2 + (i + j + k) / 100)
            for i in range(6) for j in range(i + 1, 6) for k in range(5)
        ]
        self.assertEqual(len(select(pairs, max_candidates=60)), 60)
        self.assertEqual(len(select(pairs, max_candidates=7)), 7)

    def test_per_document_pair_limit_is_respected(self):
        pairs = [pair(DOC_A, DOC_B, 0.9 - n / 100) for n in range(8)]
        pairs += [pair(DOC_A, DOC_C, 0.3), pair(DOC_A, DOC_C, 0.2)]
        selected = select(pairs)
        per_document_pair = [frozenset((c.chunk_a.document_id, c.chunk_b.document_id)) for c in selected]
        self.assertEqual(per_document_pair.count(frozenset((DOC_A, DOC_B))), MAX_PAIRS_PER_DOCUMENT_PAIR)
        self.assertEqual(per_document_pair.count(frozenset((DOC_A, DOC_C))), 2)
        self.assertEqual(len(selected), MAX_PAIRS_PER_DOCUMENT_PAIR + 2)

    def test_result_is_best_first(self):
        selected = select([
            pair(DOC_A, DOC_B, 0.6), pair(DOC_A, DOC_B, 0.3), pair(DOC_C, DOC_D, 0.1),
        ])
        self.assertEqual(scores(selected), sorted(scores(selected), reverse=True))


class MinCombinedScoreConfigTest(unittest.TestCase):
    def test_default_is_0_15(self):
        self.assertEqual(DEFAULT_MIN_COMBINED_SCORE, 0.15)
        with mock.patch.dict(os.environ, clear=True):
            self.assertEqual(configured_min_combined_score(), 0.15)
        with mock.patch.dict(os.environ, {"MIN_COMBINED_SCORE": "  "}):
            self.assertEqual(configured_min_combined_score(), 0.15)

    def test_can_be_configured_from_environment(self):
        with mock.patch.dict(os.environ, {"MIN_COMBINED_SCORE": "0.3"}):
            self.assertEqual(configured_min_combined_score(), 0.3)

    def test_invalid_value_is_rejected(self):
        with mock.patch.dict(os.environ, {"MIN_COMBINED_SCORE": "high"}):
            with self.assertRaises(ValueError):
                configured_min_combined_score()

    def test_selection_uses_configured_floor_by_default(self):
        self.assertEqual(candidates.MIN_COMBINED_SCORE, configured_min_combined_score())


class GenerateCandidatesTest(unittest.TestCase):
    """Scoring is unchanged: only the embedding signal is non-zero, so combined = 0.36 x cosine."""

    def test_floor_and_fallback_keep_scoring_fields(self):
        a = chunk(DOC_A, "pump pressure", [1.0, 0.0])
        b = chunk(DOC_B, "valve housing", [1.0, 0.0])
        c = chunk(DOC_C, "motor winding", [0.3, math.sqrt(1 - 0.09)])
        selection = generate_candidates([a, b, c], {}, min_score=0.15)

        self.assertEqual(selection.cross_document_pairs, 3)
        self.assertEqual(selection.scored_pairs, 3)
        self.assertEqual([(x.chunk_a, x.chunk_b) for x in selection.candidates], [(a, b), (a, c)])
        for candidate in selection.candidates:
            self.assertEqual(
                candidate.combined_score,
                combined_score(candidate.tfidf_score, candidate.embedding_score,
                               candidate.entity_overlap, candidate.technical_compatibility),
            )
        strong, fallback = selection.candidates
        self.assertAlmostEqual(strong.embedding_score, 1.0)
        self.assertAlmostEqual(strong.combined_score, 0.36)
        self.assertAlmostEqual(fallback.combined_score, 0.36 * 0.3)

    def test_no_floor_returns_every_pair(self):
        a = chunk(DOC_A, "pump pressure", [1.0, 0.0])
        b = chunk(DOC_B, "valve housing", [0.0, 1.0])
        c = chunk(DOC_C, "motor winding", [0.0, 1.0])
        selection = generate_candidates([a, b, c], {}, max_candidates=9, min_score=-math.inf)
        self.assertEqual(len(selection.candidates), 3)


if __name__ == "__main__":
    unittest.main()
