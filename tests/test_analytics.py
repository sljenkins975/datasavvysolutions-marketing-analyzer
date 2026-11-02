"""Exercise the data boundary and decision rules without starting a web server."""

import csv
import io
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
        for content in [b"", b"\xff", b'date,date\n1,2', b'date,platform\n"unclosed', b"date,platform\n2026-01-01,Search,extra"]:
            with self.subTest(content=content), self.assertRaises(ValueError):
                load_csv(content)

    def test_malformed_numeric_syntax_is_rejected(self):
        # Decimal accepts underscores and Unicode digits unless grammar is checked first.
        for field in ["spend", "impressions", "clicks", "conversions", "revenue"]:
            for value in ["1__0", "__1__", "1_0", "1e_1", "１", "1,000", "0x10"]:
                df = self.raw.astype(object)
                df.loc[0, ["impressions", "clicks", "conversions"]] = [100, 10, 1]
                df.loc[0, field] = value
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, field):
                        validate_data(df)
                    with self.assertRaisesRegex(ValueError, field):
                        load_csv(df.to_csv(index=False).encode())

    def test_supported_numeric_notation_remains_valid(self):
        # Preserve existing decimal/scientific notation and surrounding whitespace.
        for value in ["10", "10.0", "10.", "+10", " 10 ", "1e1", "100e-1"]:
            df = self.raw.astype(object)
            df.loc[0, "impressions"] = value
            with self.subTest(value=value):
                self.assertEqual(load_csv(df.to_csv(index=False).encode()).loc[0, "impressions"], 10)

    def test_nul_bytes_are_rejected_before_csv_inference(self):
        for field in ["date", "platform", "clicks", "metadata"]:
            df = self.raw.astype(object)
            df["metadata"] = "ABC"
            df.loc[0, field] = str(df.loc[0, field]) + "\x00hidden"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "NUL"):
                load_csv(df.to_csv(index=False).encode())
        content = self.raw.to_csv(index=False).replace("impressions", "impressions\x00hidden")
        with self.assertRaisesRegex(ValueError, "NUL"):
            load_csv(content.encode())

    def test_nonzero_money_cannot_silently_underflow_to_zero(self):
        for field in ["spend", "revenue"]:
            for value in ["1e-999", "1e999"]:
                df = self.raw.astype(object)
                df.loc[0, field] = value
                with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, field):
                    load_csv(df.to_csv(index=False).encode())
            df.loc[0, field] = "0e-999"
            self.assertEqual(load_csv(df.to_csv(index=False).encode()).loc[0, field], 0)

    def test_underflow_ratios_are_undefined_not_zero(self):
        self.assertIsNone(safe_divide(1e-308, 1e308))
        self.assertEqual(safe_divide(0, 1e308), 0)

    def test_count_precision_rejects_unsafe_values_before_rounding(self):
        # Exercise raw CSV strings so pandas cannot hide fractions before validation.
        for field in ["impressions", "clicks", "conversions"]:
            for value in ["9007199254740992", "9007199254740993",
                          "9007199254740992.5", "9007199254740990.5"]:
                df = self.raw.astype(object)
                df.loc[0, field] = value
                with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, field):
                    load_csv(df.to_csv(index=False).encode())

    def test_adjacent_large_counts_cannot_bypass_funnel_validation(self):
        df = self.raw.astype(object)
        df.loc[0, "impressions"] = "9007199254740992"
        df.loc[0, "clicks"] = "9007199254740993"
        with self.assertRaises(ValueError):
            load_csv(df.to_csv(index=False).encode())

    def test_safe_count_limit_applies_to_totals(self):
        # Every downstream subset/group total stays exact if the full total fits.
        for field in ["impressions", "clicks", "conversions"]:
            df = self.raw.astype(object)
            for count in ["impressions", "clicks", "conversions"]:
                df[count] = ["9007199254740991", "0"]
            result = load_csv(df.to_csv(index=False).encode())
            self.assertEqual(summarize(result)[field], 9007199254740991)
            self.assertEqual(campaign_performance(result).loc[0, field], 9007199254740991)
            for count in ["impressions", "clicks", "conversions"]:
                df.loc[1, count] = "1"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "total.*9,007,199,254,740,991"):
                load_csv(df.to_csv(index=False).encode())

    def test_extra_columns_survive_filtered_csv_export(self):
        df = self.raw.copy()
        df["identifier"] = ["00123", "00000"]
        df["status"] = ["NA", "NULL"]
        df["note"] = ["", "NaN"]
        df["description"] = ["  keep spaces  ", "é, quoted\ntext"]
        loaded = load_csv(df.to_csv(index=False).encode("utf-8-sig"))
        for platform in ["Search", "Social"]:
            filtered = filter_data(loaded, [platform], ["Acquisition"], "2026-01-01", "2026-01-02")
            # Parse the download as CSV text to check literal values, not inference.
            exported = list(csv.DictReader(io.StringIO(filtered.to_csv(index=False))))[0]
            original = df[df["platform"] == platform].iloc[0]
            for field in ["identifier", "status", "note", "description"]:
                self.assertEqual(exported[field], original[field])

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
        self.assertIn("Search / Acquisition: 4.00x", result["Revenue per ad dollar"])
        self.assertIn("Search / Acquisition: $10.00", result["Ad cost per conversion"])
        self.assertIn("Social / Acquisition", result["Reported revenue is below ad spend"])

    def test_insights_exclude_small_samples_and_zero_spend(self):
        df = self.eligible_data()
        df.loc[0, "conversions"] = 9
        df.loc[1, "spend"] = 0
        result = dict(generate_insights(df))
        self.assertIn("not enough data", result["Revenue per ad dollar"])
        self.assertIn("not enough data", result["Ad cost per conversion"])
        self.assertIn("1 campaign", result["Give smaller samples more time"])
        self.assertIn("1 campaign", result["Some measures cannot be calculated yet"])

    def test_zero_conversion_investigation(self):
        df = self.eligible_data()
        df.loc[1, "conversions"] = 0
        result = dict(generate_insights(df))
        self.assertIn("Social / Acquisition", result["Ad spend with no recorded conversions"])
        self.assertIn("cannot be calculated without conversions", result["Ad spend with no recorded conversions"])

    def test_insight_ties_are_deterministic(self):
        df = self.eligible_data()
        df["spend"] = 100
        df["revenue"] = 400
        first = generate_insights(df)
        self.assertEqual(first, generate_insights(df.iloc[::-1]))
        self.assertIn("2 tied campaigns", dict(first)["Revenue per ad dollar"])
        self.assertIn("Review business costs before your next test", dict(first))

    def test_insight_meanings_and_cautious_next_steps(self):
        # Explain business meaning without treating reported returns as profit or causality.
        result = dict(generate_insights(self.eligible_data()))
        self.assertIn("$4.00 in reported revenue for each $1.00", result["Revenue per ad dollar"])
        self.assertIn("This is not profit", result["Revenue per ad dollar"])
        self.assertIn("among 2 eligible campaigns", result["Revenue per ad dollar"])
        self.assertIn("may be a lead rather than a sale", result["Ad cost per conversion"])
        self.assertIn("before testing a small budget change", result["Ad cost per conversion"])
        self.assertIn("1.00x does not cover other costs", result["Reported revenue is below ad spend"])
        df = self.eligible_data()
        df["revenue"] = 400
        text = dict(generate_insights(df))["Review business costs before your next test"]
        self.assertIn("does not establish profitability or prove the ads caused sales", text)

    def test_single_eligible_campaign_is_not_a_comparison(self):
        # A sole eligible campaign cannot support a relative performance claim.
        result = dict(generate_insights(self.eligible_data().iloc[:1]))
        for title in ["Revenue per ad dollar", "Ad cost per conversion"]:
            self.assertIn("no comparison yet", result[title])
            self.assertNotIn("Has the", result[title])

    def test_rounded_leaders_are_not_presented_as_meaningfully_different(self):
        # Preserve exact ranking while acknowledging identical two-decimal displays.
        df = self.eligible_data()
        df["spend"] = [100.001, 100.002]
        df["revenue"] = [400.001, 400.002]
        result = dict(generate_insights(df))
        for title in ["Revenue per ad dollar", "Ad cost per conversion"]:
            self.assertIn("small differences do not establish a meaningful lead", result[title])
        self.assertIn("Search / Acquisition", result["Revenue per ad dollar"])

    def test_investigation_ties_disclose_the_example_selection(self):
        # Investigation examples should be as transparent about ties as the leaders.
        for conversions, revenue, title in [
            (0, 0, "Ad spend with no recorded conversions"),
            (10, 50, "Reported revenue is below ad spend"),
        ]:
            df = self.eligible_data()
            df["spend"], df["conversions"], df["revenue"] = 100, conversions, revenue
            first = generate_insights(df)
            self.assertEqual(first, generate_insights(df.iloc[::-1]))
            self.assertIn("2 campaigns share", dict(first)[title])
            self.assertIn("first alphabetically", dict(first)[title])

    def test_all_zero_insights_are_unavailable_not_poor_performance(self):
        # Undefined measures must not turn into a zero return or a recommendation to stop ads.
        df = self.eligible_data()
        df.loc[:, ["spend", "impressions", "clicks", "conversions", "revenue"]] = 0
        result = dict(generate_insights(df))
        self.assertIn("N/A means unavailable, not zero performance", result["Some measures cannot be calculated yet"])
        self.assertNotIn("Ad spend with no recorded conversions", result)
        self.assertNotIn("Reported revenue is below ad spend", result)

    def test_rankings_remain_specific_to_each_measure(self):
        # Higher revenue per dollar can coexist with a higher cost per conversion.
        df = self.eligible_data()
        df["revenue"] = [200, 800]
        result = dict(generate_insights(df))
        self.assertIn("Social / Acquisition", result["Revenue per ad dollar"])
        self.assertIn("Search / Acquisition", result["Ad cost per conversion"])
        self.assertNotIn("best campaign", " ".join(result.values()).lower())

    def test_empty_insights(self):
        result = dict(generate_insights(validate_data(self.raw).iloc[:0]))
        self.assertIn("not enough data", result["Revenue per ad dollar"])


if __name__ == "__main__":
    unittest.main()
