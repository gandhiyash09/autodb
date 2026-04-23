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
                if 'CREATE PROCEDURE' not in stmt and 'CREATE TRIGGER' not in stmt:
                    sub_stmts = stmt.split(';')
                    for sub in sub_stmts:
                        if sub.strip():
                            cursor.execute(sub.strip() + ';')
                else:
                    cursor.execute(stmt.strip())
            except Exception as e:
                pass

def setup_database():
    print("Connecting to database...")
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DROP DATABASE IF EXISTS autodb_ecommerce;")
    cursor.execute("CREATE DATABASE autodb_ecommerce;")
    cursor.execute("USE autodb_ecommerce;")

    import os
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    print("Building schema from sql/setup.sql...")
    execute_sql_file(cursor, os.path.join(base_dir, 'sql', 'setup.sql'))

    print("Building procedures from sql/procedures.sql...")
    with open(os.path.join(base_dir, 'sql', 'procedures.sql'), 'r') as f:
        procs_sql = f.read()
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

    templates = [
        "SELECT product_id, SUM(revenue) AS total_revenue FROM order_fact GROUP BY product_id",
        "SELECT product_id, revenue FROM order_fact WHERE product_id = {}",
        "SELECT p.product_name, SUM(f.revenue) FROM order_fact f JOIN product_dim p ON f.product_id = p.product_id GROUP BY p.product_name",
        "SELECT * FROM order_fact WHERE revenue > {}",
        "SELECT COUNT(*) FROM order_fact"
    ]

    for i in range(200):
        t = random.choices(templates, weights=[40, 20, 20, 10, 10])[0]

        if "{}" in t:
            if "product_id" in t:
                q = t.format(random.randint(1, 100))
            else:
                q = t.format(random.randint(10, 150))
        else:
            q = t

        try:
            dict_cursor = conn.cursor(dictionary=True)
            exp_rows = 0
            exp_key = 'NONE'
            exp_type = 'ALL'
            try:
                dict_cursor.execute(f"EXPLAIN {q}")
                exp_res = dict_cursor.fetchall()
                if exp_res:
                    exp_rows = exp_res[0].get('rows') or 1000
                    exp_key = str(exp_res[0].get('key') or 'NONE')
                    exp_type = str(exp_res[0].get('type') or 'ALL')
                while dict_cursor.nextset(): pass
            except: pass
            finally: dict_cursor.close()

            cursor.execute("CALL optimized_execute(%s, %s, %s, %s)", (q, int(exp_rows), exp_key, exp_type))
            while cursor.nextset(): pass

        except Exception as e:
            pass

    conn.commit()
    conn.commit()
    print("Workload training generation complete!")

if __name__ == "__main__":
    conn, cursor = setup_database()
    seed_data(conn, cursor)
    generate_workload(conn, cursor)
    cursor.close()
    conn.close()
    print("AutoDB Refactor Database Prepared Successfully.")
