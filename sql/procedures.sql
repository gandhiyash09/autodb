DELIMITER $$

-- ==========================================
-- BASIC STATS COLLECTORS
-- ==========================================
CREATE PROCEDURE collect_column_stats()
BEGIN
    INSERT INTO column_stats
    SELECT 'order_fact', 'product_id', COUNT(*), COUNT(DISTINCT product_id), MIN(product_id), MAX(product_id)
    FROM order_fact
    ON DUPLICATE KEY UPDATE total_rows = VALUES(total_rows), distinct_values = VALUES(distinct_values), min_value = VALUES(min_value), max_value = VALUES(max_value);
    
    INSERT INTO column_stats
    SELECT 'order_fact', 'revenue', COUNT(*), COUNT(DISTINCT revenue), MIN(revenue), MAX(revenue)
    FROM order_fact
    ON DUPLICATE KEY UPDATE total_rows = VALUES(total_rows), distinct_values = VALUES(distinct_values), min_value = VALUES(min_value), max_value = VALUES(max_value);
END$$

-- ==========================================
-- PROCEDURE: normal_execute
-- Description: Executes natively and logs normal execution time
-- ==========================================
CREATE PROCEDURE normal_execute(IN q TEXT)
BEGIN
    DECLARE v_qid INT;
    DECLARE start_t DOUBLE;
    DECLARE end_t DOUBLE;
    
    SET start_t = UNIX_TIMESTAMP(NOW(6));
    
    SET @sql = q;
    PREPARE stmt FROM @sql;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;
    
    SET end_t = UNIX_TIMESTAMP(NOW(6));
    
    -- Register into master if missing
    SET @qnorm = LOWER(TRIM(REPLACE(REPLACE(q, '\n', ' '), '\t', ' ')));
    SET @fingerprint = MD5(@qnorm);
    INSERT IGNORE INTO query_master(query_text, query_hash) VALUES (q, @fingerprint);
    SELECT query_id INTO v_qid FROM query_master WHERE query_hash = @fingerprint LIMIT 1;
    
    -- Insert baseline log (identifiable by plan 'BASELINE')
    INSERT INTO query_log (query_id, chosen_plan, normal_execution_time, actual_execution_time, query_type, explanation)
    VALUES (v_qid, 'BASELINE', end_t - start_t, end_t - start_t, 'N/A', 'Natively executed to establish baseline timing.');
END$$

