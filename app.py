import streamlit as st
import mysql.connector
import pandas as pd
import plotly.express as px
import warnings
warnings.filterwarnings('ignore', category=UserWarning)

st.set_page_config(layout="wide", page_title="AutoDB E-Commerce")

st.sidebar.title("Configuration")
db_host = st.sidebar.text_input("Host", "localhost")
db_user = st.sidebar.text_input("User", "root")
db_password = st.sidebar.text_input("Password", "", type="password")
db_name = st.sidebar.text_input("Database", "autodb_ecommerce")

def get_connection():
    return mysql.connector.connect(
        host=db_host,
        user=db_user,
        password="gandhiyash09",
        database=db_name
    )

st.title("AutoDB: Adaptive E-Commerce Query Optimizer")

tab1, tab2 = st.tabs(["E-Commerce Analytics", "Optimizer Engine"])

def run_query(query_str):
    conn = get_connection()
    # Using dictionary=True makes it much easier to display in Streamlit
    cursor = conn.cursor(dictionary=True)
    final_data = []
    
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
        
    except Exception as e:
        st.error(f"Database execution error: {e}")
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
            
    return final_data

with tab1:
    st.header("Predefined Queries")
    st.info("Click a button below to run the corresponding query through the Adaptive Optimizer.")
    
    q1 = "SELECT product_id, SUM(revenue) AS total_revenue FROM order_fact GROUP BY product_id"
    if st.button("Total Revenue by Product"):
        data1 = run_query(q1)
        st.dataframe(data1)  # <--- THIS SHOWS THE DATA
        
    q2 = "SELECT p.product_name, w.warehouse_name, SUM(f.revenue) AS total_revenue, COUNT(*) AS order_count FROM order_fact f JOIN product_dim p ON f.product_id = p.product_id JOIN warehouse_dim w ON f.warehouse_id = w.warehouse_id GROUP BY p.product_name, w.warehouse_name"
    if st.button("Revenue by Product & Warehouse (JOIN)"):
        data2 = run_query(q2)
        st.dataframe(data2)  # <--- THIS SHOWS THE DATA
        
    q3 = "SELECT d.year, SUM(f.revenue) AS total_revenue, COUNT(*) AS total_orders FROM order_fact f JOIN date_dim d ON f.date_id = d.date_id GROUP BY d.year ORDER BY d.year"
    if st.button("Annual Revenue Trend by Year"):
        data3 = run_query(q3)
        st.dataframe(data3)  # <--- THIS SHOWS THE DATA

    st.markdown("---")
    custom_q = st.text_area("Custom Query Execution Engine")
    if st.button("Route Custom Query via AutoDB"):
        if custom_q.strip():
            custom_data = run_query(custom_q)
            if custom_data:
                st.dataframe(custom_data)
        else:
            st.warning("Please enter a query first.")

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
            except Exception as e:
                st.error(f"Error resetting memory: {e}")
            finally:
                if 'reset_conn' in locals() and reset_conn.is_connected():
                    reset_cursor.close()
                    reset_conn.close()
    try:
        conn = get_connection()
        workload = pd.read_sql("SELECT * FROM workload_stats", conn)
        mv_meta = pd.read_sql("SELECT * FROM mv_metadata", conn)
        idx_cands = pd.read_sql("SELECT * FROM index_candidates", conn)
        plan_evolve = pd.read_sql("SELECT * FROM plan_evolution_short", conn)

        st.subheader("Workload Stats")
        st.dataframe(workload)
        
        st.subheader("Plan Evolution")
        if not plan_evolve.empty:
            st.dataframe(plan_evolve)
            try:
                fig = px.bar(plan_evolve, x="plan_choice", y="executions", title="Executions by Plan Choice", color="plan_choice")
                st.plotly_chart(fig)
            except Exception:
                pass
                
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
