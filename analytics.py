"""Pure analysis functions keep business rules testable outside Streamlit."""

import csv
import io
import math
import re
from decimal import Decimal, InvalidOperation

import pandas as pd

NUMERIC = ["spend", "impressions", "clicks", "conversions", "revenue"]
REQUIRED = {"date", "platform", "campaign", *NUMERIC}
COUNTS = {"impressions", "clicks", "conversions"}
# Keep all count totals exact in the float-based KPI and chart pipeline.
MAX_EXACT_COUNT = 2**53 - 1
MIN_CLICKS = 100
MIN_CONVERSIONS = 10


def _decimal_or_nan(value):
    """Parse exact decimal digits; malformed cells use the shared row-error path."""
    # Decimal itself permits underscores and Unicode digits that our CSV schema excludes.
    text = str(value).strip()
    if re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", text) is None:
        return Decimal("NaN")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("NaN")


def load_csv(content):
    """Check headers before pandas can silently rename duplicate columns."""
    try:
        text = content.decode("utf-8-sig")
        # Pandas' CSV reader truncates at NUL, which can hide invalid numbers or metadata.
        if "\x00" in text:
            raise ValueError("CSV contains a NUL character. Remove NUL characters or re-export the source as UTF-8 CSV.")
        reader = csv.reader(io.StringIO(text), strict=True)
        header = next(reader, [])
        if len(header) != len(set(header)):
            raise ValueError("Duplicate column names: keep one column per required field.")
        # Reject ragged records before pandas can reinterpret a field as an index.
        for row_number, row in enumerate(reader, start=2):
            if row and len(row) != len(header):
                raise ValueError(f"CSV row {row_number}: expected {len(header)} fields, found {len(row)}. Check commas and quoting.")
        # Preserve literal identifiers and NA-like labels until required fields are validated.
        return validate_data(pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False))
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
        # Use one exact parser for counts and currency before any float conversion.
        values = df[field].map(_decimal_or_nan)
        invalid = ~values.map(lambda value: value.is_finite() and value >= 0)
        if invalid.any():
            rows = ", ".join(str(i + 2) for i, bad in enumerate(invalid) if bad)[:100]
            raise ValueError(f"{field}: use finite, non-negative decimal numbers with ASCII digits; no underscores, currency symbols or blanks. CSV row(s): {rows}.")
        if field in COUNTS:
            if (values > MAX_EXACT_COUNT).any():
                raise ValueError(f"{field}: counts must not exceed {MAX_EXACT_COUNT:,}; reduce the count values.")
            if values.map(lambda value: value != value.to_integral_value()).any():
                raise ValueError(f"{field}: use whole-number counts, not fractional values.")
            if sum(int(value) for value in values) > MAX_EXACT_COUNT:
                raise ValueError(f"{field}: total must not exceed {MAX_EXACT_COUNT:,}; reduce the dataset's counts.")
        # Bounded count totals remain exact when aggregated alongside currency floats.
        converted = values.astype(float)
        # A nonzero value rounded to zero changes ROAS/CPA semantics; reject it explicitly.
        invalid = ~converted.map(math.isfinite) | ((values != 0) & (converted == 0))
        if invalid.any():
            rows = ", ".join(str(i + 2) for i, bad in enumerate(invalid) if bad)[:100]
            raise ValueError(f"{field}: value is outside the supported numeric range. Reduce very large values or use a representable nonzero amount. CSV row(s): {rows}.")
        df[field] = converted
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
    # A ratio too small to represent is undefined, just like an overflowing ratio.
    return result if math.isfinite(result) and (result != 0 or numerator == 0) else None


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
    """Explain existing ranking rules without claiming profit or cause and effect."""
    campaigns = campaign_performance(df)
    eligible = campaigns[(campaigns["spend"] > 0) & (campaigns["clicks"] >= MIN_CLICKS)
                         & (campaigns["conversions"] >= MIN_CONVERSIONS)]
    insights = []
    # Stable sorting keeps the example deterministic without suggesting a tie has a winner.
    for metric, ascending, title in [("roas", False, "Revenue per ad dollar"), ("cpa", True, "Ad cost per conversion")]:
        ranked = eligible.dropna(subset=[metric]).sort_values(metric, ascending=ascending, kind="stable")
        if ranked.empty:
            insights.append((title, "There is not enough data to compare campaigns yet. Each needs ad spend above $0.00, at least 100 clicks, 10 conversions, and enough information to calculate this measure. Check reporting and allow more time before changing your budget."))
            continue
        row = ranked.iloc[0]
        value = f"{row[metric]:.2f}x" if metric == "roas" else f"${row[metric]:,.2f}"
        ties = int((ranked[metric] == row[metric]).sum())
        comparison = "highest reported revenue per ad dollar" if metric == "roas" else "lowest ad cost per recorded conversion"
        meaning = (f"{value} means ${row[metric]:,.2f} in reported revenue for each $1.00 spent on ads. This is not profit."
                   if metric == "roas" else f"{value} is the average ad spend for one recorded conversion, which may be a lead rather than a sale.")
        context = (f"Shares the {comparison} across {ties:,} tied campaigns; this is the first alphabetically."
                   if ties > 1 else f"Has the {comparison} among {len(ranked):,} eligible campaigns.")
        if len(ranked) == 1:
            context = "Only one campaign has enough data for this measure, so there is no comparison yet."
        # Disclose apparent ties caused by display rounding without changing the exact ranking.
        rounded_tie = ((ranked[metric] != row[metric]) & (ranked[metric].map(lambda v: f"{v:.2f}") == f"{row[metric]:.2f}")).any()
        rounding_note = " Other results look equal at two decimals; small differences do not establish a meaningful lead." if rounded_tie else ""
        insights.append((title, f"{row['platform']} / {row['campaign']}: {meaning} {context}{rounding_note} Based on ${row['spend']:,.2f} ad spend, {row['clicks']:,.0f} clicks and {row['conversions']:,.0f} conversions. Check tracking and business costs before testing a small budget change."))
    zero = campaigns[(campaigns["spend"] > 0) & (campaigns["conversions"] == 0)]
    below = eligible[eligible["roas"] < 1]
    small = campaigns[(campaigns["clicks"] < MIN_CLICKS) | (campaigns["conversions"] < MIN_CONVERSIONS)]
    undefined = campaigns[(campaigns["spend"] == 0) | campaigns["roas"].isna() | campaigns["cpa"].isna()]
    if not zero.empty:
        row = zero.sort_values("spend", ascending=False, kind="stable").iloc[0]
        ties = int((zero["spend"] == row["spend"]).sum())
        tie_note = f" {ties:,} campaigns share this ad spend; showing the first alphabetically." if ties > 1 else ""
        insights.append(("Ad spend with no recorded conversions", f"{row['platform']} / {row['campaign']} has the most ad spend among campaigns with no recorded conversions: ${row['spend']:,.2f} and {row['clicks']:,.0f} clicks.{tie_note} Cost per acquisition cannot be calculated without conversions. Check tracking, delays in reported results and the page visitors land on before pausing ads. There may be too little data to judge performance."))
    if not below.empty:
        row = below.sort_values("roas", kind="stable").iloc[0]
        ties = int((below["roas"] == row["roas"]).sum())
        tie_note = f" {ties:,} campaigns share this return; showing the first alphabetically." if ties > 1 else ""
        insights.append(("Reported revenue is below ad spend", f"{row['platform']} / {row['campaign']} has the lowest eligible return: {row['roas']:.2f}x, or ${row['roas']:,.2f} in reported revenue per $1.00 spent on ads (rounded).{tie_note} Reported revenue is below ad spend before other business costs. Check tracking, reporting delays and margins before adjusting budget. ROAS does not measure profit, and 1.00x does not cover other costs."))
    if not small.empty:
        insights.append(("Give smaller samples more time", f"{len(small):,} {'campaign has' if len(small) == 1 else 'campaigns have'} fewer than 100 clicks or 10 conversions. They are left out of comparisons because a few results can change the picture quickly. Check reporting and gather more data before making budget decisions."))
    if not undefined.empty:
        insights.append(("Some measures cannot be calculated yet", f"{len(undefined):,} {'campaign has' if len(undefined) == 1 else 'campaigns have'} no ad spend or a revenue return or cost per conversion that cannot be calculated. N/A means unavailable, not zero performance. Check cost and conversion reporting before comparing these campaigns."))
    if zero.empty and below.empty:
        insights.append(("Review business costs before your next test", "No campaigns triggered the checks for ad spend without conversions or eligible revenue below ad spend. This does not establish profitability or prove the ads caused sales. Review tracking, business costs and goals before testing a small change."))
    return insights
