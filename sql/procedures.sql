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
-- MAIN OPTIMIZER ROUTING PROCEDURE
-- ==========================================
CREATE PROCEDURE optimized_execute(IN q TEXT, IN exp_rows INT, IN exp_key VARCHAR(50), IN exp_type VARCHAR(50))
BEGIN
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
    
    DECLARE mult_full DOUBLE DEFAULT 1.0;
    DECLARE mult_idx DOUBLE DEFAULT 0.2;
    DECLARE mult_mv DOUBLE DEFAULT 0.05;
    DECLARE mult_agg DOUBLE DEFAULT 0.3;
    
    DECLARE exec_count INT DEFAULT 0;
    DECLARE start_t DOUBLE;
    DECLARE end_t DOUBLE;
    DECLARE run_time DOUBLE;
    DECLARE mv_count INT DEFAULT 0;
    DECLARE v_stale BOOLEAN DEFAULT FALSE;
    DECLARE qtype VARCHAR(50) DEFAULT 'SIMPLE';
    DECLARE v_explanation TEXT;
    
    DECLARE v_old_avg DOUBLE;
    DECLARE v_new_avg DOUBLE;
    DECLARE v_new_mult DOUBLE;
    DECLARE v_error_msg TEXT DEFAULT NULL;
    DECLARE baseline_start DATETIME(6);
    DECLARE baseline_time DOUBLE DEFAULT 0.0;
    DECLARE improvement_percent DOUBLE DEFAULT 0.0;
    
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1 v_error_msg = MESSAGE_TEXT;
        ROLLBACK;
        INSERT INTO query_log (
            query_text, plan_choice, cost, execution_time, explain_rows, explain_key, explain_type, error_msg
        ) VALUES (
            q, IFNULL(final_plan, 'FULL_SCAN'), chosen_cost, 0.0, exp_rows, exp_key, exp_type, v_error_msg
        );
        RESIGNAL;
    END;

    START TRANSACTION;

    -- STEP A: Measure Baseline Execution
    -- Baseline execution for timing only (result ignored)
    SET baseline_start = NOW(6);
    SET @bsql = q;
    PREPARE bstmt FROM @bsql; EXECUTE bstmt; DEALLOCATE PREPARE bstmt;
    SET baseline_time = TIMESTAMPDIFF(MICROSECOND, baseline_start, NOW(6)) / 1000000;

    -- Fallback EXPLAIN rules if Python pushes null equivalent
    IF exp_rows <= 0 THEN SET exp_rows = v_total_rows; END IF;

    -- Load multipliers
    SELECT multiplier INTO mult_full FROM plan_cost_model WHERE plan_name = 'FULL_SCAN' LIMIT 1;
    SELECT multiplier INTO mult_idx FROM plan_cost_model WHERE plan_name = 'INDEX_SCAN' LIMIT 1;
    SELECT multiplier INTO mult_mv FROM plan_cost_model WHERE plan_name = 'USE_MV' LIMIT 1;
    SELECT multiplier INTO mult_agg FROM plan_cost_model WHERE plan_name = 'AGGREGATE_PUSHDOWN' LIMIT 1;

    -- Query Pattern Normalization
    SET @qnorm = LOWER(TRIM(REPLACE(REPLACE(q, '\n', ' '), '\t', ' ')));
    SET @qnorm = REGEXP_REPLACE(@qnorm, '[0-9]+(\\.[0-9]+)?', '?');
    SET @qnorm = REGEXP_REPLACE(@qnorm, '\'.*?\'', '?');
    SET @qnorm = LEFT(@qnorm, 512);
    
    -- Workload stats
    INSERT INTO workload_stats (query_pattern, execution_count, avg_time, avg_cost, last_plan)
    VALUES (@qnorm, 1, 0, 0, 'PENDING')
    ON DUPLICATE KEY UPDATE execution_count = execution_count + 1;
    SELECT execution_count INTO exec_count FROM workload_stats WHERE query_pattern = @qnorm;

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

    -- MV CREATION CONDITION
    -- query repeats >= 5 times, is aggregate, total MV count < 5
    IF v_is_aggregate AND exec_count >= 5 THEN
        SELECT mv_name, is_stale INTO v_mv_name, v_stale FROM mv_metadata WHERE query_pattern = @qnorm LIMIT 1;
        
        IF v_mv_name IS NULL THEN
            SELECT COUNT(*) INTO mv_count FROM mv_metadata;
            IF mv_count < 5 THEN
                SET v_mv_name = CONCAT('mv_auto_', mv_count + 1);
                
                SET @create_mv_sql = CONCAT('CREATE TABLE ', v_mv_name, ' AS ', q);
                PREPARE stmt_mv FROM @create_mv_sql;
                EXECUTE stmt_mv;
                DEALLOCATE PREPARE stmt_mv;
                
                INSERT INTO mv_metadata (mv_name, query_pattern, usage_count, is_stale)
                VALUES (v_mv_name, @qnorm, 0, FALSE);
                
                SET v_stale = FALSE;
            END IF;
        END IF;
    END IF;

    -- AUTO INDEX CREATION CONDITION
    -- query repeats >= 5 times, is a filter on our star schema, and no index currently serves it
    IF v_has_filter AND exec_count >= 5 AND exp_key = 'NONE' THEN
        -- extract the column ONLY for exact equality filters (safest demo path)
        SET @col_name = NULL;
        
        -- allow optional spaces around '=' and tolerate multiple spaces after WHERE
        IF @qnorm LIKE '%where%product_id=%' OR @qnorm LIKE '%where%product_id =%' THEN
            SET @col_name = 'product_id';
        ELSEIF @qnorm LIKE '%where%warehouse_id=%' OR @qnorm LIKE '%where%warehouse_id =%' THEN
            SET @col_name = 'warehouse_id';
        ELSEIF @qnorm LIKE '%where%date_id=%' OR @qnorm LIKE '%where%date_id =%' THEN
            SET @col_name = 'date_id';
        END IF;

        IF @col_name IS NOT NULL THEN
            SELECT COUNT(*) INTO @existing_idx 
            FROM index_metadata 
            WHERE table_name = 'order_fact' AND column_name = @col_name;
            
            IF @existing_idx = 0 THEN
                SELECT COUNT(*) INTO @idx_count FROM index_metadata;
                IF @idx_count < 3 THEN
                    SET @idx_name = CONCAT('idx_', @col_name);
                    SET @create_idx_sql = CONCAT('CREATE INDEX ', @idx_name, ' ON order_fact(', @col_name, ')');
                    PREPARE stmt_idx FROM @create_idx_sql;
                    EXECUTE stmt_idx;
                    DEALLOCATE PREPARE stmt_idx;
                    
                    INSERT INTO index_metadata (index_name, table_name, column_name, usage_count)
                    VALUES (@idx_name, 'order_fact', @col_name, 0);
                END IF;
            END IF;
        END IF;
    END IF;

    -- CBO COMPUTATIONS
    SET cost_full = v_total_rows * mult_full;
    SET cost_index = v_total_rows * v_selectivity * mult_idx;
    
    IF v_is_aggregate THEN
        SET cost_agg = v_total_rows * mult_agg;
    END IF;

    IF v_mv_name IS NOT NULL THEN
        SET @stmt_cnt = CONCAT('SELECT COUNT(*) INTO @mvr FROM ', v_mv_name);
        PREPARE stmt_cnt FROM @stmt_cnt; 
        EXECUTE stmt_cnt; 
        DEALLOCATE PREPARE stmt_cnt;
        SET v_mv_rows = IFNULL(@mvr, 1);
        
        -- MV USAGE CONDITION
        IF v_mv_rows < (v_total_rows * 0.7) THEN
            SET cost_mv = v_mv_rows * mult_mv;
        ELSE
            SET cost_mv = 9999999;
        END IF;
    END IF;

    -- EXPLICIT COMPETITION LOOP
    SET final_plan = CASE
      WHEN cost_full <= cost_index AND cost_full <= cost_mv AND cost_full <= cost_agg THEN 'FULL_SCAN'
      WHEN cost_index <= cost_full AND cost_index <= cost_mv AND cost_index <= cost_agg THEN 'INDEX_SCAN'
      WHEN cost_mv <= cost_full AND cost_mv <= cost_index AND cost_mv <= cost_agg THEN 'USE_MV'
      ELSE 'AGGREGATE_PUSHDOWN'
    END;

    IF final_plan IS NULL OR final_plan = '' THEN
      SET final_plan = 'FULL_SCAN';
    END IF;

    IF final_plan = 'FULL_SCAN' THEN
        SET chosen_cost = cost_full;
    ELSEIF final_plan = 'INDEX_SCAN' THEN
        SET chosen_cost = cost_index;
    ELSEIF final_plan = 'USE_MV' THEN
        SET chosen_cost = cost_mv;
    ELSE
        SET chosen_cost = cost_agg;
    END IF;

    -- EXECUTE PLAN
    SET start_t = UNIX_TIMESTAMP(NOW(6));
    
    IF final_plan = 'USE_MV' THEN
        IF v_stale THEN
            -- Safe Temp Swap Strategy
            SET @tmp_tbl = CONCAT(v_mv_name, '_tmp');
            SET @create_tmp = CONCAT('CREATE TABLE ', @tmp_tbl, ' AS ', q);
            PREPARE stmt_tmp FROM @create_tmp; EXECUTE stmt_tmp; DEALLOCATE PREPARE stmt_tmp;
            
            SET @swap = CONCAT('RENAME TABLE ', v_mv_name, ' TO ', v_mv_name, '_old, ', @tmp_tbl, ' TO ', v_mv_name);
            PREPARE stmt_swap FROM @swap; EXECUTE stmt_swap; DEALLOCATE PREPARE stmt_swap;
            
            SET @drop_old = CONCAT('DROP TABLE IF EXISTS ', v_mv_name, '_old');
            PREPARE stmt_drop FROM @drop_old; EXECUTE stmt_drop; DEALLOCATE PREPARE stmt_drop;
            
            UPDATE mv_metadata SET is_stale = FALSE WHERE mv_name = v_mv_name;
        END IF;

        UPDATE mv_metadata SET usage_count = usage_count + 1, last_updated = NOW() WHERE mv_name = v_mv_name;
        
        SET @sql = CONCAT('SELECT * FROM ', v_mv_name);
        PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
    ELSE
        IF final_plan = 'INDEX_SCAN' AND exp_key != 'NONE' THEN
            UPDATE index_metadata SET usage_count = usage_count + 1 WHERE index_name = exp_key;
        END IF;

        SET @sql = q;
        PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
    END IF;
    
    SET end_t = UNIX_TIMESTAMP(NOW(6));
    SET run_time = end_t - start_t;

    -- ===========================================
    -- ADAPTIVE COST MODEL UPDATING (MANDATORY BOUNDS)
    -- ===========================================
    SELECT avg_execution_time INTO v_old_avg FROM plan_cost_model WHERE plan_name = final_plan LIMIT 1;
    SET v_new_avg = v_old_avg * 0.8 + run_time * 0.2;
    
    -- We assume the base multiplier drifts proportional to its timing shift
    IF NULLIF(v_old_avg, 0) IS NOT NULL THEN
        SET v_new_mult = (v_new_avg / v_old_avg) * (
            CASE 
                WHEN final_plan = 'FULL_SCAN' THEN mult_full
                WHEN final_plan = 'INDEX_SCAN' THEN mult_idx
                WHEN final_plan = 'USE_MV' THEN mult_mv
                ELSE mult_agg
            END
        );
    ELSE
        SET v_new_mult = CASE 
            WHEN final_plan = 'FULL_SCAN' THEN mult_full
            WHEN final_plan = 'INDEX_SCAN' THEN mult_idx
            WHEN final_plan = 'USE_MV' THEN mult_mv
            ELSE mult_agg
        END;
    END IF;

    -- CLAMP BOUNDARIES
    IF final_plan = 'FULL_SCAN' THEN
        SET v_new_mult = GREATEST(0.5, LEAST(2.0, v_new_mult));
    ELSEIF final_plan = 'INDEX_SCAN' THEN
        SET v_new_mult = GREATEST(0.05, LEAST(1.5, v_new_mult));
    ELSEIF final_plan = 'USE_MV' THEN
        SET v_new_mult = GREATEST(0.01, LEAST(0.5, v_new_mult));
    ELSEIF final_plan = 'AGGREGATE_PUSHDOWN' THEN
        SET v_new_mult = GREATEST(0.1, LEAST(1.2, v_new_mult));
    END IF;

    UPDATE plan_cost_model 
    SET avg_execution_time = v_new_avg, multiplier = v_new_mult 
    WHERE plan_name = final_plan;

    IF (SELECT COUNT(*) FROM query_log) % 100 = 0 THEN
        UPDATE plan_cost_model SET multiplier = multiplier * 0.9 + 1.0 * 0.1 WHERE plan_name = 'FULL_SCAN';
        UPDATE plan_cost_model SET multiplier = multiplier * 0.9 + 0.2 * 0.1 WHERE plan_name = 'INDEX_SCAN';
        UPDATE plan_cost_model SET multiplier = multiplier * 0.9 + 0.05 * 0.1 WHERE plan_name = 'USE_MV';
        UPDATE plan_cost_model SET multiplier = multiplier * 0.9 + 0.3 * 0.1 WHERE plan_name = 'AGGREGATE_PUSHDOWN';
    END IF;

    -- Formulate safe explanation logically
    IF final_plan = 'FULL_SCAN' THEN
        SET v_explanation = 'FULL_SCAN chosen due to no usable index';
    ELSEIF final_plan = 'INDEX_SCAN' THEN
        SET v_explanation = 'INDEX_SCAN chosen due to high selectivity';
    ELSEIF final_plan = 'USE_MV' THEN
        SET v_explanation = 'USE_MV chosen due to cached aggregation';
    ELSE
        SET v_explanation = 'AGGREGATE_PUSHDOWN chosen for grouped execution efficiency';
    END IF;

    -- LOGGING
    IF baseline_time > 0 THEN
        SET improvement_percent = ((baseline_time - run_time) / baseline_time) * 100;
    ELSE
        SET improvement_percent = 0;
    END IF;

    INSERT INTO query_log (
        query_text, plan_choice, execution_time, cost, explain_rows, explain_key, explain_type, error_msg, baseline_time, improvement_percent
    )
    VALUES (
        q, 
        IFNULL(final_plan, 'FULL_SCAN'), 
        run_time, 
        chosen_cost, 
        exp_rows,
        exp_key,
        exp_type,
        v_explanation,
        baseline_time,
        improvement_percent
    );

    UPDATE workload_stats SET avg_time = (avg_time + run_time)/2, avg_cost = (avg_cost + chosen_cost)/2, last_plan = final_plan WHERE query_pattern = @qnorm;
    
    COMMIT;
END$$
DELIMITER ;
