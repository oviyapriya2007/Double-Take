"""Unit tests for the technical-claim compatibility retrieval signal.

    python -m unittest discover -s tests
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.nlp.technical_claims import (  # noqa: E402
    INTERVAL,
    QUANTITY,
    SPECIFICATION,
    extract_technical_claims,
    technical_compatibility,
)

STRONG = 0.5
"""Comparable claims should score at least this."""
WEAK = 0.2
"""Unrelated claims should score at most this."""


def compatibility(text_a: str, text_b: str) -> float:
    return technical_compatibility(extract_technical_claims(text_a), extract_technical_claims(text_b))


class ExtractionTest(unittest.TestCase):
    def test_quantity_with_unit_and_limit_wording(self):
        [claim] = extract_technical_claims("Maximum shaft speed: 3000 rpm")
        self.assertEqual((claim.kind, claim.unit, claim.framed), (QUANTITY, "rpm", True))
        self.assertIn("shaft", claim.context)
        self.assertNotIn("maximum", claim.context)

    def test_range_is_one_framed_claim(self):
        [claim] = extract_technical_claims("Loop current 4 to 20 mA")
        self.assertEqual((claim.kind, claim.unit, claim.framed), (QUANTITY, "ma", True))
        self.assertEqual(claim.text, "4 to 20 mA")

    def test_interval_with_schedule_wording(self):
        [claim] = extract_technical_claims("Lubricate the main bearing every 500 hours.")
        self.assertEqual((claim.kind, claim.unit, claim.framed), (INTERVAL, "hour", True))
        self.assertIn("bearing", claim.context)

    def test_specification_term_next_to_a_quantity(self):
        claims = extract_technical_claims("Relay contact: normally-open, rated 2 A")
        self.assertIn((SPECIFICATION, "normally-open"), {(c.kind, c.term) for c in claims})

    def test_ignores_dates_identifiers_and_section_numbers(self):
        text = ("Revision 3, issued 12 March 2024. Model AB-1200 uses cell CR2032.\n"
                "3.2 Air Filter\nFirmware v2.4.1 at 192.168.1.20")
        self.assertEqual(extract_technical_claims(text), [])


class CompatibilityTest(unittest.TestCase):
    def test_different_numeric_limits_for_the_same_quantity(self):
        score = compatibility(
            "Maximum shaft speed: 3000 rpm under continuous load.",
            "The shaft speed must not exceed 3600 rpm.",
        )
        self.assertGreaterEqual(score, STRONG)

    def test_two_ranges_for_the_same_measurement(self):
        score = compatibility(
            "Sensor output signal range: 4 to 20 mA",
            "Accepted sensor signal 3.8–20.5 mA",
        )
        self.assertGreaterEqual(score, STRONG)

    def test_two_replacement_intervals_in_different_units(self):
        score = compatibility(
            "Replace the drive belt every 2,000 hours.",
            "Drive belt replacement interval: 6 months",
        )
        self.assertGreaterEqual(score, STRONG)

    def test_categorical_specifications_that_differ(self):
        score = compatibility(
            "Install a 3 mm stainless-steel gasket on the pump flange.",
            "Pump flange gasket: 3 mm carbon-steel",
        )
        self.assertGreaterEqual(score, STRONG)

    def test_unrelated_numbers_with_different_units(self):
        score = compatibility(
            "Torque the cover bolts to 25 N·m.",
            "The supplied cable is 25 m long and weighs 4 kg.",
        )
        self.assertLessEqual(score, WEAK)

    def test_unrelated_dates(self):
        score = compatibility(
            "Effective date: January 15, 2026. Revision 4.",
            "Approved on 3 March 2021 by the review board.",
        )
        self.assertLessEqual(score, WEAK)

    def test_same_unit_but_unrelated_meaning(self):
        score = compatibility(
            "Store spare cartridges in a refrigerator at 5°C.",
            "The display backlight switches off above 60°C.",
        )
        self.assertLessEqual(score, WEAK)

    def test_intervals_for_unrelated_components(self):
        score = compatibility(
            "Replace the air intake filter every 6 months.",
            "Recalibrate the load cell every 12 months.",
        )
        self.assertLessEqual(score, WEAK)

    def test_duration_is_not_compared_with_service_interval(self):
        score = compatibility(
            "The main relay opens within 50 ms of a fault.",
            "Main relay replacement: every 24 months.",
        )
        self.assertEqual(score, 0.0)

    def test_score_is_symmetric_and_bounded(self):
        a = "Maximum shaft speed: 3000 rpm"
        b = "The shaft speed must not exceed 3600 rpm."
        self.assertEqual(compatibility(a, b), compatibility(b, a))
        self.assertLessEqual(compatibility(a, b), 1.0)
        self.assertEqual(compatibility(a, ""), 0.0)


class CombinedScoreTest(unittest.TestCase):
    def test_combined_score_stays_normalised(self):
        from app.retrieval.candidates import combined_score

        self.assertAlmostEqual(combined_score(1, 1, 1, 1), 1.0)
        self.assertAlmostEqual(combined_score(0, 0, 0, 0), 0.0)
        self.assertGreater(combined_score(0.2, 0.3, 0.2, 1.0), combined_score(0.2, 0.3, 0.2, 0.0))


if __name__ == "__main__":
    unittest.main()
