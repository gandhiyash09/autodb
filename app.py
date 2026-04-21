import streamlit as st
import mysql.connector
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide", page_title="AutoDB E-Commerce")

def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="gandhiyash09",
        database="autodb_ecommerce"
    )

st.title("AutoDB: Adaptive E-Commerce Query Optimizer")

tab1, tab2 = st.tabs(["E-Commerce Analytics", "Optimizer Engine"])

def run_query(query_str):
    conn = get_connection()
    # Using dictionary=True makes it much easier to display in Streamlit
    cursor = conn.cursor(dictionary=True)
    final_data = []
    run_metrics = None
    
    try:
        # We replace single quotes in the query string to prevent SQL syntax crashes
        safe_query = query_str.replace("'", "''")
        cursor.execute(f"CALL optimized_execute('{safe_query}')")
        
        # Loop through ALL result sets
        for result in cursor.stored_results():
            try:
                rows = result.fetchall()
                if rows:
                    final_data = rows 
            except Exception:
                pass
                
        # Forcefully flush any hidden buffers
        while cursor.nextset():
            pass
                
        # CRITICAL: We must commit for logs
        conn.commit()

        # Fetch exact metrics for the live run profiling
        cursor.execute("SELECT execution_time, plan_choice, estimated_cost FROM query_log ORDER BY query_id DESC LIMIT 1")
        try:
            metrics_data = cursor.fetchall()
            if metrics_data:
                run_metrics = metrics_data[0]
            # Flush buffers from this fetch
            while cursor.nextset(): 
                pass
        except Exception:
            pass
        
    except Exception as e:
        # Re-raise so the frontend can catch and display the SQL error gracefully
        raise e
    finally:
        # Last safety flush loop
        try:
            while cursor.nextset():
                pass
        except Exception:
            pass
            
        if cursor:
            cursor.close()
        if conn.is_connected():
            conn.close()
            
    return final_data, run_metrics

def display_results(data, metrics, is_custom=False):
    if metrics:
        if is_custom:
            st.success("Query Intercepted and Executed by AutoDB")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Plan Chosen", metrics.get('plan_choice', 'N/A'))
        with col2:
            st.metric("Execution Time", f"{metrics.get('execution_time', 0.0):.4f}s")
        with col3:
            st.metric("Estimated Cost", f"{metrics.get('estimated_cost', 0.0):.1f}")
            
    if data:
        st.dataframe(data)

with tab1:
    st.header("Predefined Queries")
    st.info("Click a button below to run the corresponding query through the Adaptive Optimizer.")
    
    q1 = "SELECT product_id, SUM(revenue) AS total_revenue FROM order_fact GROUP BY product_id"
    if st.button("Total Revenue by Product"):
        try:
            data1, metrics1 = run_query(q1)
            display_results(data1, metrics1)
        except Exception as e:
            st.error(f"Database execution error: {e}")
        
    q2 = "SELECT p.product_name, w.warehouse_name, SUM(f.revenue) AS total_revenue, COUNT(*) AS order_count FROM order_fact f JOIN product_dim p ON f.product_id = p.product_id JOIN warehouse_dim w ON f.warehouse_id = w.warehouse_id GROUP BY p.product_name, w.warehouse_name"
    if st.button("Revenue by Product & Warehouse (JOIN)"):
        try:
            data2, metrics2 = run_query(q2)
            display_results(data2, metrics2)
        except Exception as e:
            st.error(f"Database execution error: {e}")
        
    q3 = "SELECT d.year, SUM(f.revenue) AS total_revenue, COUNT(*) AS total_orders FROM order_fact f JOIN date_dim d ON f.date_id = d.date_id GROUP BY d.year ORDER BY d.year"
    if st.button("Annual Revenue Trend by Year"):
        try:
            data3, metrics3 = run_query(q3)
            display_results(data3, metrics3)
        except Exception as e:
            st.error(f"Database execution error: {e}")

    st.markdown("---")
    st.subheader("Custom Query Execution Engine")
    custom_q = st.text_area("SQL Terminal: Route Raw Query via AutoDB", height=150)
    if st.button("Route Custom Query via AutoDB"):
        if custom_q.strip():
            try:
                custom_data, custom_metrics = run_query(custom_q)
                display_results(custom_data, custom_metrics, is_custom=True)
            except Exception as e:
                st.error(f"SQL Syntax Invalid or Database Error: {e}")
        else:
            st.warning("Please enter a query first.")

    st.info("**Why We Built This:** AutoDB intercepts your raw SQL, parses it for heavy operations "
            "(JOINs, GROUP BYs), calculates algorithmic cost, and checks workload history. If a query "
            "is repetitive and expensive, it dynamically reroutes execution to pre-computed "
            "Materialized Views—saving computational overhead.")


