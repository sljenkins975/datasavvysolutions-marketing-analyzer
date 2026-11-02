"""Check the real Streamlit page, including filter reruns and empty states."""

import io
import json

import pyarrow as pa
import unittest
from unittest.mock import patch
from pathlib import Path

from streamlit.testing.v1 import AppTest


class AppTests(unittest.TestCase):
    def test_business_labels_formats_help_and_export(self):
        # Include a zero row to distinguish measured zero from missing ratios.
        csv = (b"date,platform,campaign,spend,impressions,clicks,conversions,revenue,identifier\n"
               b"2026-01-01,Search,Synthetic example,1234.5,10000,1000,100,2469,00123\n"
               b"2026-01-01,Social,Synthetic zero,0,0,0,0,0,00000\n")
        with patch("streamlit.file_uploader", return_value=io.BytesIO(csv)), patch("streamlit.download_button") as download:
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=60)
        self.assertFalse(app.exception)
        expected = {
            "platform": "Marketing Channel", "campaign": "Campaign Name", "spend": "Ad Spend",
            "impressions": "Impressions", "clicks": "Clicks", "conversions": "Conversions",
            "revenue": "Revenue Generated", "ctr": "Click-Through Rate (CTR)",
            "cpc": "Cost Per Click (CPC)", "conversion_rate": "Conversion Rate",
            "cpa": "Cost Per Acquisition (CPA)", "roas": "Return on Ad Spend (ROAS)",
        }
        table = app.dataframe[0]
        config = json.loads(table.proto.columns)
        self.assertEqual({key: config[key]["label"] for key in expected}, expected)
        self.assertEqual(list(table.value.columns), list(expected))
        cards = {item.label: item for item in app.metric}
        for key in ["ctr", "cpc", "cpa", "conversion_rate", "roas"]:
            self.assertTrue(config[key]["help"])
            self.assertEqual(cards[expected[key]].proto.help, config[key]["help"])
        self.assertIn("not profit", config["roas"]["help"])
        # Streamlit 1.66 nests Arrow data; earlier supported versions expose it directly.
        arrow = getattr(table.proto, "arrow_data", table.proto)
        display = pa.ipc.open_stream(arrow.styler.display_values).read_all().to_pandas()
        formatted = {"spend": "$1,234.50", "revenue": "$2,469.00", "impressions": "10,000",
                     "clicks": "1,000", "conversions": "100", "ctr": "10.00%", "cpc": "$1.23",
                     "conversion_rate": "10.00%", "cpa": "$12.35", "roas": "2.00x"}
        for key, value in formatted.items():
            with self.subTest(key=key):
                self.assertEqual(display.loc[0, key], value)
                self.assertEqual(cards[expected[key]].value, value)
        for key in ["ctr", "cpc", "cpa", "conversion_rate", "roas"]:
            self.assertEqual(display.loc[1, key], "N/A")
        self.assertEqual(display.loc[1, "spend"], "$0.00")
        self.assertEqual(display.loc[1, "clicks"], "0")
        exported = download.call_args_list[-1].args[1]
        self.assertEqual(exported.splitlines()[0], csv.decode().splitlines()[0])
        self.assertIn("00123", exported)
        self.assertNotIn("Marketing Channel", exported)
        trend, bars = [json.loads(item.proto.spec) for item in app.get("plotly_chart")]
        self.assertEqual([trace["name"] for trace in trend["data"]], ["Ad Spend", "Revenue Generated"])
        self.assertEqual(trend["layout"]["yaxis"]["tickformat"], ",.2f")
        self.assertEqual(bars["layout"]["xaxis"]["title"]["text"], "Marketing Channel")
        self.assertEqual(bars["data"][0]["texttemplate"], "%{y:.2f}x")
        self.assertEqual(app.multiselect[0].label, "Marketing Channels")
        self.assertEqual(app.multiselect[1].label, "Campaign Names")

    def test_uploaded_zero_data(self):
        # Mock only file selection; exercise the real parsing, charts and page.
        csv = b"date,platform,campaign,spend,impressions,clicks,conversions,revenue\n2026-01-01,Search,Synthetic zero,0,0,0,0,0\n"
        with patch("streamlit.file_uploader", return_value=io.BytesIO(csv)):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=60)
        self.assertFalse(app.exception)
        self.assertIn("UPLOADED DATA", app.info[0].value)
        self.assertEqual(app.metric[2].value, "N/A")
        self.assertTrue(any("No defined channel ROAS" in item.value for item in app.info))

    def test_invalid_upload_stops_with_guidance(self):
        with patch("streamlit.file_uploader", return_value=io.BytesIO(b"wrong\n1")):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=60)
        self.assertFalse(app.exception)
        self.assertIn("Missing columns", app.error[0].value)
        self.assertEqual(len(app.metric), 0)

    def test_sample_dashboard_and_filters(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=60)
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric), 10)
        self.assertIn("SYNTHETIC SAMPLE DATA", app.info[0].value)
        self.assertTrue(any(item.value == "Executive Insights" for item in app.subheader))
        app.multiselect[0].set_value(["Google Ads"]).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe[0].value), 1)
        app.multiselect[0].set_value([]).run()
        self.assertFalse(app.exception)
        self.assertIn("No records match", app.warning[0].value)
        app.multiselect[0].set_value(["Google Ads"]).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric), 10)


if __name__ == "__main__":
    unittest.main()
