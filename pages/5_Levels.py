import plotly.graph_objects as go
import streamlit as st

from thesistester.data.sessions import tag_session
from thesistester.levels import compute_all_levels, compute_session_levels


def _parse_lengths(raw: str, label: str) -> list[int]:
    """Parse comma-separated length values for indicator controls."""
    lengths: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        value = int(token)
        if value <= 0:
            raise ValueError(f"{label} lengths must be positive integers, got: {value}")
        lengths.append(value)
    if not lengths:
        raise ValueError(f"Please provide at least one {label} length.")
    return sorted(set(lengths))

st.title("📏 Levels")

if "data" not in st.session_state:
    st.warning("No data loaded. Please load data from the Data page first.")
    st.stop()

instrument = st.session_state.get("instrument", "ES")
opening_range_minutes = st.selectbox("Opening range duration (minutes)", [5, 15, 30], index=2)
sma_lengths_raw = st.text_input("SMA lengths (comma-separated)", value="20,50,200")
ema_lengths_raw = st.text_input("EMA lengths (comma-separated)", value="20,50,200")
vwap_windows = st.multiselect(
    "Rolling VWAP windows",
    options=["15min", "30min", "1h", "4h"],
    default=["15min", "30min", "1h", "4h"],
)
poc_windows = st.multiselect(
    "Rolling POC windows",
    options=["30min", "1h", "4h"],
    default=["30min", "1h", "4h"],
)
value_area_pct = st.slider("Value area (%)", min_value=50, max_value=95, value=70, step=1) / 100.0

try:
    sma_lengths = _parse_lengths(sma_lengths_raw, "SMA")
    ema_lengths = _parse_lengths(ema_lengths_raw, "EMA")
except ValueError as exc:
    st.error(str(exc))
    st.stop()

current_settings = {
    "instrument": instrument,
    "opening_range_minutes": opening_range_minutes,
    "sma_lengths": sma_lengths,
    "ema_lengths": ema_lengths,
    "vwap_windows": sorted(vwap_windows),
    "poc_windows": sorted(poc_windows),
    "value_area_pct": value_area_pct,
}
previous_settings = st.session_state.get("levels_settings")
has_calculated_levels = "levels" in st.session_state and "session_levels" in st.session_state

button_label = "Recalculate levels" if has_calculated_levels else "Calculate levels"
calculate_levels = st.button(button_label, type="primary")

if calculate_levels:
    with st.spinner("Calculating levels..."):
        base_df = st.session_state["data"]
        if "session" not in base_df.columns:
            base_df = tag_session(base_df, instrument)

        levels_df = compute_all_levels(
            base_df,
            instrument=instrument,
            opening_range_minutes=opening_range_minutes,
            sma_lengths=sma_lengths,
            ema_lengths=ema_lengths,
            vwap_windows=vwap_windows,
            poc_windows=poc_windows,
            value_area_pct=value_area_pct,
        )

        session_levels = compute_session_levels(
            base_df,
            instrument=instrument,
            opening_range_minutes=opening_range_minutes,
        )
        st.session_state["session_levels"] = session_levels
        st.session_state["levels"] = levels_df
        st.session_state["levels_settings"] = current_settings

levels_df = st.session_state.get("levels")
if levels_df is None:
    st.info("Configure the settings above, then click **Calculate levels** to generate levels.")
    st.stop()

if previous_settings is not None and previous_settings != current_settings:
    st.info("Settings have changed. Click **Recalculate levels** to update results.")

base_columns = {"timestamp", "open", "high", "low", "close", "volume", "session", "settlement"}
level_columns = [col for col in levels_df.columns if col not in base_columns]

st.subheader("Levels preview")
preview_cols = ["timestamp", "close", "session", *level_columns]
st.dataframe(levels_df[preview_cols].tail(200), use_container_width=True)

selected_levels = st.multiselect(
    "Levels to plot",
    options=level_columns,
    default=[col for col in ["RTH_Open", "OR_High", "OR_Low", "ONH", "ONL"] if col in level_columns],
)

fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=levels_df["timestamp"],
        y=levels_df["close"],
        mode="lines",
        name="close",
    )
)

for col in selected_levels:
    fig.add_trace(
        go.Scatter(
            x=levels_df["timestamp"],
            y=levels_df[col],
            mode="lines",
            name=col,
        )
    )

fig.update_layout(height=520, margin=dict(l=10, r=10, t=35, b=10), legend=dict(orientation="h"))
st.plotly_chart(fig, use_container_width=True)
