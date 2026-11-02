"""Session-only portfolio dashboard; all calculation rules live in analytics.py."""

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics import (NUMERIC, campaign_performance, filter_data,
                       generate_insights, load_csv, safe_divide, summarize, validate_data)
from sample_data import make_sample_data

st.set_page_config(page_title="Marketing Performance Analyzer | Data Savvy Solutions", page_icon="📊", layout="wide")
# Limit CSS to presentation; native Streamlit controls retain keyboard support.
st.markdown("""
<style>
.block-container {max-width: 1440px; padding-top: 4rem;}
h1, h2, h3 {color: #122B49; letter-spacing: -0.025em;}
[data-testid="stMetric"] {background: #F1F5FA; border: 1px solid #D7E3F0;
    border-top: 3px solid #1763B8; border-radius: 10px; padding: 1rem;}
[data-testid="stMetricValue"] {color: #122B49; font-variant-numeric: tabular-nums;}
@media (max-width: 640px) {
    .block-container {padding: 4rem 1rem 1rem;}
    [data-testid="stMetricValue"] {font-size: 1.6rem;}
}
</style>
""", unsafe_allow_html=True)
st.caption("DATA SAVVY SOLUTIONS  /  PORTFOLIO DEMONSTRATION  /  V1.1")
st.title("Marketing Performance Analyzer")
st.write("Turn campaign reporting into clear performance decisions.")

with st.sidebar:
    st.header("Data Savvy Solutions")
    st.caption("Marketing intelligence • Version 1.1")
    st.divider()
    st.subheader("Data source")
    uploaded = st.file_uploader("Upload a CSV", type=["csv"], help="UTF-8 CSV, up to 10 MB. Download the synthetic sample for the required column format.")
    st.download_button("Download synthetic sample CSV", make_sample_data().to_csv(index=False), "marketing_synthetic_sample.csv", "text/csv")
    with st.expander("CSV requirements"):
        st.write("Required columns: date, platform, campaign, spend, impressions, clicks, conversions, revenue.")
        st.write("Dates: YYYY-MM-DD. Counts: whole numbers. All numbers: finite and non-negative. Spend and revenue: USD. Clicks ≤ impressions; conversions ≤ clicks.")
        st.caption("Count values and column totals must not exceed 9,007,199,254,740,991 to preserve exact counts.")
        st.caption("Each row is additive campaign activity for one calendar day. Do not mix currencies or overlapping totals.")

try:
    # No upload caching or disk writes: each session processes its own dataframe.
    data = load_csv(uploaded.getvalue()) if uploaded is not None else validate_data(make_sample_data())
except ValueError as exc:
    st.error(f"Unable to load data: {exc}")
    st.stop()

if uploaded is None:
    st.info("SYNTHETIC SAMPLE DATA — Fictional marketing activity for demonstration only. These are not client results.")
else:
    st.info("UPLOADED DATA — Analyzing your CSV in this active session. All monetary values are interpreted as USD.")

with st.sidebar:
    st.subheader("Filters")
    platforms = st.multiselect("Platforms", sorted(data["platform"].unique()), default=sorted(data["platform"].unique()))
    campaigns = st.multiselect("Campaigns", sorted(data["campaign"].unique()), default=sorted(data["campaign"].unique()))
    start, end = data["date"].min().date(), data["date"].max().date()
    selected = st.date_input("Date range", value=(start, end), min_value=start, max_value=end)
    st.caption("Uploads are processed in memory for the active session. Use non-confidential data in this public demo.")

if len(selected) != 2:
    st.warning("Select a start and end date.")
    st.stop()
filtered = filter_data(data, platforms, campaigns, selected[0], selected[1])
if filtered.empty:
    st.warning("No records match these filters. Select at least one platform and campaign, or expand the date range.")
    st.stop()

kpi = summarize(filtered)


def fmt(value, kind="number"):
    """Keep missing ratios distinct from measured zeroes across all cards."""
    if value is None:
        return "N/A"
    if kind == "currency":
        return f"${value:,.2f}"
    if kind == "percent":
        return f"{value:.2%}"
    if kind == "ratio":
        return f"{value:.2f}x"
    return f"{value:,.0f}"


st.subheader("Performance snapshot")
st.caption(f"{selected[0]:%b %d, %Y} – {selected[1]:%b %d, %Y} • {len(filtered):,} records • {filtered['platform'].nunique()} platforms • USD")
metrics = [
    ("Ad spend", "spend", "currency"), ("Revenue", "revenue", "currency"),
    ("ROAS", "roas", "ratio"), ("Conversions", "conversions", "number"),
    ("CPA", "cpa", "currency"), ("Conversion rate", "conversion_rate", "percent"),
    ("Impressions", "impressions", "number"), ("Clicks", "clicks", "number"),
    ("CTR", "ctr", "percent"), ("CPC", "cpc", "currency"),
]
for row in range(0, len(metrics), 2):
    columns = st.columns(2)
    for col, (label, key, kind) in zip(columns, metrics[row:row + 2]):
        col.metric(label, fmt(kpi[key], kind))
