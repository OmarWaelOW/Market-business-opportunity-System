"""EGY-CRETE Market Opportunity App.

TODO: add account administration and role-based permissions before production deployment.
R analysis runs through standalone Rscript subprocesses so rpy2 is not required.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import bcrypt
import pandas as pd
import streamlit as st

from analysis import run_clustering, run_forecast
from db import (
    add_competitor_move, add_input_cost, add_regional_signal, connect,
    create_user, delete_record, get_user, import_input_csv, import_workbook,
    initialize_db, read_table, update_record, user_count,
)


st.set_page_config(page_title="EGY-CRETE | Market Opportunities", page_icon="EC", layout="wide")
DB_PATH = Path(__file__).with_name("market_opportunities.db")


@st.cache_resource
def get_connection():
    connection = connect(DB_PATH)
    initialize_db(connection)
    return connection


connection = get_connection()


def create_account_form(label: str = "Create account") -> None:
    with st.form(f"{label.lower().replace(' ', '_')}_form"):
        username = st.text_input("Username")
        display_name = st.text_input("Display name")
        password = st.text_input("Password", type="password")
        confirmation = st.text_input("Confirm password", type="password")
        submitted = st.form_submit_button(label, type="primary")
    if submitted:
        if not username or not display_name or not password:
            st.error("Username, display name, and password are required.")
        elif password != confirmation:
            st.error("Passwords do not match.")
        elif len(password) < 8:
            st.error("Use a password with at least 8 characters.")
        else:
            try:
                password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
                create_user(connection, username, password_hash, display_name)
                st.success("Account created. You can now sign in.")
            except Exception:
                st.error("That username is already in use.")


def authenticate() -> None:
    if "user" in st.session_state:
        return
    st.title("EGY-CRETE")
    st.caption("Sign in to the market opportunity intelligence desk")
    if user_count(connection) == 0:
        st.info("Create the first account to initialize this private workspace.")
        create_account_form("Create first account")
        st.stop()
    login_tab, registration_tab = st.tabs(["Sign in", "Create account"])
    with login_tab:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", type="primary")
        if submitted:
            user = get_user(connection, username)
            if user and bcrypt.checkpw(password.encode("utf-8"), user["password_hash"]):
                st.session_state.user = {"id": user["id"], "display_name": user["display_name"]}
                st.rerun()
            st.error("Invalid username or password.")
    with registration_tab:
        create_account_form()
    st.stop()


authenticate()
current_user = st.session_state.user["display_name"]

st.markdown("""<style>
.block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1500px;}
[data-testid="stMetric"] {background: #f4f0e8; border-left: 4px solid #c66b32; padding: 1rem;}
h1, h2, h3 {font-family: Georgia, serif;}
</style>""", unsafe_allow_html=True)


def source_notice(frame: pd.DataFrame) -> None:
    if not frame.empty and "synthetic" in set(frame["data_source"].dropna()):
        st.warning("Synthetic test data is present in this view. Confirm the data source before making a market decision.")


def editor(table: str, frame: pd.DataFrame, fields: list[str], labels: dict[str, str]) -> None:
    if frame.empty:
        return
    st.subheader("Edit or delete a record")
    selected_id = st.selectbox("Record ID", frame["id"].tolist(), key=f"{table}_selected")
    record = frame[frame["id"] == selected_id].iloc[0]
    with st.form(f"{table}_editor"):
        values = {}
        for field in fields:
            value = record[field]
            if field.endswith("date"):
                value = pd.to_datetime(value).date()
                values[field] = st.date_input(labels[field], value, key=f"{table}_{field}")
            elif field in {"demand_growth", "supplier_coverage", "impact"}:
                values[field] = st.slider(labels[field], 1, 5, int(value), key=f"{table}_{field}")
            elif field == "price_egp":
                values[field] = st.number_input(labels[field], min_value=0.0, value=float(value), key=f"{table}_{field}")
            else:
                values[field] = st.text_area(labels[field], str(value or ""), key=f"{table}_{field}")
        save, remove = st.columns(2)
        save_clicked = save.form_submit_button("Save changes", type="primary")
        delete_clicked = remove.form_submit_button("Delete record")
    if save_clicked:
        for field, value in values.items():
            if isinstance(value, date):
                values[field] = value.isoformat()
        values["created_by"] = current_user
        update_record(connection, table, int(selected_id), values)
        st.success("Record updated.")
        st.rerun()
    if delete_clicked:
        delete_record(connection, table, int(selected_id))
        st.success("Record deleted.")
        st.rerun()


def dashboard():
    regional = read_table(connection, "regional_signals", "signal_date DESC")
    moves = read_table(connection, "competitor_moves", "move_date DESC")
    costs = read_table(connection, "input_cost_signals", "price_date DESC")
    source_notice(pd.concat([regional[["data_source"]], moves[["data_source"]], costs[["data_source"]]]))
    st.subheader("Executive view")
    quarter_start = (pd.Timestamp.today() - pd.offsets.QuarterBegin(startingMonth=1)).date().isoformat()
    high_count = int((regional["priority"] == "High").sum()) if not regional.empty else 0
    quarter_moves = moves[moves["move_date"] >= quarter_start] if not moves.empty else moves
    active = quarter_moves["competitor"].mode().iloc[0] if not quarter_moves.empty else "No moves logged"
    cement = costs[costs["input_type"].str.contains("Cement", case=False, na=False)] if not costs.empty else costs
    cement_trend = cement.iloc[0]["trend"] if not cement.empty else "No price logged"
    first, second, third = st.columns(3)
    first.metric("High-priority gaps", high_count)
    second.metric("Most active this quarter", active)
    third.metric("Latest cement trend", cement_trend)
    st.divider()
    st.write("Use the workspace tabs to capture signals, review movement, and run the Phase 2 models.")
    if not regional.empty:
        gap_by_region = regional.groupby("region", as_index=False)["opportunity_gap"].mean().sort_values("opportunity_gap", ascending=False)
        st.bar_chart(gap_by_region.set_index("region"), y="opportunity_gap", color="#c66b32")


def regional_page():
    st.header("Regional demand signals")
    frame = read_table(connection, "regional_signals", "opportunity_gap DESC, signal_date DESC")
    source_notice(frame)
    with st.form("regional_form", clear_on_submit=True):
        left, right = st.columns(2)
        region = left.text_input("Region")
        signal_observed = left.text_area("Signal observed")
        source = right.text_input("Source")
        signal_date = right.date_input("Date", date.today())
        demand_growth = left.slider("Demand Growth", 1, 5, 3)
        supplier_coverage = right.slider("Current Supplier Coverage", 1, 5, 3)
        if st.form_submit_button("Log regional signal", type="primary"):
            if not region or not signal_observed:
                st.error("Region and signal observed are required.")
            else:
                add_regional_signal(connection, locals() | {"created_by": current_user})
                st.success("Regional signal saved.")
    frame = read_table(connection, "regional_signals", "opportunity_gap DESC, signal_date DESC")
    if not frame.empty:
        regions = st.multiselect("Filter regions", sorted(frame["region"].unique()))
        priorities = st.multiselect("Filter priority", ["High", "Medium", "Low"])
        shown = frame[frame["region"].isin(regions)] if regions else frame
        shown = shown[shown["priority"].isin(priorities)] if priorities else shown
        st.dataframe(shown, use_container_width=True, hide_index=True)
        editor("regional_signals", frame, ["region", "signal_observed", "source", "signal_date", "demand_growth", "supplier_coverage"], {"region": "Region", "signal_observed": "Signal observed", "source": "Source", "signal_date": "Date", "demand_growth": "Demand Growth", "supplier_coverage": "Supplier Coverage"})
        st.bar_chart(frame.groupby("region", as_index=False)["opportunity_gap"].mean().set_index("region"), y="opportunity_gap", color="#c66b32")
    else:
        st.info("No regional signals logged yet.")


def competitor_page():
    st.header("Competitor & project moves")
    frame = read_table(connection, "competitor_moves", "move_date DESC, impact DESC")
    source_notice(frame)
    with st.form("competitor_form", clear_on_submit=True):
        left, right = st.columns(2)
        move_date = left.date_input("Date", date.today())
        competitor = left.text_input("Competitor / project")
        move_observed = left.text_area("Move observed")
        source = right.text_input("Source")
        impact = right.slider("Impact", 1, 5, 3)
        implication = right.text_area("Implication notes")
        action_owner = right.text_input("Action / Owner")
        if st.form_submit_button("Log competitor move", type="primary"):
            if not competitor or not move_observed:
                st.error("Competitor and move observed are required.")
            else:
                add_competitor_move(connection, locals() | {"created_by": current_user})
                st.success("Competitor move saved.")
    frame = read_table(connection, "competitor_moves", "move_date DESC, impact DESC")
    if not frame.empty:
        competitors = st.multiselect("Filter competitors", sorted(frame["competitor"].unique()))
        shown = frame[frame["competitor"].isin(competitors)] if competitors else frame
        st.dataframe(shown, use_container_width=True, hide_index=True)
        editor("competitor_moves", frame, ["move_date", "competitor", "move_observed", "source", "impact", "implication", "action_owner"], {"move_date": "Date", "competitor": "Competitor / project", "move_observed": "Move observed", "source": "Source", "impact": "Impact", "implication": "Implication notes", "action_owner": "Action / Owner"})
        timeline = frame.assign(move_date=pd.to_datetime(frame["move_date"])).set_index("move_date").groupby("competitor").resample("MS").size().unstack(0, fill_value=0)
        st.line_chart(timeline)
    else:
        st.info("No competitor moves logged yet.")


def costs_page():
    st.header("Input cost signals")
    frame = read_table(connection, "input_cost_signals", "price_date DESC")
    source_notice(frame)
    with st.form("cost_form", clear_on_submit=True):
        left, right = st.columns(2)
        price_date = left.date_input("Date", date.today())
        input_type = left.selectbox("Input type", ["Cement", "Aggregate", "Energy"])
        price_egp = right.number_input("Price (EGP)", min_value=0.0, step=1.0)
        source = right.text_input("Source")
        note = right.text_input("Note")
        if st.form_submit_button("Log input cost", type="primary"):
            add_input_cost(connection, locals() | {"created_by": current_user})
            st.success("Input cost saved with prior-month comparison.")
    uploaded = st.file_uploader("Import CSV or Excel history", type=["csv", "xlsx"])
    if uploaded and st.button("Import history"):
        try:
            counts = import_input_csv(connection, uploaded.getvalue(), current_user) if uploaded.name.lower().endswith(".csv") else import_workbook(connection, uploaded.getvalue(), uploaded.name, current_user)
            st.success(f"Imported {counts['input_cost']} input-cost rows; skipped {counts['duplicates']} duplicates.")
        except Exception as exc:
            st.error(f"Import failed: {exc}")
    frame = read_table(connection, "input_cost_signals", "price_date DESC")
    if not frame.empty:
        st.dataframe(frame, use_container_width=True, hide_index=True)
        editor("input_cost_signals", frame, ["price_date", "input_type", "price_egp", "source", "note"], {"price_date": "Date", "input_type": "Input type", "price_egp": "Price (EGP)", "source": "Source", "note": "Note"})
        chart = frame.assign(price_date=pd.to_datetime(frame["price_date"])).pivot_table(index="price_date", columns="input_type", values="price_egp", aggfunc="last").sort_index()
        st.line_chart(chart)
    else:
        st.info("No input costs logged yet.")


def analysis_page():
    st.header("Phase 2 analysis")
    forecast_tab, cluster_tab = st.tabs(["ARIMA cost forecast", "Regional clusters"])
    with forecast_tab:
        horizon = st.slider("Forecast months", 3, 6, 3)
        if st.button("Run cost forecast", type="primary"):
            result = run_forecast(connection, horizon)
            if result.error:
                st.info(result.error)
            else:
                st.line_chart(result.data.set_index("date")[['actual', 'forecast', 'lower', 'upper']])
                st.dataframe(result.data, use_container_width=True, hide_index=True)
    with cluster_tab:
        clusters = st.slider("Number of clusters", 2, 6, 3)
        if st.button("Run regional clustering", type="primary"):
            result = run_clustering(connection, clusters)
            if result.error:
                st.info(result.error)
            else:
                st.scatter_chart(result.data, x="demand_growth", y="supplier_coverage", color="cluster", size="opportunity_gap")
                st.dataframe(result.data, use_container_width=True, hide_index=True)


def import_page():
    st.header("Data import")
    st.write("Import the tracker template or synthetic workbook. Rows are mapped into normalized SQLite tables.")
    uploaded = st.file_uploader("Choose workbook", type=["xlsx"])
    if uploaded and st.button("Import workbook", type="primary"):
        try:
            counts = import_workbook(connection, uploaded.getvalue(), uploaded.name, current_user)
            st.success(f"Imported {counts['regional']} regional, {counts['competitor']} competitor, and {counts['input_cost']} input-cost rows; skipped {counts['duplicates']} duplicates.")
        except Exception as exc:
            st.error(f"Import failed: {exc}")
    st.download_button("Download regional CSV", read_table(connection, "regional_signals", "signal_date DESC").to_csv(index=False), "regional_signals.csv", "text/csv")


pages = {"Overview": dashboard, "Regional demand": regional_page, "Competitor moves": competitor_page, "Input costs": costs_page, "Phase 2 analysis": analysis_page, "Data import": import_page}
with st.sidebar:
    st.write(f"Signed in as **{current_user}**")
    if st.button("Sign out"):
        del st.session_state["user"]
        st.rerun()
    selection = st.radio("Workspace", list(pages))
pages[selection]()
