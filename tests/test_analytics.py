"""Exercise the data boundary and decision rules without starting a web server."""

import unittest

import pandas as pd

from analytics import (campaign_performance, filter_data, generate_insights,
                       load_csv, safe_divide, summarize, validate_data)
from sample_data import make_sample_data


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        # Different row sizes catch accidental averaging of row-level ratios.
        self.raw = pd.DataFrame({"date": ["2026-01-01", "2026-01-02"],
            "platform": ["Search", "Social"], "campaign": ["Acquisition", "Acquisition"],
            "spend": [10, 20], "impressions": [100, 900], "clicks": [10, 9],
            "conversions": [1, 1], "revenue": [30, 40]})

    def test_sample_data_is_valid_and_reproducible(self):
        df = validate_data(make_sample_data())
        self.assertEqual(len(df), 365 * 5)
        pd.testing.assert_frame_equal(make_sample_data(), make_sample_data())

    def test_weighted_kpis(self):
        result = summarize(validate_data(self.raw))
        expected = {"spend": 30, "impressions": 1000, "clicks": 19,
                    "conversions": 2, "revenue": 70, "ctr": .019,
                    "cpc": 30 / 19, "conversion_rate": 2 / 19, "cpa": 15, "roas": 70 / 30}
        for metric, value in expected.items():
            with self.subTest(metric=metric):
                self.assertAlmostEqual(result[metric], value)

    def test_zero_denominators_and_empty_totals(self):
        self.raw.loc[:, ["spend", "impressions", "clicks", "conversions", "revenue"]] = 0
        for df in [self.raw, self.raw.iloc[:0]]:
            for metric in ["ctr", "cpc", "conversion_rate", "cpa", "roas"]:
                self.assertIsNone(summarize(df)[metric])
        self.assertIsNone(safe_divide(1e308, 1e-308))

    def test_missing_empty_and_duplicate_columns(self):
        for df, message in [(self.raw.drop(columns="spend"), "Missing columns: spend"),
                            (self.raw.iloc[:0], "No data rows"),
                            (pd.concat([self.raw, self.raw[["spend"]]], axis=1), "Duplicate")]:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                validate_data(df)

    def test_invalid_numeric_values(self):
        for field in ["spend", "impressions", "clicks", "conversions", "revenue"]:
            for value in [None, "", "oops", "$10", float("inf"), float("-inf"), -1, float("nan")]:
                df = self.raw.astype(object)
                df.loc[0, field] = value
                with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, field):
                    validate_data(df)

    def test_counts_and_funnel_consistency(self):
        for field, value, message in [("clicks", 1.5, "whole-number"),
                                      ("clicks", 101, "Clicks cannot exceed"),
                                      ("conversions", 11, "conversions cannot exceed")]:
            df = self.raw.astype(object)
            df.loc[0, field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                validate_data(df)

    def test_invalid_dates_and_labels(self):
        for field, values in {"date": [None, "", "2026-02-30", "01/02/2026", "2026-01-01T10:00:00Z"],
                              "platform": [None, " ", 42], "campaign": [None, ""]}.items():
            for value in values:
                df = self.raw.astype(object)
                df.loc[0, field] = value
                with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, field):
                    validate_data(df)

    def test_validation_copies_and_normalizes(self):
        self.raw.loc[0, "platform"] = " Search "
        result = validate_data(self.raw)
        self.assertEqual(result.loc[0, "platform"], "Search")
        self.assertEqual(self.raw.loc[0, "platform"], " Search ")
        self.assertEqual(result.loc[0, "date"], pd.Timestamp("2026-01-01"))

    def test_csv_boundary(self):
        result = load_csv(self.raw.to_csv(index=False).encode("utf-8-sig"))
        self.assertEqual(len(result), 2)
        for content in [b"", b"\xff", b'date,date\n1,2', b'date,platform\n"unclosed']:
            with self.subTest(content=content), self.assertRaises(ValueError):
                load_csv(content)

    def test_large_totals_rejected(self):
        self.raw["spend"] = [1e308, 1e308]
        with self.assertRaisesRegex(ValueError, "total is too large"):
            validate_data(self.raw)

    def test_filters_include_endpoints_and_empty_selections(self):
        df = validate_data(self.raw)
        self.assertEqual(len(filter_data(df, ["Search", "Social"], ["Acquisition"], "2026-01-01", "2026-01-02")), 2)
        self.assertEqual(list(filter_data(df, ["Social"], ["Acquisition"], "2026-01-02", "2026-01-02")["platform"]), ["Social"])
        for platforms, campaigns in [([], ["Acquisition"]), (["Search"], []), (["Missing"], ["Acquisition"])]:
            self.assertTrue(filter_data(df, platforms, campaigns, "2026-01-01", "2026-01-02").empty)

    def test_campaigns_remain_separate_by_platform(self):
        self.assertEqual(len(campaign_performance(validate_data(self.raw))), 2)

    def eligible_data(self):
        # Exact sample thresholds verify that eligibility includes its endpoints.
        df = self.raw.copy()
        df["impressions"] = 1000
        df["clicks"] = 100
        df["conversions"] = 10
        df["spend"] = [100, 200]
        df["revenue"] = [400, 100]
        return validate_data(df)

    def test_insight_leaders_and_investigation(self):
        result = dict(generate_insights(self.eligible_data()))
        self.assertIn("Search / Acquisition: 4.00x", result["Highest ROAS"])
        self.assertIn("Search / Acquisition: $10.00", result["Lowest CPA"])
        self.assertIn("Social / Acquisition", result["Investigate revenue recovery"])

    def test_insights_exclude_small_samples_and_zero_spend(self):
        df = self.eligible_data()
        df.loc[0, "conversions"] = 9
        df.loc[1, "spend"] = 0
        result = dict(generate_insights(df))
        self.assertIn("Insufficient evidence", result["Highest ROAS"])
        self.assertIn("Insufficient evidence", result["Lowest CPA"])
        self.assertIn("1 campaign", result["Build more evidence"])
        self.assertIn("1 campaign", result["Check undefined ratios"])

    def test_zero_conversion_investigation(self):
        df = self.eligible_data()
        df.loc[1, "conversions"] = 0
        result = dict(generate_insights(df))
        self.assertIn("Social / Acquisition", result["Investigate conversion tracking"])
        self.assertIn("CPA is undefined", result["Investigate conversion tracking"])

    def test_insight_ties_are_deterministic(self):
        df = self.eligible_data()
        df["spend"] = 100
        df["revenue"] = 400
        first = generate_insights(df)
        self.assertEqual(first, generate_insights(df.iloc[::-1]))
        self.assertIn("Tied across 2", dict(first)["Highest ROAS"])
        self.assertIn("Next investigation", dict(first))

    def test_empty_insights(self):
        result = dict(generate_insights(validate_data(self.raw).iloc[:0]))
        self.assertIn("Insufficient evidence", result["Highest ROAS"])


if __name__ == "__main__":
    unittest.main()