st.caption("Ratios use summed totals, not averages of row-level ratios. N/A means the denominator is zero or the ratio cannot be represented.")

st.subheader("Executive Insights")
st.caption("Rule-based observations for the current filters. Recommendations are investigation prompts, not causal conclusions.")
for title, explanation in generate_insights(filtered):
    with st.container(border=True):
        st.markdown(f"**{title}**")
        # Plain text prevents uploaded campaign names from injecting Markdown links.
        st.text(explanation)
with st.expander("How insights and KPIs are calculated"):
    st.write("Leader eligibility: positive spend, at least 100 clicks and 10 conversions per platform/campaign. These are demonstration heuristics, not statistical significance thresholds. Ties are disclosed and resolved alphabetically.")
    st.write("Highest ROAS = revenue ÷ spend. Lowest CPA = spend ÷ conversions. Zero-conversion investigation shows the highest-spend campaign without conversions. Revenue investigation shows the lowest eligible ROAS below 1.00x. Revenue below spend is not a complete profit calculation.")
    st.write("CTR = clicks ÷ impressions. CPC = spend ÷ clicks. Conversion rate = conversions ÷ clicks. Compare equivalent attribution windows and currencies. Business margins, lifetime value, attribution lag and incrementality are not modeled.")


def style_chart(fig):
    """Use the same typography and palette for each chart and its tooltips."""
    fig.update_layout(template="plotly_white", font=dict(family="Arial, sans-serif", color="#122B49"),
                      paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
                      margin=dict(l=16, r=16, t=24, b=16), legend_title_text="",
                      legend=dict(orientation="h", y=1.12), height=360)
    fig.update_yaxes(gridcolor="#E4EBF3", rangemode="tozero")
    return fig


st.subheader("Performance over time")
daily = filtered.groupby("date", as_index=False)[["spend", "revenue"]].sum()
# Short selections need point markers; long date ranges stay legible as lines.
trend = px.line(daily, x="date", y=["spend", "revenue"], markers=len(daily) <= 31,
                color_discrete_map={"spend": "#1763B8", "revenue": "#122B49"},
                labels={"value": "Amount (USD)", "date": "Date", "variable": "Metric"})
trend.for_each_trace(lambda trace: trace.update(name=trace.name.title()))
trend.update_traces(hovertemplate="%{x|%b %d, %Y}<br>$%{y:,.2f}<extra>%{fullData.name}</extra>")
trend.update_yaxes(tickprefix="$", tickformat=",.0f")
st.plotly_chart(style_chart(trend), width="stretch")
st.caption("Daily totals for available records. Missing dates are not assumed to be zero activity.")

st.subheader("Channel comparison")
channel = filtered.groupby("platform", as_index=False)[NUMERIC].sum()
# Reuse grouped totals instead of rescanning every input row for each platform.
channel["roas"] = [safe_divide(row.revenue, row.spend) for row in channel.itertuples()]
channel = channel.sort_values("roas", ascending=False, kind="stable")
if channel["roas"].notna().any():
    bars = px.bar(channel.dropna(subset=["roas"]), x="platform", y="roas", text_auto=".2f",
                  color_discrete_sequence=["#1763B8"], labels={"roas": "Return on ad spend (x)", "platform": "Platform"})
    bars.update_traces(hovertemplate="%{x}<br>ROAS: %{y:.2f}x<extra></extra>")
    bars.update_yaxes(ticksuffix="x", tickformat=".2f")
    st.plotly_chart(style_chart(bars), width="stretch")
else:
    st.info("No defined channel ROAS for this selection. Check reported spend.")
st.caption("Channels with undefined ROAS are omitted. Channel ratios include all selected records; leader rankings apply the sample thresholds above.")

st.subheader("Campaign performance")
campaign = campaign_performance(filtered)
# Explicit column formats make currency, counts, percentages and ratios scannable.
st.dataframe(campaign.style.format({
    **{field: "{:,.0f}" for field in ["impressions", "clicks", "conversions"]},
    **{field: "${:,.2f}" for field in ["spend", "revenue", "cpc", "cpa"]},
    **{field: "{:.2%}" for field in ["ctr", "conversion_rate"]}, "roas": "{:.2f}x",
}, na_rep="N/A"), width="stretch", hide_index=True)
st.download_button("Download filtered results", filtered.to_csv(index=False), "marketing_filtered.csv", "text/csv")
st.caption("Data Savvy Solutions • Marketing Performance Analyzer V1.1 • Portfolio demonstration")
