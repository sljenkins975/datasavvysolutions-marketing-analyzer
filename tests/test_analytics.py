import unittest
import pandas as pd
from analytics import summarize, validate_data
from sample_data import make_sample_data

class AnalyticsTests(unittest.TestCase):
    def test_sample_data(self):
        df = validate_data(make_sample_data())
        self.assertEqual(len(df), 365 * 5)
        self.assertTrue((df["clicks"] <= df["impressions"]).all())

    def test_weighted_ctr(self):
        df = pd.DataFrame({"spend": [10, 20], "impressions": [100, 900], "clicks": [10, 9], "conversions": [1, 1], "revenue": [30, 40]})
        self.assertAlmostEqual(summarize(df)["ctr"], 0.019)

    def test_zero_denominator(self):
        df = pd.DataFrame({"spend": [0], "impressions": [0], "clicks": [0], "conversions": [0], "revenue": [0]})
        self.assertIsNone(summarize(df)["roas"])

if __name__ == "__main__":
    unittest.main()
