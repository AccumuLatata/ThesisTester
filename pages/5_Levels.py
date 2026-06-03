import plotly.graph_objects as go
import streamlit as st

from thesistester.data.sessions import tag_session
from thesistester.levels import compute_session_levels

st.title("📏 Levels")

if "data" not in st.session_state:
    st.warning("No data loaded. Please load data from the Data page first.")
    st.stop()

instrument = st.session_state.get("instrument", "ES")
opening_range_minutes = st.selectbox("Opening range duration (minutes)", [5, 15, 30], index=2)

base_df = st.session_state["data"]
if "session" not in base_df.columns:
    base_df = tag_session(base_df, instrument)

levels_df = compute_session_levels(
    base_df,
    instrument=instrument,
    opening_range_minutes=opening_range_minutes,
)
st.session_state["session_levels"] = levels_df

level_columns = [
    "ONH",
    "ONL",
    "OR_High",
    "OR_Low",
    "RTH_Open",
    "prevSettlement",
    "dOpen",
    "wOpen",
    "mOpen",
    "pdOpen",
    "pwOpen",
    "pmOpen",
    "pdHigh",
    "pdLow",
    "pwHigh",
    "pwLow",
    "pmHigh",
    "pmLow",
    "pdEQ",
    "pwEQ",
    "pmEQ",
]

st.subheader("Session levels preview")
preview_cols = ["timestamp", "close", "session", *level_columns]
st.dataframe(levels_df[preview_cols].tail(200), use_container_width=True)

selected_levels = st.multiselect(
    "Levels to plot",
    options=level_columns,
    default=["RTH_Open", "OR_High", "OR_Low", "ONH", "ONL"],
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
