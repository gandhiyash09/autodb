import streamlit as st
import mysql.connector
import pandas as pd
import plotly.express as px

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
        password=db_password,
        database=db_name
    )

st.title("AutoDB: Adaptive E-Commerce Query Optimizer")

tab1, tab2 = st.tabs(["E-Commerce Analytics", "Optimizer Engine"])

def run_query(query_str):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("CALL optimized_execute(%s)", (query_str,))
        
        for result in cursor.stored_results():
            cols = [i[0] for i in result.description]
            data = result.fetchall()
            df = pd.DataFrame(data, columns=cols)
            if len(cols) == 1 and cols[0] == "plan_used":
                continue 
            st.dataframe(df)

        query_log = pd.read_sql("SELECT * FROM query_log ORDER BY created_at DESC LIMIT 1", conn)
        st.write("### Query Log (Optimizer Output)")
        st.dataframe(query_log)
        
    except Exception as e:
        st.error(f"Error executing query: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

with tab1:
    st.header("Predefined Queries")
    st.info("Click a button below to run the corresponding query through the Adaptive Optimizer.")
    
    q1 = "SELECT product_id, SUM(revenue) AS total_revenue FROM order_fact GROUP BY product_id"
    if st.button("Total Revenue by Product"):
        run_query(q1)
        
    q2 = "SELECT p.product_name, w.warehouse_name, SUM(f.revenue) AS total_revenue, COUNT(*) AS order_count FROM order_fact f JOIN product_dim p ON f.product_id = p.product_id JOIN warehouse_dim w ON f.warehouse_id = w.warehouse_id GROUP BY p.product_name, w.warehouse_name"
    if st.button("Revenue by Product & Warehouse (JOIN)"):
        run_query(q2)
        
    q3 = "SELECT d.year, SUM(f.revenue) AS total_revenue, COUNT(*) AS total_orders FROM order_fact f JOIN date_dim d ON f.date_id = d.date_id GROUP BY d.year ORDER BY d.year"
    if st.button("Annual Revenue Trend by Year"):
        run_query(q3)

with tab2:
    st.header("Optimizer Metrics")
    st.info("This is the DBA View. It shows workload statistics and optimization decisions made by AutoDB.")
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
