import sys
import os
import streamlit as st
import mysql.connector
import pandas as pd
import plotly.express as px

# Ensure backend folder is accessible
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.optimizer_logic import fetch_workload_kpis, parse_improvements

st.set_page_config(layout="wide", page_title="AutoDB E-Commerce Simulator")

def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="gandhiyash09",
        database="autodb_ecommerce"
    )

st.title("AutoDB: Adaptive Cost-Based Optimizer Simulator")
st.caption(
    "SQL queries natively executed in MySQL. "
    "Demonstrates dynamic Materialized Views generation, CBO valuations, and trace monitoring."
)

tab1, tab2 = st.tabs(["AutoDB Terminal & Runs", "Optimizer Analytics & Dashboard"])

def _strip_single_trailing_semicolon(sql_text):
    cleaned = sql_text.strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].rstrip()
    return cleaned

def _has_multiple_statements(sql_text):
    clean_q = sql_text.strip()
    parts = [p.strip() for p in clean_q.split(';')]
    valid_parts = [p for p in parts if p]
    return len(valid_parts) > 1

def _is_explain_result(column_names):
    explain_cols = {"id", "select_type", "table", "type", "possible_keys", "key", "key_len", "ref", "rows", "filtered", "extra", "partitions"}
    col_set = {str(col).lower() for col in column_names}
    if "query_block" in col_set: return True
    return len(col_set.intersection(explain_cols)) >= 5

def run_query(query_str):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    final_df = None
    run_metrics = None
    status_msg = None
    
    try:
        clean_q = _strip_single_trailing_semicolon(query_str)
        if _has_multiple_statements(clean_q):
            raise Exception("Multiple statements not supported")

        cursor.execute("CALL optimized_execute(%s)", (clean_q,))

        for result in cursor.stored_results():
            cols = list(result.column_names or [])
            if not cols: continue
            if _is_explain_result(cols):
                result.fetchall()
                continue
            if final_df is None:
                rows = result.fetchall()
                final_df = pd.DataFrame(rows, columns=cols)
        while cursor.nextset(): pass
        conn.commit()

        if final_df is None:
            q_upper = clean_q.lstrip().upper()
            if q_upper.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")):
                affected = cursor.rowcount if cursor.rowcount is not None and cursor.rowcount >= 0 else 0
                status_msg = f"Query executed successfully. {affected} rows affected."
            elif q_upper.startswith(("CREATE", "ALTER", "DROP", "TRUNCATE", "RENAME", "USE", "SET", "CALL")):
                status_msg = "Query executed successfully."
            elif not q_upper.startswith(("SELECT", "WITH", "SHOW", "DESCRIBE", "DESC")):
                status_msg = "Query executed successfully."
            elif q_upper.startswith("SELECT"):
                final_df = pd.DataFrame() # fail safe empty

        metrics_cursor = conn.cursor(dictionary=True)
        metrics_cursor.execute(
            "SELECT actual_execution_time as execution_time, plan_choice, estimated_cost, explanation "
            "FROM query_log ORDER BY created_at DESC, query_id DESC LIMIT 1"
        )
        try:
            run_metrics = metrics_cursor.fetchone()
            while metrics_cursor.nextset(): pass
        except: pass
        finally: metrics_cursor.close()
        
    except Exception as e:
        raise e
    finally:
        try:
            while cursor.nextset(): pass
        except: pass
        if cursor: cursor.close()
        if conn.is_connected(): conn.close()
    return final_df, run_metrics, status_msg

def display_results(metrics, is_custom=False):
    if metrics is not None:
        if is_custom: st.success("Query Intercepted and Executed by AutoDB")
        col1, col2, col3 = st.columns(3)
        with col1: st.metric("Plan Chosen", metrics.get('plan_choice', 'N/A'))
        with col2: st.metric("Execution Time", f"{metrics.get('execution_time', 0.0):.4f}s")
        with col3: st.metric("Estimated Cost", f"{metrics.get('estimated_cost', 0.0):.1f}")
        st.info(f"**AI Engine Explanation:** {metrics.get('explanation', 'None')}")