with tab2:
    st.header("Optimizer Metrics")
    
    col_info, col_btn = st.columns([0.8, 0.2])
    with col_info:
        st.info("This is the DBA View. It shows workload statistics and optimization decisions made by AutoDB.")
    with col_btn:
        if st.button("Reset AutoDB Memory", type="primary"):
            try:
                reset_conn = get_connection()
                reset_cursor = reset_conn.cursor()
                reset_cursor.execute("TRUNCATE query_log;")
                reset_cursor.execute("TRUNCATE query_feedback;")
                reset_cursor.execute("TRUNCATE workload_stats;")
                reset_cursor.execute("UPDATE mv_metadata SET usage_count = 0, is_stale = FALSE;")
                reset_conn.commit()
                st.success("Memory wiped successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Error resetting memory: {e}")
            finally:
                if 'reset_conn' in locals() and reset_conn.is_connected():
                    reset_cursor.close()
                    reset_conn.close()

    try:
        conn = get_connection()
        full_query_log = pd.read_sql("SELECT * FROM query_log ORDER BY created_at ASC", conn)
        workload = pd.read_sql("SELECT * FROM workload_stats", conn)
        mv_meta = pd.read_sql("SELECT * FROM mv_metadata", conn)
        idx_cands = pd.read_sql("SELECT * FROM index_candidates", conn)
        
        st.subheader("System Analytics KPIs")
        if not full_query_log.empty:
            total_queries = len(full_query_log)
            mv_hits = len(full_query_log[full_query_log['plan_choice'] == 'USE_MV'])
            hit_ratio = (mv_hits / total_queries) * 100
        else:
            total_queries = 0
            hit_ratio = 0.0

        kpi1, kpi2 = st.columns(2)
        with kpi1:
            st.metric("Total Queries Run", total_queries)
        with kpi2:
            st.metric("Materialization Hit Ratio", f"{hit_ratio:.1f}%")
        
        st.markdown("---")
        
        st.subheader("Optimizer Learning Curve")
        if not full_query_log.empty:
            full_query_log['Run Number'] = range(1, len(full_query_log) + 1)
            # Ensure query_id is treated purely as a category/string for distinct colors
            full_query_log['query_id'] = full_query_log['query_id'].astype(str)
            
            fig = px.line(full_query_log, 
                          x='Run Number', 
                          y='execution_time', 
                          color='query_id', 
                          symbol='plan_choice',
                          markers=True, 
                          title="Execution Time Evolution Across Queries")
            
            fig.update_layout(yaxis_title="Execution Time (s)", xaxis_title="Sequential Run Number")
            st.plotly_chart(fig, use_container_width=True)
            
            st.subheader("Query Path Trace")
            st.dataframe(full_query_log[['query_id', 'plan_choice', 'execution_time', 'used_index', 'used_mv']])
        else:
            st.info("No queries have been run yet!")

        st.markdown("---")
        st.subheader("Workload Stats")
        st.dataframe(workload)
                
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("MV Metadata")
            st.dataframe(mv_meta)
        with col2:
            st.subheader("Index Candidates")
            st.dataframe(idx_cands)
            
    except Exception as e:
        st.error(f"Could not load optimizer metrics. Please ensure the database is setup and running. Error: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            conn.close()
