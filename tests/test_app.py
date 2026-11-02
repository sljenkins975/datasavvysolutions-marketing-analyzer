"""Check the real Streamlit page, including filter reruns and empty states."""

import io
import unittest
from unittest.mock import patch
from pathlib import Path

from streamlit.testing.v1 import AppTest


class AppTests(unittest.TestCase):
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