-- ==========================================
-- MAIN OPTIMIZER ROUTING PROCEDURE
-- ==========================================
CREATE PROCEDURE optimized_execute(IN q TEXT)
BEGIN
    DECLARE v_qid INT;
    DECLARE v_mv_name VARCHAR(50) DEFAULT NULL;
    DECLARE v_is_aggregate BOOLEAN DEFAULT FALSE;
    DECLARE v_has_filter BOOLEAN DEFAULT FALSE;
    
    DECLARE v_total_rows INT DEFAULT 15000;
    DECLARE v_distinct INT DEFAULT 100;
    DECLARE v_selectivity DOUBLE DEFAULT 1.0;
    DECLARE v_mv_rows INT DEFAULT 0;
    
    DECLARE cost_full DOUBLE DEFAULT 0;
    DECLARE cost_index DOUBLE DEFAULT 0;
    DECLARE cost_mv DOUBLE DEFAULT 999999;
    DECLARE cost_agg DOUBLE DEFAULT 999999;
    DECLARE chosen_cost DOUBLE;
    DECLARE final_plan VARCHAR(50);
    
    DECLARE exec_count INT DEFAULT 0;
    DECLARE start_t DOUBLE;
    DECLARE end_t DOUBLE;
    DECLARE mv_count INT DEFAULT 0;
    DECLARE v_stale BOOLEAN DEFAULT FALSE;
    DECLARE qtype VARCHAR(50) DEFAULT 'SIMPLE';
    DECLARE v_explanation TEXT;

    -- Normalize and Fingerprint
    SET @qnorm = LOWER(TRIM(REPLACE(REPLACE(q, '\n', ' '), '\t', ' ')));
    SET @fingerprint = MD5(@qnorm);
    
    -- Update Workload Execution Counts
    INSERT INTO workload_stats (fingerprint, execution_count, avg_time, avg_cost, last_plan)
    VALUES (@fingerprint, 1, 0, 0, 'PENDING')
    ON DUPLICATE KEY UPDATE execution_count = execution_count + 1;
    SELECT execution_count INTO exec_count FROM workload_stats WHERE fingerprint = @fingerprint;

    -- Register text
    INSERT IGNORE INTO query_master(query_text, query_hash) VALUES (q, @fingerprint);
    SELECT query_id INTO v_qid FROM query_master WHERE query_hash = @fingerprint LIMIT 1;

    -- CLASSIFICATION
    IF @qnorm LIKE '%group by%' THEN 
        SET v_is_aggregate = TRUE; 
        SET qtype = 'AGGREGATE'; 
    END IF;
    IF @qnorm LIKE '%where%' THEN 
        SET v_has_filter = TRUE; 
        SET qtype = 'FILTER'; 
    END IF;
    IF @qnorm LIKE '%join%' THEN SET qtype = 'JOIN'; END IF;

    -- GRAB STATS
    SELECT total_rows, distinct_values INTO v_total_rows, v_distinct 
    FROM column_stats WHERE column_name = 'product_id' LIMIT 1;
    SET v_total_rows = IFNULL(v_total_rows, 15000);
    SET v_distinct = IFNULL(v_distinct, 100);

    -- SELECTIVITY LOGIC
    IF v_has_filter THEN
        IF @qnorm LIKE '%=%' THEN
            SET v_selectivity = 1.0 / v_distinct;
        ELSEIF @qnorm LIKE '%>%' OR @qnorm LIKE '%<%' OR @qnorm LIKE '%between%' THEN
            SET v_selectivity = 0.3;
        END IF;
    END IF;

    -- MV CREATION & LOOKUP
    IF v_is_aggregate AND exec_count >= 5 THEN
        SELECT mv_name, is_stale INTO v_mv_name, v_stale FROM mv_metadata WHERE query_fingerprint = @fingerprint LIMIT 1;
        
        IF v_mv_name IS NULL THEN
            SELECT COUNT(*) INTO mv_count FROM mv_metadata;
            IF mv_count < 5 THEN
                SET v_mv_name = CONCAT('mv_', SUBSTRING(@fingerprint, 1, 8));
                
                -- Spawn Dynamic View
                SET @create_mv_sql = CONCAT('CREATE TABLE ', v_mv_name, ' AS ', q);
                PREPARE stmt_mv FROM @create_mv_sql;
                EXECUTE stmt_mv;
                DEALLOCATE PREPARE stmt_mv;
                
                INSERT INTO mv_metadata (mv_name, query_fingerprint, usage_count, is_stale)
                VALUES (v_mv_name, @fingerprint, 0, FALSE);
                
                SET v_stale = FALSE;
            END IF;
        END IF;
    END IF;

    -- CBO COMPUTATIONS
    SET cost_full = v_total_rows * 1.0;
    SET cost_index = v_total_rows * v_selectivity * 0.2;
    
    IF v_is_aggregate THEN
        SET cost_agg = v_total_rows * 0.3;
    END IF;

    IF v_mv_name IS NOT NULL THEN
        -- Get MV Rows dynamically
        SET @stmt_cnt = CONCAT('SELECT COUNT(*) INTO @mvr FROM ', v_mv_name);
        PREPARE stmt_cnt FROM @stmt_cnt; 
        EXECUTE stmt_cnt; 
        DEALLOCATE PREPARE stmt_cnt;
        SET v_mv_rows = IFNULL(@mvr, 1);
        SET cost_mv = v_mv_rows * 0.05;
    END IF;

    -- COMPARE & ROUTE
    SET chosen_cost = cost_full;
    SET final_plan = 'FULL_SCAN';
    SET v_explanation = CONCAT('FULL_SCAN selected. Base Cost: ', cost_full);

    IF v_has_filter AND cost_index < chosen_cost THEN
        SET chosen_cost = cost_index;
        SET final_plan = 'INDEX_SCAN';
        SET v_explanation = CONCAT('INDEX_SCAN selected due to high selectivity filter. Cost: ', cost_index);
    END IF;

    IF v_is_aggregate AND cost_agg < chosen_cost THEN
        SET chosen_cost = cost_agg;
        SET final_plan = 'AGGREGATE_PUSHDOWN';
        SET v_explanation = CONCAT('AGGREGATE_PUSHDOWN selected for GROUP BY topology. Cost: ', cost_agg);
    END IF;

    IF v_mv_name IS NOT NULL AND cost_mv < chosen_cost THEN
        SET chosen_cost = cost_mv;
        SET final_plan = 'USE_MV';
        SET v_explanation = CONCAT('USE_MV selected! Repetitive aggregate pattern matched to materialized cache. Cost: ', cost_mv);
    END IF;

    -- Index Recommendation Engine (Background Task)
    IF exec_count > 10 AND chosen_cost > 3000 THEN
        IF v_has_filter THEN
            INSERT IGNORE INTO index_recommendations (query_fingerprint, recommendation)
            VALUES (@fingerprint, CONCAT('CREATE INDEX idx_auto_', SUBSTRING(@fingerprint,1,6), ' ON order_fact(product_id) -- (Driven by CBO high cost threshold)'));
        END IF;
    END IF;

    -- EXECUTE PLAN
    SET start_t = UNIX_TIMESTAMP(NOW(6));
    
    IF final_plan = 'USE_MV' THEN
        IF v_stale THEN
            -- Synchronous refresh of stale MV
            SET @trunc = CONCAT('TRUNCATE TABLE ', v_mv_name);
            PREPARE stmt_trunc FROM @trunc; EXECUTE stmt_trunc; DEALLOCATE PREPARE stmt_trunc;
            
            SET @ref = CONCAT('INSERT INTO ', v_mv_name, ' ', q);
            PREPARE stmt_ref FROM @ref; EXECUTE stmt_ref; DEALLOCATE PREPARE stmt_ref;
            
            UPDATE mv_metadata SET is_stale = FALSE WHERE mv_name = v_mv_name;
        END IF;
        
        UPDATE mv_metadata SET usage_count = usage_count + 1, last_updated = NOW() WHERE mv_name = v_mv_name;
        
        SET @sql = CONCAT('SELECT * FROM ', v_mv_name);
        PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
    ELSE
        SET @sql = q;
        PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
    END IF;
    
    SET end_t = UNIX_TIMESTAMP(NOW(6));

    -- LOGGING
    INSERT INTO query_log (query_id, estimated_cost, actual_execution_time, chosen_plan, used_index, used_mv, query_type, explanation)
    VALUES (
        v_qid, 
        chosen_cost, 
        end_t - start_t, 
        final_plan, 
        CASE WHEN final_plan = 'INDEX_SCAN' THEN TRUE ELSE FALSE END,
        CASE WHEN final_plan = 'USE_MV' THEN TRUE ELSE FALSE END,
        qtype,
        v_explanation
    );

    UPDATE workload_stats SET avg_time = (avg_time + (end_t - start_t))/2, avg_cost = (avg_cost + chosen_cost)/2, last_plan = final_plan WHERE fingerprint = @fingerprint;
END$$
DELIMITER ;
