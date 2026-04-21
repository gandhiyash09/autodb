import mysql.connector
import random
from datetime import datetime, timedelta

def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="gandhiyash09"
    )

def execute_sql_file(cursor, filepath):
    with open(filepath, 'r') as f:
        sql_script = f.read()
    
    statements = sql_script.split('$$')
    for stmt in statements:
        if stmt.strip() and not stmt.strip().startswith('DELIMITER'):
            try:
                # Handle standard semicolon splits inside non-delimiter blocks if needed
                if 'CREATE PROCEDURE' not in stmt and 'CREATE TRIGGER' not in stmt:
                    sub_stmts = stmt.split(';')
                    for sub in sub_stmts:
                        if sub.strip():
                            cursor.execute(sub.strip() + ';')
                else:
                    cursor.execute(stmt.strip())
            except Exception as e:
                pass # print(f"Error executing statement: {e}")

def setup_database():
    print("Connecting to database...")
    conn = get_connection()
    cursor = conn.cursor()
    
    # Switch to generic execution to load raw scripts
    cursor.execute("DROP DATABASE IF EXISTS autodb_ecommerce;")
    cursor.execute("CREATE DATABASE autodb_ecommerce;")
    cursor.execute("USE autodb_ecommerce;")
    
    print("Building schema from sql/setup.sql...")
    with open('sql/setup.sql', 'r') as f:
        setup_sql = f.read()
        for result in cursor.execute(setup_sql, multi=True):
            pass
            
    print("Building procedures from sql/procedures.sql...")
    with open('sql/procedures.sql', 'r') as f:
        procs_sql = f.read()
        # manually executing procedures since multi=True is weird with DELIMITER
        stmts = procs_sql.replace('DELIMITER $$', '').replace('DELIMITER ;', '').split('$$')
        for s in stmts:
            if s.strip():
                cursor.execute(s.strip())
                
    conn.commit()
    return conn, cursor

def seed_data(conn, cursor):
    print("Inserting dimensions...")
    categories = ['Electronics', 'Clothing', 'Home', 'Toys', 'Sports']
    products = [(i, f"Product {i}", random.choice(categories), round(random.uniform(10.0, 500.0), 2)) for i in range(1, 101)]
    cursor.executemany("INSERT INTO product_dim VALUES (%s, %s, %s, %s)", products)

    regions = ['North', 'South', 'East', 'West']
    warehouses = [(i, f"Warehouse {i}", random.choice(regions)) for i in range(1, 11)]
    cursor.executemany("INSERT INTO warehouse_dim VALUES (%s, %s, %s)", warehouses)

    start_date = datetime(2023, 1, 1)
    dates = []
    for i in range(1, 731):
        d = start_date + timedelta(days=i-1)
        dates.append((i, d.strftime('%Y-%m-%d'), d.year, d.month, d.day, f"Q{(d.month - 1) // 3 + 1}"))
    cursor.executemany("INSERT INTO date_dim VALUES (%s, %s, %s, %s, %s, %s)", dates)
    conn.commit()

    print("Inserting 15,000+ facts...")
    orders = []
    for _ in range(15000):
        orders.append((random.randint(1, 100), random.randint(1, 10), round(random.uniform(5.0, 200.0), 2), random.randint(1, len(dates))))

    for i in range(0, len(orders), 5000):
        cursor.executemany("INSERT INTO order_fact (product_id, warehouse_id, revenue, date_id) VALUES (%s, %s, %s, %s)", orders[i:i+5000])
        conn.commit()

    print("Generating base stats...")
    cursor.execute("CALL collect_column_stats()")
    conn.commit()

def generate_workload(conn, cursor):
    print("Generating training workload (200 Queries)...")
    
    # Base query templates driving specific paths
    templates = [
        "SELECT product_id, SUM(revenue) AS total_revenue FROM order_fact GROUP BY product_id", # Aggregate -> triggers USE_MV
        "SELECT product_id, revenue FROM order_fact WHERE product_id = {}", # Filter -> triggers INDEX_SCAN recommendations
        "SELECT p.product_name, SUM(f.revenue) FROM order_fact f JOIN product_dim p ON f.product_id = p.product_id GROUP BY p.product_name", # Heavy aggregation
        "SELECT * FROM order_fact WHERE revenue > {}", # FULL_SCAN bypass (range filter selectivity heuristic)
        "SELECT COUNT(*) FROM order_fact" # Trivial aggregate
    ]
    
    for i in range(200):
        # Weight the Aggregate queries heavier to force Dynamic MV creation naturally!
        t = random.choices(templates, weights=[40, 20, 20, 10, 10])[0]
        
        if "{}" in t:
            if "product_id" in t:
                q = t.format(random.randint(1, 100))
            else:
                q = t.format(random.randint(10, 150))
        else:
            q = t
            
        try:
            # First fetch the baseline time
            cursor.execute("CALL normal_execute(%s)", (q,))
            while cursor.nextset(): pass
            
            # Then run optimizer execution
            cursor.execute("CALL optimized_execute(%s)", (q,))
            while cursor.nextset(): pass
            
        except Exception as e:
            pass # print(f"Workload err: {e}")
            
    conn.commit()
    
    # Auto-link baseline normal times to the optimized rows for the dashboard!
    cursor.execute("""
        UPDATE query_log q_opt 
        JOIN query_log q_base ON q_opt.query_id = q_base.query_id AND q_base.chosen_plan = 'BASELINE'
        SET q_opt.normal_execution_time = q_base.actual_execution_time
        WHERE q_opt.chosen_plan != 'BASELINE'
    """)
    conn.commit()
    print("Workload training generation complete!")

if __name__ == "__main__":
    conn, cursor = setup_database()
    seed_data(conn, cursor)
    generate_workload(conn, cursor)
    cursor.close()
    conn.close()
    print("AutoDB Refactor Database Prepared Successfully.")
