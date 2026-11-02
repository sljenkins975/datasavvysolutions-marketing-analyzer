import pandas as pd
import plotly.express as px
import streamlit as st
from analytics import validate_data, summarize
from sample_data import make_sample_data

st.set_page_config(page_title="Marketing Performance Analyzer | Data Savvy Solutions", page_icon="📊", layout="wide")
st.title("Marketing Performance Analyzer")
st.caption("Data Savvy Solutions | Interactive marketing analytics demonstration")
st.info("DEMONSTRATION DATA: The built-in dataset is synthetic and does not represent actual client results.")

with st.sidebar:
    st.header("Data source")
    uploaded = st.file_uploader("Upload a CSV", type=["csv"], help="Required: date, platform, campaign, spend, impressions, clicks, conversions, revenue")
    st.download_button("Download sample CSV", make_sample_data().to_csv(index=False), "marketing_sample.csv", "text/csv")
try:
    data = validate_data(pd.read_csv(uploaded) if uploaded else make_sample_data())
except (ValueError, pd.errors.ParserError, UnicodeError) as exc:
    st.error(f"Unable to load data: {exc}")
    st.stop()

with st.sidebar:
    st.header("Filters")
    platforms = st.multiselect("Platforms", sorted(data["platform"].unique()), default=sorted(data["platform"].unique()))
    campaigns = st.multiselect("Campaigns", sorted(data["campaign"].unique()), default=sorted(data["campaign"].unique()))
    start, end = data["date"].min().date(), data["date"].max().date()
    selected = st.date_input("Date range", value=(start, end), min_value=start, max_value=end)

if len(selected) != 2:
    st.warning("Select a start and end date.")
    st.stop()
filtered = data[
    data["platform"].isin(platforms)
    & data["campaign"].isin(campaigns)
    & data["date"].between(pd.Timestamp(selected[0]), pd.Timestamp(selected[1]))
]
if filtered.empty:
    st.warning("No records match these filters.")
    st.stop()

kpi = summarize(filtered)
def fmt(value, kind="number"):
    if value is None:
        return "N/A"
    if kind == "currency":
        return f"${value:,.2f}"
    if kind == "percent":
        return f"{value:.2%}"
    if kind == "ratio":
        return f"{value:.2f}x"
    return f"{value:,.0f}"

metrics = [
    ("Spend", "spend", "currency"), ("Impressions", "impressions", "number"),
    ("Clicks", "clicks", "number"), ("CTR", "ctr", "percent"),
    ("Conversions", "conversions", "number"), ("Conversion Rate", "conversion_rate", "percent"),
    ("CPC", "cpc", "currency"), ("CPA", "cpa", "currency"), ("ROAS", "roas", "ratio"),
]
for row in range(0, len(metrics), 3):
    columns = st.columns(3)
    for col, (label, key, kind) in zip(columns, metrics[row:row + 3]):
        col.metric(label, fmt(kpi[key], kind))

st.subheader("Performance over time")
daily = filtered.groupby("date", as_index=False)[["spend", "revenue", "conversions"]].sum()
st.plotly_chart(px.line(daily, x="date", y=["spend", "revenue"], labels={"value": "Amount (USD)", "date": "Date", "variable": "Metric"}), use_container_width=True)

st.subheader("Channel comparison")
channel = filtered.groupby("platform", as_index=False)[["spend", "revenue", "clicks", "conversions", "impressions"]].sum()
channel["roas"] = channel.apply(lambda r: r["revenue"] / r["spend"] if r["spend"] else None, axis=1)
st.plotly_chart(px.bar(channel, x="platform", y="roas", labels={"roas": "ROAS", "platform": "Platform"}), use_container_width=True)

st.subheader("Campaign performance")
campaign = filtered.groupby(["platform", "campaign"], as_index=False)[["spend", "impressions", "clicks", "conversions", "revenue"]].sum()
campaign["ctr"] = campaign.apply(lambda r: r["clicks"] / r["impressions"] if r["impressions"] else None, axis=1)
campaign["cpa"] = campaign.apply(lambda r: r["spend"] / r["conversions"] if r["conversions"] else None, axis=1)
campaign["roas"] = campaign.apply(lambda r: r["revenue"] / r["spend"] if r["spend"] else None, axis=1)
st.dataframe(campaign, use_container_width=True, hide_index=True)
st.download_button("Download filtered results", filtered.to_csv(index=False), "marketing_filtered.csv", "text/csv")
st.caption("Uploaded data is processed in the active session. Avoid uploading confidential or personally identifiable information to this public demonstration.")
