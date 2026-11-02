import random
from datetime import date, timedelta
import pandas as pd

PLATFORMS = {
    "Facebook": (0.018, 0.045),
    "Instagram": (0.023, 0.035),
    "TikTok": (0.015, 0.025),
    "LinkedIn": (0.012, 0.055),
    "Google Ads": (0.045, 0.065),
}

def make_sample_data():
    rng = random.Random(42)
    start = date(2025, 11, 1)
    rows = []
    for day in range(365):
        current = start + timedelta(days=day)
        for platform, (ctr, conversion_rate) in PLATFORMS.items():
            impressions = rng.randint(800, 9000)
            clicks = round(impressions * ctr * rng.uniform(0.75, 1.25))
            conversions = round(clicks * conversion_rate * rng.uniform(0.65, 1.35))
            spend = round(clicks * rng.uniform(0.6, 3.2), 2)
            revenue = round(conversions * rng.uniform(35, 160), 2)
            rows.append({
                "date": current.isoformat(),
                "platform": platform,
                "campaign": f"{platform} - Acquisition",
                "spend": spend,
                "impressions": impressions,
                "clicks": clicks,
                "conversions": conversions,
                "revenue": revenue,
            })
    return pd.DataFrame(rows)
