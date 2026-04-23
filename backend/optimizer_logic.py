import mysql.connector
import pandas as pd

def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="gandhiyash09",
        database="autodb_ecommerce"
    )

def fetch_workload_kpis():
    conn = get_connection()
    try:
        full_query_log = pd.read_sql("SELECT * FROM query_log WHERE plan_choice != 'BASELINE' ORDER BY created_at ASC", conn)
        workload = pd.read_sql("SELECT * FROM workload_stats", conn)
        mv_meta = pd.read_sql("SELECT * FROM mv_metadata", conn)
        idx_cands = pd.read_sql("SELECT * FROM index_recommendations", conn)
        return full_query_log, workload, mv_meta, idx_cands
    finally:
        conn.close()

def parse_improvements(full_query_log):
    return 0.0
