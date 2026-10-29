from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import date, datetime, timedelta
import pandas as pd
import plotly.express as px
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(__import__('os').environ.get('DENTAL_DB_PATH', str(APP_DIR / 'clinic.db')))

st.set_page_config(page_title="Dental Clinic OS", page_icon="🦷", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 1.2rem; max-width: 1500px;}
[data-testid="stMetric"] {background:#f7f9fc;border:1px solid #e5eaf2;padding:14px 16px;border-radius:12px;}
.hero {padding:20px 22px;border-radius:16px;background:linear-gradient(120deg,#eaf5ff,#f4fbf7);border:1px solid #dceaf4;margin-bottom:16px;}
</style>
""", unsafe_allow_html=True)

# ---------------- Database ----------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_code TEXT UNIQUE,
            full_name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            registration_date TEXT NOT NULL,
            notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            appointment_date TEXT NOT NULL,
            reason TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Booked',
            notes TEXT DEFAULT '',
            FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE RESTRICT
        );
        CREATE TABLE IF NOT EXISTS treatment_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            plan_date TEXT NOT NULL,
            description TEXT NOT NULL,
            estimated_amount REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Presented',
            notes TEXT DEFAULT '',
            FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE RESTRICT
        );
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            payment_date TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0),
            method TEXT DEFAULT 'UPI',
            description TEXT DEFAULT '',
            FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE RESTRICT
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expense_date TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT DEFAULT '',
            amount REAL NOT NULL CHECK(amount >= 0)
        );
        CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(appointment_date);
        CREATE INDEX IF NOT EXISTS idx_payments_date ON payments(payment_date);
        CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(expense_date);
        """)


def query_df(sql: str, params=()) -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def execute(sql: str, params=()):
    with get_conn() as conn:
        conn.execute(sql, params)
        conn.commit()


def money(value) -> str:
    return f"₹{float(value or 0):,.0f}"


def patient_options() -> tuple[list[str], dict[str, int]]:
    patients = query_df("SELECT id, patient_code, full_name, phone FROM patients ORDER BY full_name")
    labels = []
    mapping = {}
    for row in patients.itertuples(index=False):
        label = f"{row.patient_code or ('P'+str(row.id))} · {row.full_name}" + (f" · {row.phone}" if row.phone else "")
        labels.append(label)
        mapping[label] = int(row.id)
    return labels, mapping

init_db()

st.markdown('<div class="hero"><h1>🦷 Dental Clinic OS</h1><p>Clinic management and growth metrics in one place — prototype v0.2</p></div>', unsafe_allow_html=True)
st.warning("Prototype only. Use synthetic/test records until security, authentication, backups, and durable hosting are implemented. Do not deploy this version for real patient data on a public link.", icon="🔒")

# ---------------- Navigation ----------------
dashboard, patients_tab, appointments_tab, treatment_tab, payments_tab, expenses_tab, export_tab = st.tabs([
    "📊 Growth dashboard", "👤 Patients", "📅 Appointments", "🦷 Treatment plans", "💳 Payments", "🧾 Expenses", "📤 Export"
])

with dashboard:
    st.subheader("Practice performance")
    period = st.selectbox("Reporting period", ["This month", "Last 30 days", "This year", "All time"], index=0, key="dash_period")
    today = date.today()
    if period == "This month":
        start = today.replace(day=1)
    elif period == "Last 30 days":
        start = today - timedelta(days=29)
    elif period == "This year":
        start = today.replace(month=1, day=1)
    else:
        start = date(2000, 1, 1)
    start_s, end_s = start.isoformat(), today.isoformat()

    rev_df = query_df("SELECT COALESCE(SUM(amount),0) AS total FROM payments WHERE payment_date BETWEEN ? AND ?", (start_s, end_s))
    exp_df = query_df("SELECT COALESCE(SUM(amount),0) AS total FROM expenses WHERE expense_date BETWEEN ? AND ?", (start_s, end_s))
    revenue = float(rev_df.iloc[0]['total'])
    expenses = float(exp_df.iloc[0]['total'])
    appts = query_df("SELECT status, COUNT(*) AS n FROM appointments WHERE appointment_date BETWEEN ? AND ? GROUP BY status", (start_s, end_s))
    status_counts = {str(r['status']): int(r['n']) for _, r in appts.iterrows()}
    booked = sum(status_counts.values())
    attended = status_counts.get('Completed', 0)
    attendance_rate = attended / booked * 100 if booked else 0
    new_patients = int(query_df("SELECT COUNT(*) AS n FROM patients WHERE registration_date BETWEEN ? AND ?", (start_s, end_s)).iloc[0]['n'])
    plans = query_df("SELECT status, COUNT(*) AS n, COALESCE(SUM(estimated_amount),0) AS value FROM treatment_plans WHERE plan_date BETWEEN ? AND ? GROUP BY status", (start_s, end_s))
    presented_count = int(plans[plans['status'].isin(['Presented','Accepted','Declined'])]['n'].sum()) if not plans.empty else 0
    accepted_count = int(plans[plans['status'] == 'Accepted']['n'].sum()) if not plans.empty else 0
    acceptance = accepted_count / presented_count * 100 if presented_count else 0
    outstanding_value = float(query_df("SELECT COALESCE(SUM(estimated_amount),0) AS total FROM treatment_plans WHERE status IN ('Presented','Pending')").iloc[0]['total'])

    cols = st.columns(4)
    cols[0].metric("Collections", money(revenue))
    cols[1].metric("Recorded expenses", money(expenses))
    cols[2].metric("Net operating result", money(revenue-expenses), help="Collections minus expenses entered; not formal accounting profit.")
    cols[3].metric("Appointment attendance", f"{attendance_rate:.1f}%")
    cols = st.columns(4)
    cols[0].metric("Appointments", f"{booked:,}")
    cols[1].metric("New patients", f"{new_patients:,}")
    cols[2].metric("Treatment acceptance", f"{acceptance:.1f}%")
    cols[3].metric("Presented/pending plan value", money(outstanding_value))

    monthly = query_df("""
        SELECT substr(payment_date,1,7) AS month, SUM(amount) AS collections
        FROM payments WHERE payment_date BETWEEN ? AND ? GROUP BY substr(payment_date,1,7) ORDER BY month
    """, (start_s, end_s))
    monthly_exp = query_df("""
        SELECT substr(expense_date,1,7) AS month, SUM(amount) AS expenses
        FROM expenses WHERE expense_date BETWEEN ? AND ? GROUP BY substr(expense_date,1,7) ORDER BY month
    """, (start_s, end_s))
    monthly_all = pd.merge(monthly, monthly_exp, on='month', how='outer').fillna(0) if not monthly.empty or not monthly_exp.empty else pd.DataFrame()
    if not monthly_all.empty:
        # SQLite may return integer, float, or object columns depending on the
        # records entered. Normalize both series before plotting to avoid
        # Plotly Express wide-form mixed-dtype errors.
        for col in ('collections', 'expenses'):
            monthly_all[col] = pd.to_numeric(monthly_all[col], errors='coerce').fillna(0).astype(float)
        monthly_all['month'] = monthly_all['month'].astype(str)
        monthly_all['net_result'] = monthly_all['collections'] - monthly_all['expenses']
        left, right = st.columns(2)
        with left:
            chart_data = monthly_all.melt(
                id_vars=['month'],
                value_vars=['collections', 'expenses'],
                var_name='type',
                value_name='amount',
            )
            st.plotly_chart(
                px.bar(chart_data, x='month', y='amount', color='type', barmode='group',
                       title='Collections vs expenses',
                       labels={'amount': 'Amount (₹)', 'month': 'Month', 'type': 'Category'}),
                use_container_width=True,
            )
        with right:
            st.plotly_chart(px.line(monthly_all, x='month', y='net_result', markers=True, title='Net operating result by month', labels={'net_result':'Amount (₹)','month':'Month'}), use_container_width=True)
    else:
        st.info("Add payments and expenses to see financial trends. The dashboard starts empty intentionally; no fake clinic data is inserted.")

    st.subheader("Operational prompts (rule-based, not AI yet)")
    prompts = []
    if booked and attendance_rate < 80:
        prompts.append(f"Attendance is {attendance_rate:.1f}%. Review missed/cancelled appointment patterns and reminder workflows.")
    if presented_count and acceptance < 50:
        prompts.append(f"Treatment-plan acceptance is {acceptance:.1f}%. Review how estimates, options, and follow-up are explained and documented.")
    if revenue and expenses/revenue > 0.65:
        prompts.append(f"Recorded expenses are {expenses/revenue:.1%} of collections in this period. Check expense categorisation and compare with your own past months.")
    if not prompts:
        prompts.append("As you enter real operational records, this area will surface simple patterns to investigate. These are prompts, not clinical or financial advice.")
    for prompt in prompts:
        st.write("• " + prompt)

with patients_tab:
    st.subheader("Patient register")
    with st.form("add_patient", clear_on_submit=True):
        c1, c2 = st.columns(2)
        full_name = c1.text_input("Full name *")
        phone = c2.text_input("Phone")
        email = c1.text_input("Email (optional)")
        registration_date = c2.date_input("Registration date", value=date.today())
        notes = st.text_area("Administrative notes only (optional)", help="Avoid unnecessary sensitive clinical details in this prototype.")
        submitted = st.form_submit_button("Add patient", type="primary")
        if submitted:
            if not full_name.strip():
                st.error("Patient name is required.")
            else:
                code = "P" + datetime.now().strftime("%y%m%d%H%M%S%f")[-12:]
                try:
                    execute("INSERT INTO patients(patient_code,full_name,phone,email,registration_date,notes) VALUES(?,?,?,?,?,?)", (code, full_name.strip(), phone.strip(), email.strip(), registration_date.isoformat(), notes.strip()))
                    st.success(f"Patient added. ID: {code}")
                    st.rerun()
                except sqlite3.IntegrityError as e:
                    st.error(f"Could not add patient: {e}")
    patients = query_df("SELECT id, patient_code AS 'Patient ID', full_name AS 'Name', phone AS 'Phone', email AS 'Email', registration_date AS 'Registered', notes AS 'Admin notes' FROM patients ORDER BY id DESC")
    st.dataframe(patients.drop(columns=['id']) if not patients.empty else patients, use_container_width=True, hide_index=True)
    if not patients.empty:
        with st.expander("Update or remove a test patient"):
            st.caption("Deletion is blocked if appointments, treatment plans, or payments are linked to the patient.")
            chosen = st.selectbox("Choose patient", patients['id'].tolist(), format_func=lambda x: f"{patients.loc[patients.id==x, 'Patient ID'].iloc[0]} · {patients.loc[patients.id==x, 'Name'].iloc[0]}")
            if st.button("Delete selected patient", key="delete_patient"):
                try:
                    execute("DELETE FROM patients WHERE id=?", (int(chosen),))
                    st.success("Patient deleted.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("This patient has linked records. Keep the record and use an appropriate retention/deactivation process instead.")

with appointments_tab:
    st.subheader("Appointments")
    labels, pmap = patient_options()
    if not labels:
        st.info("Add a patient first to create an appointment.")
    else:
        with st.form("add_appointment", clear_on_submit=True):
            patient_label = st.selectbox("Patient", labels)
            appt_date = st.date_input("Appointment date", value=date.today(), key="appt_date")
            reason = st.text_input("Appointment type / reason")
            status = st.selectbox("Status", ["Booked", "Completed", "Cancelled", "No-show", "Rescheduled"])
            appt_notes = st.text_input("Administrative note (optional)")
            submitted = st.form_submit_button("Save appointment", type="primary")
            if submitted:
                execute("INSERT INTO appointments(patient_id,appointment_date,reason,status,notes) VALUES(?,?,?,?,?)", (pmap[patient_label], appt_date.isoformat(), reason.strip(), status, appt_notes.strip()))
                st.success("Appointment saved.")
                st.rerun()
    appointments = query_df("SELECT a.id, a.appointment_date AS Date, p.patient_code AS 'Patient ID', p.full_name AS Patient, a.reason AS Reason, a.status AS Status, a.notes AS Notes FROM appointments a JOIN patients p ON p.id=a.patient_id ORDER BY a.appointment_date DESC, a.id DESC")
    st.dataframe(appointments.drop(columns=['id']) if not appointments.empty else appointments, use_container_width=True, hide_index=True)
    if not appointments.empty:
        with st.form("update_appointment_status"):
            appt_id = st.selectbox("Appointment to update", appointments['id'].tolist(), format_func=lambda x: f"#{x} · {appointments.loc[appointments.id==x,'Date'].iloc[0]} · {appointments.loc[appointments.id==x,'Patient'].iloc[0]}")
            new_status = st.selectbox("New status", ["Booked", "Completed", "Cancelled", "No-show", "Rescheduled"])
            if st.form_submit_button("Update status"):
                execute("UPDATE appointments SET status=? WHERE id=?", (new_status, int(appt_id)))
                st.success("Appointment updated.")
                st.rerun()

with treatment_tab:
    st.subheader("Treatment plans")
    labels, pmap = patient_options()
    if not labels:
        st.info("Add a patient first to record a treatment plan.")
    else:
        with st.form("add_treatment_plan", clear_on_submit=True):
            patient_label = st.selectbox("Patient", labels, key="tp_patient")
            plan_date = st.date_input("Plan date", value=date.today(), key="plan_date")
            description = st.text_input("Plan description *", placeholder="e.g., restorative treatment plan")
            amount = st.number_input("Estimated amount (₹)", min_value=0.0, step=500.0)
            plan_status = st.selectbox("Status", ["Presented", "Accepted", "Pending", "Declined", "Completed"])
            plan_notes = st.text_input("Note (optional)")
            submitted = st.form_submit_button("Save treatment plan", type="primary")
            if submitted:
                if not description.strip():
                    st.error("Enter a plan description.")
                else:
                    execute("INSERT INTO treatment_plans(patient_id,plan_date,description,estimated_amount,status,notes) VALUES(?,?,?,?,?,?)", (pmap[patient_label], plan_date.isoformat(), description.strip(), float(amount), plan_status, plan_notes.strip()))
                    st.success("Treatment plan saved.")
                    st.rerun()
    plans_df = query_df("SELECT t.id, t.plan_date AS Date, p.patient_code AS 'Patient ID', p.full_name AS Patient, t.description AS Plan, t.estimated_amount AS 'Estimate (₹)', t.status AS Status, t.notes AS Notes FROM treatment_plans t JOIN patients p ON p.id=t.patient_id ORDER BY t.plan_date DESC, t.id DESC")
    st.dataframe(plans_df.drop(columns=['id']) if not plans_df.empty else plans_df, use_container_width=True, hide_index=True)
    if not plans_df.empty:
        with st.form("update_treatment_status"):
            plan_id = st.selectbox("Plan to update", plans_df['id'].tolist(), format_func=lambda x: f"#{x} · {plans_df.loc[plans_df.id==x,'Patient'].iloc[0]} · {plans_df.loc[plans_df.id==x,'Plan'].iloc[0]}")
            new_plan_status = st.selectbox("New status", ["Presented", "Accepted", "Pending", "Declined", "Completed"])
            if st.form_submit_button("Update plan status"):
                execute("UPDATE treatment_plans SET status=? WHERE id=?", (new_plan_status, int(plan_id)))
                st.success("Treatment plan updated.")
                st.rerun()

with payments_tab:
    st.subheader("Payments / collections")
    labels, pmap = patient_options()
    if not labels:
        st.info("Add a patient first to record a payment.")
    else:
        with st.form("add_payment", clear_on_submit=True):
            patient_label = st.selectbox("Patient", labels, key="pay_patient")
            pay_date = st.date_input("Payment date", value=date.today(), key="pay_date")
            amount = st.number_input("Amount received (₹)", min_value=0.0, step=500.0, key="pay_amount")
            method = st.selectbox("Payment method", ["UPI", "Cash", "Card", "Bank transfer", "Other"])
            description = st.text_input("Reference / description")
            submitted = st.form_submit_button("Record payment", type="primary")
            if submitted:
                if amount <= 0:
                    st.error("Payment amount must be greater than zero.")
                else:
                    execute("INSERT INTO payments(patient_id,payment_date,amount,method,description) VALUES(?,?,?,?,?)", (pmap[patient_label], pay_date.isoformat(), float(amount), method, description.strip()))
                    st.success("Payment recorded.")
                    st.rerun()
    payment_df = query_df("SELECT x.id, x.payment_date AS Date, p.patient_code AS 'Patient ID', p.full_name AS Patient, x.amount AS 'Amount (₹)', x.method AS Method, x.description AS Description FROM payments x JOIN patients p ON p.id=x.patient_id ORDER BY x.payment_date DESC, x.id DESC")
    st.dataframe(payment_df.drop(columns=['id']) if not payment_df.empty else payment_df, use_container_width=True, hide_index=True)

with expenses_tab:
    st.subheader("Clinic expenses")
    with st.form("add_expense", clear_on_submit=True):
        expense_date = st.date_input("Expense date", value=date.today())
        category = st.selectbox("Category", ["Rent", "Salaries", "Lab charges", "Materials", "Utilities", "Marketing", "Equipment", "Software", "Maintenance", "Other"])
        description = st.text_input("Description")
        amount = st.number_input("Amount (₹)", min_value=0.0, step=500.0, key="expense_amount")
        submitted = st.form_submit_button("Record expense", type="primary")
        if submitted:
            if amount <= 0:
                st.error("Expense amount must be greater than zero.")
            else:
                execute("INSERT INTO expenses(expense_date,category,description,amount) VALUES(?,?,?,?)", (expense_date.isoformat(), category, description.strip(), float(amount)))
                st.success("Expense recorded.")
                st.rerun()
    expense_df = query_df("SELECT id, expense_date AS Date, category AS Category, description AS Description, amount AS 'Amount (₹)' FROM expenses ORDER BY expense_date DESC, id DESC")
    st.dataframe(expense_df, use_container_width=True, hide_index=True)

with export_tab:
    st.subheader("Export your clinic records")
    st.caption("Exports contain identifiable patient information. Store downloaded files securely and share only with authorised people.")
    export_map = {
        "Patients": "SELECT patient_code AS patient_id, full_name, phone, email, registration_date, notes FROM patients ORDER BY id",
        "Appointments": "SELECT a.id, p.patient_code AS patient_id, p.full_name, a.appointment_date, a.reason, a.status, a.notes FROM appointments a JOIN patients p ON p.id=a.patient_id ORDER BY a.id",
        "Treatment plans": "SELECT t.id, p.patient_code AS patient_id, p.full_name, t.plan_date, t.description, t.estimated_amount, t.status, t.notes FROM treatment_plans t JOIN patients p ON p.id=t.patient_id ORDER BY t.id",
        "Payments": "SELECT x.id, p.patient_code AS patient_id, p.full_name, x.payment_date, x.amount, x.method, x.description FROM payments x JOIN patients p ON p.id=x.patient_id ORDER BY x.id",
        "Expenses": "SELECT id, expense_date, category, description, amount FROM expenses ORDER BY id",
    }
    for label, sql in export_map.items():
        data = query_df(sql)
        st.download_button(f"Download {label} CSV", data.to_csv(index=False).encode('utf-8'), file_name=label.lower().replace(' ','_')+'.csv', mime='text/csv', key='export_'+label)
    st.divider()
    st.markdown("**Database location**")
    st.code(str(DB_PATH))
    st.caption("Back up the database file only when the app is stopped or using a safe backup method. For hosted deployment, move to managed PostgreSQL with access controls and automated backups before real use.")

st.sidebar.markdown("### Prototype notes")
st.sidebar.caption("Single-clinic local SQLite prototype. No login, roles, audit log, encrypted database, automated backups, or multi-clinic separation yet.")
st.sidebar.caption("Built with Streamlit + SQLite + Pandas + Plotly")


