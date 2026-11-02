"""Pure analysis functions keep business rules testable outside Streamlit."""

import csv
import io
import math

import pandas as pd

NUMERIC = ["spend", "impressions", "clicks", "conversions", "revenue"]
REQUIRED = {"date", "platform", "campaign", *NUMERIC}
MIN_CLICKS = 100
MIN_CONVERSIONS = 10


def load_csv(content):
    """Check headers before pandas can silently rename duplicate columns."""
    try:
        text = content.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text), strict=True)
        header = next(reader, [])
        if len(header) != len(set(header)):
            raise ValueError("Duplicate column names: keep one column per required field.")
        # Reject ragged records before pandas can reinterpret a field as an index.
        for row_number, row in enumerate(reader, start=2):
            if row and len(row) != len(header):
                raise ValueError(f"CSV row {row_number}: expected {len(header)} fields, found {len(row)}. Check commas and quoting.")
        return validate_data(pd.read_csv(io.StringIO(text)))
    except (UnicodeError, csv.Error, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError("Use a UTF-8, comma-separated CSV with a header and data rows. Download the sample for a template.") from exc


def validate_data(df):
    """Reject incomplete records instead of silently dropping or repairing them."""
    if df.columns.duplicated().any():
        raise ValueError("Duplicate column names: keep one column per required field.")
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError("Missing columns: " + ", ".join(sorted(missing)) + ". Download the sample CSV for the required schema.")
    if df.empty:
        raise ValueError("No data rows found. Add at least one complete record below the header.")
    df = df.copy()
    for field in ["platform", "campaign"]:
        valid = df[field].map(lambda value: isinstance(value, str) and bool(value.strip()))
        if not valid.all():
            raise ValueError(f"{field}: enter a non-blank text label in every row.")
        df[field] = df[field].str.strip()
    # ISO calendar dates avoid locale ambiguity and timezone shifts in daily filters.
    dates = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce")
    if dates.isna().any():
        raise ValueError("date: use a valid YYYY-MM-DD calendar date in every row (for example, 2026-01-31).")
    df["date"] = dates
    for field in NUMERIC:
        values = pd.to_numeric(df[field], errors="coerce")
        invalid = ~values.map(lambda value: math.isfinite(value) and value >= 0)
        if invalid.any():
            rows = ", ".join(str(i + 2) for i, bad in enumerate(invalid) if bad)[:100]
            raise ValueError(f"{field}: use finite, non-negative numbers without currency symbols or blanks. CSV row(s): {rows}.")
        if field in ["impressions", "clicks", "conversions"] and (values % 1 != 0).any():
            raise ValueError(f"{field}: use whole-number counts, not fractional values.")
        # Floats avoid integer overflow when pandas aggregates large input counts.
        df[field] = values.astype(float)
        if sum(df[field]) == math.inf:
            raise ValueError(f"{field}: total is too large; reduce the numeric values.")
    if (df["clicks"] > df["impressions"]).any() or (df["conversions"] > df["clicks"]).any():
        raise ValueError("Clicks cannot exceed impressions and conversions cannot exceed clicks. Check the count columns in each row.")
    return df


def safe_divide(numerator, denominator):
    """Undefined or unrepresentable ratios must never appear as zero performance."""
    if not denominator:
        return None
    result = numerator / denominator
    return result if math.isfinite(result) else None


def summarize(df):
    """Divide summed totals so large and small records receive correct weights."""
    totals = df[NUMERIC].sum()
    return {
        **totals.to_dict(),
        "ctr": safe_divide(totals["clicks"], totals["impressions"]),
        "cpc": safe_divide(totals["spend"], totals["clicks"]),
        "conversion_rate": safe_divide(totals["conversions"], totals["clicks"]),
        "cpa": safe_divide(totals["spend"], totals["conversions"]),
        "roas": safe_divide(totals["revenue"], totals["spend"]),
    }


def filter_data(df, platforms, campaigns, start, end):
    """Include both calendar-date endpoints; an empty selection means no records."""
    return df[df["platform"].isin(platforms) & df["campaign"].isin(campaigns)
              & df["date"].between(pd.Timestamp(start), pd.Timestamp(end))].copy()


def campaign_performance(df):
    """Keep identical campaign names on different platforms separate."""
    rows = []
    for (platform, campaign), group in df.groupby(["platform", "campaign"], sort=True):
        rows.append({"platform": platform, "campaign": campaign, **summarize(group)})
    return pd.DataFrame(rows, columns=["platform", "campaign", *NUMERIC, "ctr", "cpc", "conversion_rate", "cpa", "roas"])


def generate_insights(df):
    """Use disclosed heuristics, not statistical significance or causal claims."""
    campaigns = campaign_performance(df)
    eligible = campaigns[(campaigns["spend"] > 0) & (campaigns["clicks"] >= MIN_CLICKS)
                         & (campaigns["conversions"] >= MIN_CONVERSIONS)]
    insights = []
    # Stable sorting preserves alphabetical platform/campaign order when ratios tie.
    for metric, ascending, title in [("roas", False, "Highest ROAS"), ("cpa", True, "Lowest CPA")]:
        ranked = eligible.dropna(subset=[metric]).sort_values(metric, ascending=ascending, kind="stable")
        if ranked.empty:
            insights.append((title, "Insufficient evidence: no campaign has positive spend, 100 clicks, 10 conversions, and a defined ratio."))
        else:
            row = ranked.iloc[0]
            value = f"{row[metric]:.2f}x" if metric == "roas" else f"${row[metric]:,.2f}"
            ties = int((ranked[metric] == row[metric]).sum())
            tie_note = f" Tied across {ties} campaigns; showing the first alphabetically." if ties > 1 else ""
            insights.append((title, f"{row['platform']} / {row['campaign']}: {value}, based on ${row['spend']:,.2f} spend, {row['clicks']:,.0f} clicks and {row['conversions']:,.0f} conversions.{tie_note} Review tracking and business targets before changing budget."))
    zero = campaigns[(campaigns["spend"] > 0) & (campaigns["conversions"] == 0)]
    below = eligible[eligible["roas"] < 1]
    small = campaigns[(campaigns["clicks"] < MIN_CLICKS) | (campaigns["conversions"] < MIN_CONVERSIONS)]
    undefined = campaigns[(campaigns["spend"] == 0) | campaigns["roas"].isna() | campaigns["cpa"].isna()]
    if not zero.empty:
        row = zero.sort_values("spend", ascending=False, kind="stable").iloc[0]
        insights.append(("Investigate conversion tracking", f"{row['platform']} / {row['campaign']} spent ${row['spend']:,.2f} with zero conversions and {row['clicks']:,.0f} clicks. Check tracking, attribution lag and landing pages; CPA is undefined. This may be a small sample."))
    if not below.empty:
        row = below.sort_values("roas", kind="stable").iloc[0]
        insights.append(("Investigate revenue recovery", f"{row['platform']} / {row['campaign']} has {row['roas']:.2f}x ROAS: reported revenue is below ad spend. Check attribution and margins before adjusting budget; 1.00x is not a profitability target."))
    if not small.empty:
        insights.append(("Build more evidence", f"{len(small)} campaign(s) fall below 100 clicks or 10 conversions and are excluded from leader rankings. Gather more observations before drawing conclusions."))
    if not undefined.empty:
        insights.append(("Check undefined ratios", f"{len(undefined)} campaign(s) have zero spend or an undefined ROAS/CPA. Check missing cost or conversion reporting; undefined ratios are excluded from relevant rankings."))
    if zero.empty and below.empty:
        insights.append(("Next investigation", "No campaign meets the zero-conversion or eligible ROAS-below-1.00x rules. Review attribution, margins and business targets; this does not establish profitability."))
    return insights