with tab1:
    st.header("AutoDB Terminal")

    st.subheader("Quick Benchmarks")
    st.caption("Push predefined queries to trace optimizer decisions live.")

    q1 = "SELECT product_id, SUM(revenue) AS total_revenue FROM order_fact GROUP BY product_id"
    if st.button("Total Revenue by Product"):
        try:
            data1, metrics1, status1 = run_query(q1)
            display_results(metrics1)
            if data1 is not None and len(data1.columns) > 0:
                st.dataframe(data1, use_container_width=True)
            elif status1:
                st.success(status1)
        except Exception as e: st.error(f"Database error: {e}")
        
    q2 = "SELECT product_id, revenue FROM order_fact WHERE product_id = 99"
    if st.button("Product Filter (Index Recommend Test)"):
        try:
            data2, metrics2, status2 = run_query(q2)
            display_results(metrics2)
            if data2 is not None and len(data2.columns) > 0:
                st.dataframe(data2, use_container_width=True)
            elif status2:
                st.success(status2)
        except Exception as e: st.error(f"Database error: {e}")
        
    st.markdown("---")
    st.subheader("Interactive Custom SQL Executer")
    custom_q = st.text_area("SQL Protocol Payload:", height=150)
    if st.button("Execute Frame Strategy"):
        if custom_q.strip():
            try:
                custom_data, custom_metrics, status_msg = run_query(custom_q)
                display_results(custom_metrics, is_custom=True)
                if custom_data is not None and len(custom_data.columns) > 0:
                    st.dataframe(custom_data, use_container_width=True)
                else:
                    st.success(status_msg if status_msg else "Query executed successfully. (0 rows returned)")
            except Exception as e:
                st.error(f"SQL Syntax Invalid or Database Error: {e}")
        else:
            st.warning("Please enter a query first.")


with tab2:
    st.header("Optimizer Analytics & Dashboards")
    st.caption("Visualizing performance scaling, View creation schemas, and AI CBO index suggestions.")

    col_info, col_btn = st.columns([0.8, 0.2])
    with col_info: st.info("Realtime trace monitor pulling directly from metadata engines.")
    
    try:
        full_query_log, workload, mv_meta, idx_cands = fetch_workload_kpis()
        improvement = parse_improvements(full_query_log)
        
        st.subheader("System Analytics KPIs")
        if not full_query_log.empty:
            total_queries = len(full_query_log)
            mv_hits = len(full_query_log[full_query_log['plan_choice'] == 'USE_MV'])
            hit_ratio = (mv_hits / total_queries) * 100
        else:
            total_queries = 0; hit_ratio = 0.0

        k1, k2, k3 = st.columns(3)
        with k1: st.metric("Total User + Training Queries", total_queries)
        with k2: st.metric("Materialization Hit Ratio", f"{hit_ratio:.1f}%")
        with k3: st.metric("Optimizer Speed Improvement %", f"{improvement:.1f}%")
        
        st.markdown("---")
        
        st.subheader("Plan Choice Distribution")
        if not full_query_log.empty:
            plan_counts = full_query_log.groupby("plan_choice", as_index=False).size().rename(columns={"size": "count"})
            plan_fig = px.bar(plan_counts, x="plan_choice", y="count", title="Plan Routing Volume")
            st.plotly_chart(plan_fig, use_container_width=True)
        else: st.info("No plan data available yet.")

        st.markdown("---")
        
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Materialized Views Engine")
            st.dataframe(mv_meta, use_container_width=True)
        with c2:
            st.subheader("Index Recommendation Generator")
            st.dataframe(idx_cands, use_container_width=True)
        
        st.markdown("---")
        st.subheader("Comprehensive Query AI Logs")
        if not full_query_log.empty:
            view_logs = full_query_log[['actual_execution_time', 'chosen_plan', 'estimated_cost', 'explanation']]
            st.dataframe(view_logs, use_container_width=True)
            
    except Exception as e:
        st.error(f"Failed pulling AI metrics. Please boot backend/workload_generator.py explicitly. Trace: {e}")
