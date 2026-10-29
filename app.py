from __future__ import annotations

from io import BytesIO
from datetime import date
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Dental Practice Growth Analytics",
    page_icon="🦷",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- Theme / helpers ----------
st.markdown("""
<style>
    .block-container {padding-top: 1.5rem; padding-bottom: 2.5rem; max-width: 1440px;}
    [data-testid="stMetric"] {background: #f7f9fc; border: 1px solid #e5eaf2; padding: 16px 18px; border-radius: 14px;}
    .hero {padding: 22px 24px; border-radius: 18px; background: linear-gradient(120deg,#eaf5ff,#f4fbf7); border: 1px solid #dceaf4; margin-bottom: 18px;}
    .hero h1 {margin: 0 0 6px 0; font-size: 1.9rem;}
    .hero p {margin: 0; color: #425466;}
    .small-note {font-size: 0.85rem; color: #617184;}
    div[data-testid="stDataFrame"] {border-radius: 12px;}
</style>
""", unsafe_allow_html=True)

REQUIRED_COLUMNS = [
    "date", "revenue", "expenses", "appointments_booked",
    "appointments_attended", "treatment_plans_presented",
    "treatment_plans_accepted", "new_patients", "returning_patients"
]
NUMERIC_COLUMNS = REQUIRED_COLUMNS[1:]

@st.cache_data
def make_sample_data() -> pd.DataFrame:
    # Synthetic monthly practice-level data; no real patient data.
    dates = pd.date_range(end=pd.Timestamp.today().normalize().replace(day=1), periods=12, freq="MS")
    rows = []
    for i, dt in enumerate(dates):
        seasonal = 1 + 0.08 * ((i % 4) - 1.5)
        booked = int(155 + i * 2 + (i % 3) * 7)
        attended = int(booked * (0.77 + (i % 4) * 0.025))
        presented = int(attended * 0.55)
        accepted = int(presented * (0.48 + (i % 3) * 0.04))
        revenue = round((245000 + i * 9000) * seasonal, 0)
        expenses = round(revenue * (0.53 + (i % 3) * 0.015), 0)
        rows.append({
            "date": dt.date().isoformat(),
            "revenue": int(revenue),
            "expenses": int(expenses),
            "appointments_booked": booked,
            "appointments_attended": attended,
            "treatment_plans_presented": presented,
            "treatment_plans_accepted": accepted,
            "new_patients": int(18 + (i % 5) * 2),
            "returning_patients": int(58 + i * 2 + (i % 3) * 4),
        })
    return pd.DataFrame(rows)

