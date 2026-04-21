import mysql.connector
import random
from datetime import datetime, timedelta

def generate_data():
    print("Connecting to database...")
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="", # Modify if your local setup requires a password
        database="autodb_ecommerce"
    )
    cursor = conn.cursor()

    print("Clearing old data...")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
    cursor.execute("TRUNCATE TABLE order_fact;")
    cursor.execute("TRUNCATE TABLE product_dim;")
    cursor.execute("TRUNCATE TABLE warehouse_dim;")
    cursor.execute("TRUNCATE TABLE date_dim;")
    
    cursor.execute("TRUNCATE TABLE product_revenue_mv;")
    cursor.execute("TRUNCATE TABLE product_warehouse_mv;")
    cursor.execute("TRUNCATE TABLE yearly_revenue_mv;")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")

    print("Inserting dimensions...")
    categories = ['Electronics', 'Clothing', 'Home', 'Toys', 'Sports']
    products = []
    for i in range(1, 101):
        price = round(random.uniform(10.0, 500.0), 2)
        products.append((i, f"Product {i}", random.choice(categories), price))
    cursor.executemany("INSERT INTO product_dim VALUES (%s, %s, %s, %s)", products)

    regions = ['North', 'South', 'East', 'West']
    warehouses = []
    for i in range(1, 11):
        warehouses.append((i, f"Warehouse {i}", random.choice(regions)))
    cursor.executemany("INSERT INTO warehouse_dim VALUES (%s, %s, %s)", warehouses)

    start_date = datetime(2023, 1, 1)
    dates = []
    for i in range(1, 731): # 2 years
        d = start_date + timedelta(days=i-1)
        quarter = f"Q{(d.month - 1) // 3 + 1}"
        dates.append((i, d.strftime('%Y-%m-%d'), d.year, d.month, d.day, quarter))
    cursor.executemany("INSERT INTO date_dim VALUES (%s, %s, %s, %s, %s, %s)", dates)
    conn.commit()

    print("Inserting 15,000+ facts...")
    orders = []
    for _ in range(15000):
        product_id = random.randint(1, 100)
        warehouse_id = random.randint(1, 10)
        revenue = round(random.uniform(5.0, 200.0), 2)
        date_id = random.randint(1, len(dates))
        orders.append((product_id, warehouse_id, revenue, date_id))

    chunk_size = 5000
    for i in range(0, len(orders), chunk_size):
        chunk = orders[i:i+chunk_size]
        cursor.executemany("INSERT INTO order_fact (product_id, warehouse_id, revenue, date_id) VALUES (%s, %s, %s, %s)", chunk)
        conn.commit()

    print("Generating stats...")
    cursor.execute("CALL collect_all_stats()")
    conn.commit()

    print("Successfully seeded 15,000+ orders into the autodb_ecommerce database!")
    cursor.close()
    conn.close()

if __name__ == "__main__":
    generate_data()
