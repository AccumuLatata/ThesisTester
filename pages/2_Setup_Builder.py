import streamlit as st

st.title("\U0001F9E9 Setup Builder")
st.caption("Stub \u2014 wired up in Phase 4. Shows the planned configuration surface.")

st.subheader("Confluences (pick 1\u20135)")
st.write(
    "Dynamic: SMA, EMA, rolling VWAP (15m/30m/1h/4h), rolling POC (30m/1h/4h). "
    "Session: ONH/ONL, OR High/Low, RTH_Open, prevSettlement, d/w/m opens (+prior), "
    "prior d/w/m H/L, prior d/w/m EQ. Profile: pd/pw/pm VAH/VAL/POC. Plus a 'naked only' toggle."
)

st.subheader("Triggers")
st.write(
    "`touch`, `reject`, `break`, `reclaim`, and **`confirm_3bar`** "
    "(arrival \u2192 reversal close \u2192 x-tick retracement entry). See docs/ENGINEERING.md \u00a73.3."
)

st.info("Configuration controls land in Phase 4.")