def normalize_data(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))
    df = df[REQUIRED_COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if df["date"].isna().any():
        raise ValueError("Some dates could not be read. Use YYYY-MM-DD, for example 2026-01-31.")
    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        if df[col].isna().any():
            raise ValueError(f"Column '{col}' contains blank or non-numeric values.")
        if (df[col] < 0).any():
            raise ValueError(f"Column '{col}' cannot contain negative values.")
    if (df["appointments_attended"] > df["appointments_booked"]).any():
        raise ValueError("Attended appointments cannot exceed appointments booked.")
    if (df["treatment_plans_accepted"] > df["treatment_plans_presented"]).any():
        raise ValueError("Accepted treatment plans cannot exceed plans presented.")
    return df.sort_values("date").reset_index(drop=True)

def inr(value: float) -> str:
    return "₹" + f"{value:,.0f}"

def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")

# ---------- Sidebar ----------
st.sidebar.title("🦷 Practice Analytics")
st.sidebar.caption("Version 0.1 · MVP")
source = st.sidebar.radio("Data source", ["Use sample data", "Upload my CSV"], index=0)
uploaded = None
if source == "Upload my CSV":
    uploaded = st.sidebar.file_uploader("Upload monthly clinic metrics (.csv)", type=["csv"])
st.sidebar.divider()
st.sidebar.markdown("**Privacy first**")
st.sidebar.caption("Start with synthetic data. Do not upload identifiable patient records. Use aggregated clinic-level metrics only until secure data handling is implemented.")
st.sidebar.markdown("---")
st.sidebar.caption("Built with Python · Streamlit · Pandas · Plotly")

# ---------- Load data ----------
if source == "Use sample data":
    df = make_sample_data()
    is_sample = True
elif uploaded is not None:
    try:
        df = normalize_data(pd.read_csv(uploaded))
        is_sample = False
    except Exception as exc:
        st.error(f"Could not use this CSV: {exc}")
        st.info("Download the template from the Data & Export page, fill it with monthly aggregate figures, then upload it again.")
        st.stop()
else:
    st.markdown('<div class="hero"><h1>Welcome to Dental Practice Growth Analytics</h1><p>Upload a monthly metrics CSV from the sidebar, or switch to sample data to explore the dashboard.</p></div>', unsafe_allow_html=True)
    st.stop()

# Normalize date dtype for both sample data and uploaded CSVs.
# Keep this conversion immediately before using the pandas .dt accessor.
df["date"] = pd.to_datetime(df["date"], errors="coerce")
if df["date"].isna().any():
    st.error("The date column contains invalid values. Please use dates such as 2026-01-01.")
    st.stop()

# Derived metrics
df["net_operating_result"] = df["revenue"] - df["expenses"]
df["attendance_rate"] = (df["appointments_attended"] / df["appointments_booked"].replace(0, pd.NA) * 100).fillna(0)
df["treatment_acceptance_rate"] = (df["treatment_plans_accepted"] / df["treatment_plans_presented"].replace(0, pd.NA) * 100).fillna(0)
df["total_patients_seen"] = df["new_patients"] + df["returning_patients"]
df["month"] = df["date"].dt.strftime("%b %Y")

# ---------- Header ----------
st.markdown(f"""
<div class="hero">
  <h1>Dental Practice Growth Analytics</h1>
  <p>Understand your clinic's performance, spot trends, and choose your next action.</p>
</div>
""", unsafe_allow_html=True)
if is_sample:
    st.info("You are viewing **synthetic sample data**. Figures are illustrative and do not represent a real clinic.", icon="ℹ️")

# Date range filter
min_date, max_date = df["date"].min().date(), df["date"].max().date()
with st.sidebar:
    st.subheader("Filter period")
    date_range = st.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date, max_date
view = df[(df["date"].dt.date >= start_date) & (df["date"].dt.date <= end_date)].copy()
if view.empty:
    st.warning("No rows in the selected date range.")
    st.stop()

# ---------- Navigation ----------
overview, trends, actions, data_tab = st.tabs(["Overview", "Trends", "Action ideas", "Data & export"])

with overview:
    st.subheader("Practice at a glance")
    total_revenue = view["revenue"].sum()
    total_expenses = view["expenses"].sum()
    net = view["net_operating_result"].sum()
    booked = view["appointments_booked"].sum()
    attended = view["appointments_attended"].sum()
    presented = view["treatment_plans_presented"].sum()
    accepted = view["treatment_plans_accepted"].sum()
    attendance = attended / booked * 100 if booked else 0
    acceptance = accepted / presented * 100 if presented else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total revenue", inr(total_revenue))
    c2.metric("Expenses", inr(total_expenses))
    c3.metric("Net operating result", inr(net), help="Revenue minus the expenses entered. Not a formal accounting profit figure.")
    c4.metric("Attendance rate", f"{attendance:.1f}%")
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Appointments booked", f"{booked:,.0f}")
    c6.metric("Appointments attended", f"{attended:,.0f}")
    c7.metric("Treatment acceptance", f"{acceptance:.1f}%")
    c8.metric("Patients seen", f"{view['total_patients_seen'].sum():,.0f}")

    left, right = st.columns(2)
    with left:
        fig = px.bar(view, x="month", y=["revenue", "expenses"], barmode="group",
                     title="Revenue vs expenses", labels={"value": "Amount (₹)", "month": "Month", "variable": ""})
        fig.update_layout(legend_title_text="", margin=dict(l=10,r=10,t=55,b=10))
        st.plotly_chart(fig, use_container_width=True)
    with right:
        fig = px.line(view, x="month", y="net_operating_result", markers=True,
                      title="Net operating result by month", labels={"net_operating_result": "Amount (₹)", "month": "Month"})
        fig.update_layout(margin=dict(l=10,r=10,t=55,b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Monthly snapshot")
    display = view[["month", "revenue", "expenses", "net_operating_result", "appointments_booked", "appointments_attended", "attendance_rate", "treatment_acceptance_rate"]].copy()
    display = display.rename(columns={"month":"Month","revenue":"Revenue (₹)","expenses":"Expenses (₹)","net_operating_result":"Net result (₹)","appointments_booked":"Booked","appointments_attended":"Attended","attendance_rate":"Attendance (%)","treatment_acceptance_rate":"Acceptance (%)"})
    st.dataframe(display, use_container_width=True, hide_index=True)

with trends:
    st.subheader("Performance trends")
    left, right = st.columns(2)
    with left:
        fig = px.line(view, x="month", y=["attendance_rate", "treatment_acceptance_rate"], markers=True,
                      title="Attendance and treatment acceptance",
                      labels={"value":"Rate (%)","month":"Month","variable":"Metric"})
        fig.update_layout(legend_title_text="", yaxis_ticksuffix="%", margin=dict(l=10,r=10,t=55,b=10))
        st.plotly_chart(fig, use_container_width=True)
    with right:
        patient_trend = view[["month", "new_patients", "returning_patients"]].melt(id_vars="month", var_name="patient_type", value_name="count")
        fig = px.bar(patient_trend, x="month", y="count", color="patient_type", barmode="stack",
                     title="New vs returning patients", labels={"count":"Patients","month":"Month","patient_type":"Type"})
        fig.update_layout(legend_title_text="", margin=dict(l=10,r=10,t=55,b=10))
        st.plotly_chart(fig, use_container_width=True)
    st.caption("These are descriptive metrics, not benchmarks. Compare against your own historical performance and clinic context.")

with actions:
    st.subheader("Suggested areas to investigate")
    st.caption("These rules are simple prompts for review, not clinical or financial advice.")
    suggestions = []
    if attendance < 80:
        suggestions.append(("Review appointment attendance", f"Attendance is {attendance:.1f}%. Review cancellation patterns, reminder timing, and rescheduling workflows."))
    if acceptance < 50 and presented > 0:
        suggestions.append(("Review treatment-plan follow-through", f"Acceptance is {acceptance:.1f}%. Review how options, estimates, and follow-up conversations are documented."))
    if total_revenue > 0 and net / total_revenue < 0.35:
        suggestions.append(("Review operating costs", f"Expenses represent {(total_expenses/total_revenue*100):.1f}% of revenue in the selected period. Check cost categories and whether all figures are entered consistently."))
    if len(view) >= 2:
        first_rev, last_rev = view.iloc[0]["revenue"], view.iloc[-1]["revenue"]
        if first_rev and last_rev < first_rev:
            suggestions.append(("Investigate revenue trend", "Revenue in the last selected month is below the first selected month. Compare appointment volume, case mix, and seasonality before drawing conclusions."))
    if not suggestions:
        suggestions.append(("Choose one metric to improve", "No simple rule was triggered. Compare month-to-month changes and select one operational metric to investigate."))
    for title, body in suggestions:
        with st.container(border=True):
            st.markdown(f"**{title}**")
            st.write(body)
    st.markdown("#### Weekly experiment")
    st.write("Pick one operational change, record the date, and compare the relevant metric over a consistent period. Avoid changing several things at once.")

with data_tab:
    st.subheader("Data preview")
    st.dataframe(view[REQUIRED_COLUMNS], use_container_width=True, hide_index=True)
    st.download_button("Download filtered data (CSV)", data=to_csv_bytes(view[REQUIRED_COLUMNS]),
                       file_name="dental_practice_metrics.csv", mime="text/csv")
    st.download_button("Download CSV template", data=to_csv_bytes(make_sample_data()[REQUIRED_COLUMNS].head(0)),
                       file_name="dental_metrics_template.csv", mime="text/csv")
    st.markdown("#### Required CSV columns")
    st.code(", ".join(REQUIRED_COLUMNS), language="text")
    st.markdown("""
**Data definitions**
- One row per month; `date` can be any date within that month.
- `revenue` and `expenses`: aggregate amounts in INR.
- Appointment and treatment fields: non-negative monthly counts.
- `treatment_plans_accepted` must not exceed `treatment_plans_presented`.
- Use aggregated clinic-level figures. Do not include names, phone numbers, addresses, diagnoses, or other identifiable patient information.
""")

st.markdown("---")
st.markdown('<p class="small-note">Dental Practice Growth Analytics · MVP v0.1 · For operational exploration only. Validate inputs and consult your accountant for formal financial reporting.</p>', unsafe_allow_html=True)
