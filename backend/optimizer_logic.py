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
        # We explicitly filter out the BASELINE logs to focus on optimizer paths
        full_query_log = pd.read_sql("SELECT * FROM query_log WHERE chosen_plan != 'BASELINE' ORDER BY created_at ASC", conn)
        workload = pd.read_sql("SELECT * FROM workload_stats", conn)
        mv_meta = pd.read_sql("SELECT * FROM mv_metadata", conn)
        idx_cands = pd.read_sql("SELECT * FROM index_recommendations", conn)
        return full_query_log, workload, mv_meta, idx_cands
    finally:
        conn.close()

def parse_improvements(full_query_log):
    if full_query_log.empty:
        return 0.0
    
    # Calculate performance improvement percentage specifically where an optimization triggered vs Baseline normal executed logic!
    optimized_traces = full_query_log[full_query_log['actual_execution_time'].notna() & full_query_log['normal_execution_time'].notna()]
    if optimized_traces.empty:
        return 0.0

    sum_baseline = optimized_traces['normal_execution_time'].sum()
    sum_optimized = optimized_traces['actual_execution_time'].sum()
    
    if sum_baseline == 0:
        return 0.0
        
    improvement_pct = ((sum_baseline - sum_optimized) / sum_baseline) * 100
    return improvement_pct
