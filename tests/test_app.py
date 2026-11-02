"""Check the real Streamlit page, including filter reruns and empty states."""

import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


class AppTests(unittest.TestCase):
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
