from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from jobly_demo import DemoProfile, FixtureSource, evaluate_expected, hard_gate, normalise_record, run_pipeline


ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures" / "jobs.json"


class PublicDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = FixtureSource(FIXTURES)
        cls.result = run_pipeline(cls.source)

    def test_pipeline_is_source_independent(self) -> None:
        self.assertEqual(self.result["source_mode"], "synthetic-fixture")

    def test_duplicate_repost_is_collapsed(self) -> None:
        self.assertEqual(self.result["summary"]["duplicates_collapsed"], 1)
        rows = self.result["review_queue"]
        self.assertTrue(any("fixture-006" in row["alternate_source_ids"] for row in rows))

    def test_contract_role_fails_hard_gate(self) -> None:
        record = next(row for row in self.source.fetch() if row["source_id"] == "fixture-008")
        rejection = hard_gate(
            normalise_record(record),
            DemoProfile(),
            datetime(2026, 10, 12, tzinfo=timezone.utc),
        )
        self.assertIn("permanent full-time", rejection)

    def test_out_of_region_role_fails_hard_gate(self) -> None:
        rejected = {row["source_id"]: row["reason"] for row in self.result["rejected"]}
        self.assertIn("outside", rejected["fixture-007"])

    def test_salary_floor_is_deterministic(self) -> None:
        rejected = {row["source_id"]: row["reason"] for row in self.result["rejected"]}
        self.assertIn("salary", rejected["fixture-004"].casefold())

    def test_ranked_rows_include_an_explanation(self) -> None:
        self.assertTrue(all("." in str(row["explanation"]) for row in self.result["review_queue"]))

    def test_expected_outcomes_form_a_golden_set(self) -> None:
        evaluation = evaluate_expected(self.result, self.source)
        self.assertEqual(evaluation["failed"], 0, json.dumps(evaluation["checks"], indent=2))

    def test_pipeline_output_is_reproducible(self) -> None:
        second = run_pipeline(self.source)
        self.assertEqual(self.result["reproducibility_hash"], second["reproducibility_hash"])


if __name__ == "__main__":
    unittest.main()
