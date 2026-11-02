import pandas as pd

REQUIRED = {"date", "platform", "campaign", "spend", "impressions", "clicks", "conversions", "revenue"}

def validate_data(df):
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError("Missing columns: " + ", ".join(sorted(missing)))
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="raise")
    for field in ("spend", "impressions", "clicks", "conversions", "revenue"):
        df[field] = pd.to_numeric(df[field], errors="raise")
        if (df[field] < 0).any():
            raise ValueError(f"{field} cannot contain negative values")
    if (df["clicks"] > df["impressions"]).any() or (df["conversions"] > df["clicks"]).any():
        raise ValueError("Clicks cannot exceed impressions and conversions cannot exceed clicks")
    return df

def safe_divide(numerator, denominator):
    return numerator / denominator if denominator else None

def summarize(df):
    totals = df[["spend", "impressions", "clicks", "conversions", "revenue"]].sum()
    return {
        **totals.to_dict(),
        "ctr": safe_divide(totals["clicks"], totals["impressions"]),
        "cpc": safe_divide(totals["spend"], totals["clicks"]),
        "conversion_rate": safe_divide(totals["conversions"], totals["clicks"]),
        "cpa": safe_divide(totals["spend"], totals["conversions"]),
        "roas": safe_divide(totals["revenue"], totals["spend"]),
    }
