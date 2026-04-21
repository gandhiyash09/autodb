DROP DATABASE IF EXISTS autodb_ecommerce;
CREATE DATABASE autodb_ecommerce;
USE autodb_ecommerce;

-- ==========================================
-- STEP 1: SCHEMAS
-- ==========================================
CREATE TABLE product_dim (
    product_id INT PRIMARY KEY,
    product_name VARCHAR(100),
    category VARCHAR(50),
    unit_price DECIMAL(10,2)
);

CREATE TABLE warehouse_dim (
    warehouse_id INT PRIMARY KEY,
    warehouse_name VARCHAR(100),
    region VARCHAR(50)
);

CREATE TABLE date_dim (
    date_id INT PRIMARY KEY,
    full_date DATE,
    year INT,
    month INT,
    day INT,
    quarter VARCHAR(5)
);

CREATE TABLE order_fact (
    order_id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT,
    warehouse_id INT,
    revenue DECIMAL(10,2),
    date_id INT,
    FOREIGN KEY (product_id) REFERENCES product_dim(product_id),
    FOREIGN KEY (warehouse_id) REFERENCES warehouse_dim(warehouse_id),
    FOREIGN KEY (date_id) REFERENCES date_dim(date_id)
);

-- ==========================================
-- STEP 2: METADATA TABLES
-- ==========================================
CREATE TABLE query_master (
    query_id INT AUTO_INCREMENT PRIMARY KEY,
    query_text TEXT,
    query_hash VARCHAR(64) UNIQUE
);

CREATE TABLE query_log (
    query_id INT,
    estimated_cost DOUBLE,
    actual_execution_time DOUBLE,
    normal_execution_time DOUBLE,
    chosen_plan VARCHAR(50),
    used_index BOOLEAN DEFAULT FALSE,
    used_mv BOOLEAN DEFAULT FALSE,
    query_type VARCHAR(50),
    explanation TEXT,
    explain_rows INT,
    explain_key VARCHAR(50),
    explain_type VARCHAR(50),
    error_msg TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_query FOREIGN KEY (query_id) REFERENCES query_master(query_id)
);

CREATE TABLE query_feedback (
    query_id INT,
    plan_choice VARCHAR(50),
    query_type VARCHAR(50),
    avg_execution_time DOUBLE,
    avg_cost DOUBLE,
    executions INT,
    PRIMARY KEY (query_id, plan_choice)
);

CREATE TABLE mv_metadata (
    mv_name VARCHAR(50) PRIMARY KEY,
    query_fingerprint VARCHAR(64),
    usage_count INT DEFAULT 0,
    is_stale BOOLEAN DEFAULT FALSE,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE workload_stats (
    fingerprint VARCHAR(64) PRIMARY KEY,
    execution_count INT DEFAULT 0,
    avg_time DOUBLE,
    avg_cost DOUBLE,
    last_plan VARCHAR(50)
);

CREATE TABLE column_stats (
    table_name VARCHAR(50),
    column_name VARCHAR(50),
    total_rows INT,
    distinct_values INT,
    min_value DOUBLE,
    max_value DOUBLE,
    PRIMARY KEY (table_name, column_name)
);

CREATE TABLE index_recommendations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    query_fingerprint VARCHAR(64),
    recommendation TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE plan_cost_model (
    plan_name VARCHAR(50) PRIMARY KEY,
    avg_execution_time DOUBLE DEFAULT 0.0,
    multiplier DOUBLE DEFAULT 1.0
);

INSERT INTO plan_cost_model (plan_name, multiplier) VALUES
('FULL_SCAN', 1.0),
('INDEX_SCAN', 0.2),
('USE_MV', 0.05),
('AGGREGATE_PUSHDOWN', 0.3);

-- ==========================================
-- TRIGGERS FOR STALENESS
-- ==========================================
DELIMITER $$
CREATE TRIGGER mark_mv_stale_insert
AFTER INSERT ON order_fact
FOR EACH ROW
BEGIN
    UPDATE mv_metadata SET is_stale = TRUE;
END$$

CREATE TRIGGER mark_mv_stale_update
AFTER UPDATE ON order_fact
FOR EACH ROW
BEGIN
    UPDATE mv_metadata SET is_stale = TRUE;
END$$

CREATE TRIGGER mark_mv_stale_delete
AFTER DELETE ON order_fact
FOR EACH ROW
BEGIN
    UPDATE mv_metadata SET is_stale = TRUE;
END$$
DELIMITER ;
