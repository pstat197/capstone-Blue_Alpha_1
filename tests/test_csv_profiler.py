from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from backend.app.services.csv_profiler import profile_csv
from backend.app.services.example_datasets import blank_template_csv, runnable_demo_csv, schema_preview_csv


def _profile_csv_text(csv_text: str, filename: str = "test.csv"):
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / filename
        path.write_text(csv_text, encoding="utf-8")
        return profile_csv("upload_test", filename, path)


def _check_status(profile, group: str, code: str) -> str:
    readiness = getattr(profile, group)
    for check in readiness.checks:
        if check.code == code:
            return check.status
    raise AssertionError(f"Check not found: {group}.{code}")


def _check_message(profile, group: str, code: str) -> str:
    readiness = getattr(profile, group)
    for check in readiness.checks:
        if check.code == code:
            return check.message
    raise AssertionError(f"Check not found: {group}.{code}")


class CsvProfilerReadinessTests(unittest.TestCase):
    def test_tiny_preview_schema_passes_but_modeling_fails(self):
        profile = _profile_csv_text(schema_preview_csv(), "meridian_schema_preview.csv")

        self.assertEqual(profile.row_count, 3)
        self.assertEqual(profile.schema_readiness.status, "valid")
        self.assertEqual(_check_status(profile, "modeling_readiness", "enough_history"), "error")
        self.assertIn("not large enough for Meridian modeling", _check_message(profile, "modeling_readiness", "enough_history"))

    def test_blank_template_has_headers_but_no_modeling_rows(self):
        profile = _profile_csv_text(blank_template_csv(), "meridian_blank_template.csv")

        self.assertEqual(profile.row_count, 0)
        self.assertEqual(profile.schema_readiness.status, "valid")
        self.assertEqual(_check_status(profile, "modeling_readiness", "enough_history"), "error")
        self.assertIn("headers but no data rows", _check_message(profile, "modeling_readiness", "enough_history"))

    def test_runnable_demo_passes_schema_and_modeling_readiness(self):
        profile = _profile_csv_text(runnable_demo_csv(), "meridian_runnable_demo_156_weeks.csv")

        self.assertEqual(profile.row_count, 156)
        self.assertEqual(profile.schema_readiness.status, "valid")
        self.assertEqual(profile.modeling_readiness.status, "valid")
        self.assertEqual(_check_status(profile, "modeling_readiness", "weekly_spacing"), "valid")
        self.assertEqual(_check_status(profile, "modeling_readiness", "high_correlation"), "valid")

    def test_missing_spend_pair_fails_schema_matching_check(self):
        csv_text = "\n".join(
            [
                "date,subscriptions,revenue_per_subscription,meta_impressions,promo",
                *[
                    f"2024-01-{day:02d},{1000 + day},42.50,{100000 + day * 1000},0.1"
                    for day in range(1, 15, 7)
                ],
            ]
        )
        profile = _profile_csv_text(csv_text, "missing_spend.csv")

        self.assertEqual(_check_status(profile, "schema_readiness", "media_columns"), "valid")
        self.assertEqual(_check_status(profile, "schema_readiness", "matching_spend_columns"), "error")

    def test_highly_correlated_csv_warns_about_multicollinearity(self):
        rows = ["date,subscriptions,revenue_per_subscription,meta_impressions,meta_spend,google_clicks,google_spend,promo"]
        for index in range(80):
            current = date(2024, 1, 1) + timedelta(days=index * 7)
            media = 100000 + index * 1000
            rows.append(f"{current.isoformat()},{1000 + index},42.50,{media},{media / 100:.2f},{media * 2},{media / 50:.2f},{media}")
        profile = _profile_csv_text("\n".join(rows), "correlated.csv")

        self.assertEqual(_check_status(profile, "modeling_readiness", "high_correlation"), "warning")
        self.assertIn("highly correlated", _check_message(profile, "modeling_readiness", "high_correlation"))


if __name__ == "__main__":
    unittest.main()
