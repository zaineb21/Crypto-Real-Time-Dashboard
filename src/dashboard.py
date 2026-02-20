# dashboard.py
import streamlit as st
from kafka import KafkaConsumer
import json
import pandas as pd
import plotly.express as px
from streamlit_autorefresh import st_autorefresh

# ─── Kafka config ────────────────────────────────────────────────────────────
KAFKA_BROKER = "localhost:9092"
TOPIC        = "crypto-aggregates"

# ─── Streamlit setup ─────────────────────────────────────────────────────────
st.set_page_config(page_title="Crypto Dashboard", layout="wide")
st.title("📈 Crypto Real-Time Dashboard")
st.caption("Live BTC & ETH price aggregates — refreshes every 5 seconds")

# Auto-refresh every 5 seconds
st_autorefresh(interval=5000, key="crypto_refresh")

# ─── Session state to accumulate records across reruns ───────────────────────
if "records" not in st.session_state:
    st.session_state.records = []

# ─── Kafka Consumer ──────────────────────────────────────────────────────────
consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers=KAFKA_BROKER,
    auto_offset_reset="earliest",
    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    consumer_timeout_ms=2000
)

# ─── Fetch new messages ──────────────────────────────────────────────────────
def fetch_data(consumer, max_messages=100):
    records = []
    for i, msg in enumerate(consumer):
        if i >= max_messages:
            break
        value = msg.value
        print("[MSG]", value)  # debug log

        required = ["symbol", "avg_price", "window_start", "window_end"]
        if not all(k in value for k in required):
            print("[SKIP] missing fields:", value)
            continue

        records.append({
            "symbol":       value["symbol"],
            "avg_price":    value["avg_price"],
            "min_price":    value.get("min_price", 0),
            "max_price":    value.get("max_price", 0),
            "count":        value.get("count", 0),
            "window_start": pd.to_datetime(value["window_start"]),
            "window_end":   pd.to_datetime(value["window_end"])
        })
    return records

new_records = fetch_data(consumer)
st.session_state.records.extend(new_records)

# Keep only the last 500 rows to avoid memory bloat
if st.session_state.records:
    df = pd.DataFrame(st.session_state.records).tail(500).reset_index(drop=True)
else:
    df = pd.DataFrame()

# ─── Display ─────────────────────────────────────────────────────────────────
if df.empty:
    st.info("⏳ Waiting for data from Kafka... make sure the producer and Spark job are running.")
    st.stop()

# ── KPI metrics (latest window per symbol) ───────────────────────────────────
st.subheader("📌 Latest KPIs")
latest = df.sort_values("window_end").groupby("symbol").last().reset_index()

cols = st.columns(len(latest))
for col_ui, (_, row) in zip(cols, latest.iterrows()):
    spread = row["max_price"] - row["min_price"]
    col_ui.metric(
        label=f"🪙 {row['symbol']}",
        value=f"${row['avg_price']:,.2f}",
        delta=f"spread ${spread:,.2f}"
    )
    col_ui.caption(f"min ${row['min_price']:,.2f} | max ${row['max_price']:,.2f} | n={int(row['count'])}")

st.divider()

# ── Chart 1 : Time series — avg price per window ─────────────────────────────
st.subheader("📊 Average Price — Sliding Window (5 min / 1 min)")
fig_line = px.line(
    df.sort_values("window_end"),
    x="window_end",
    y="avg_price",
    color="symbol",
    labels={"window_end": "Window End", "avg_price": "Avg Price (USD)", "symbol": "Symbol"},
    markers=True
)
st.plotly_chart(fig_line, use_container_width=True)

st.divider()

# ── Chart 2 : Bar chart — min / avg / max for the latest window ──────────────
st.subheader("🏆 Price Range — Latest Window per Symbol")
last_window = df.sort_values("window_end").groupby("symbol").last().reset_index()
bar_data = last_window.melt(
    id_vars="symbol",
    value_vars=["min_price", "avg_price", "max_price"],
    var_name="metric",
    value_name="price"
)
fig_bar = px.bar(
    bar_data,
    x="symbol",
    y="price",
    color="metric",
    barmode="group",
    labels={"price": "Price (USD)", "symbol": "Symbol", "metric": "Metric"},
    color_discrete_map={
        "min_price": "#3b82f6",
        "avg_price": "#f59e0b",
        "max_price": "#ef4444"
    }
)
st.plotly_chart(fig_bar, use_container_width=True)

st.divider()

# ── Raw data table ────────────────────────────────────────────────────────────
with st.expander("🔍 Raw aggregated data"):
    st.dataframe(
        df.sort_values("window_end", ascending=False)
          [["symbol", "avg_price", "min_price", "max_price", "count", "window_start", "window_end"]],
        use_container_width=True
    )