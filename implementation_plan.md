# AutoDB: Adaptive, Self-Optimizing E-Commerce Data Warehouse
## Execution Plan — Cricket → E-Commerce Domain Translation

This plan translates the optimizer system documented in `DBMS_COURSE_PROJECT_SQL_COMMANDS.md` (Cricket domain) into an E-Commerce data warehouse with zero behavioral changes — only schema, table names, column names, and query patterns change.

---

## Strict Non-Negotiables

> [!IMPORTANT]
> **No New Logic Rule:** Every stored procedure, trigger, view, and cost model is a direct translation of the original Cricket logic. The behavioral flow — query logging → cost estimation → workload stats → MV routing → feedback-based plan selection — is preserved exactly. No new optimization strategies are introduced.

> [!IMPORTANT]
> **Metadata Table Names Are Frozen:** The following tables **retain their exact names and roles** from the original system:
> - `query_master` — deduplication registry using MD5 fingerprint
> - `query_log` — per-execution log (cost, plan, timing, index/MV flags)
> - `query_feedback` — adaptive learning table (rolling averages per plan per query)
> - `mv_metadata` — staleness + usage tracking for materialized views
> - `workload_stats` — fingerprint-keyed rolling workload aggregator

---

## Step 1 — Schema Translation

### Cricket → E-Commerce Mapping

| Cricket Table | E-Commerce Table | Role |
|---|---|---|
| `match_fact` | `order_fact` | Central fact table |
| `player_dim` | `product_dim` | Dimension: product catalog |
| `team_dim` | `warehouse_dim` | Dimension: fulfillment location |
| `time_dim` / `date_dim` | `date_dim` | Dimension: calendar |
| `player_stats_mv` | `product_revenue_mv` | MV: total revenue per product |
| `player_team_mv` | `product_warehouse_mv` | MV: revenue by product+warehouse |
| `yearly_stats_mv` | `yearly_revenue_mv` | MV: revenue by year |

### Column Mapping

**`order_fact`** (replaces `match_fact`):
| Cricket Column | E-Commerce Column | Type |
|---|---|---|
| `match_id` | `order_id` | INT PK AUTO_INCREMENT |
| `player_id` | `product_id` | INT (FK → product_dim) |
| `team_id` | `warehouse_id` | INT (FK → warehouse_dim) |
| `runs` | `revenue` | DECIMAL(10,2) |
| `date_id` | `date_id` | INT (FK → date_dim) |

**`product_dim`** (replaces `player_dim`):
- `product_id` INT PK, `product_name` VARCHAR(100), `category` VARCHAR(50), `unit_price` DECIMAL(10,2)

**`warehouse_dim`** (replaces `team_dim`):
- `warehouse_id` INT PK, `warehouse_name` VARCHAR(100), `region` VARCHAR(50)

**`date_dim`** (retained structure, `match_season` → `quarter`):
- `date_id` INT PK, `full_date` DATE, `year` INT, `month` INT, `day` INT, `quarter` VARCHAR(5)

---

## Step 2 — Metadata Tables (Exact Names, Exact Roles)

These tables are **copied verbatim** from the original with no structural changes:

| Table | Structure | Role |
|---|---|---|
| `query_master` | `query_id`, `query_text`, `query_hash` (MD5 UNIQUE) | Deduplication registry |
| `query_log` | `query_id` (FK), `execution_time`, `estimated_cost`, `plan_choice`, `used_index`, `used_mv`, `index_benefit` | Per-run audit log |
| `query_feedback` | `query_id`, `plan_choice`, `query_type`, `avg_execution_time`, `avg_cost`, `executions` (PK: query_id+plan_choice) | Adaptive learning |
| `mv_metadata` | `mv_name` (PK), `last_updated`, `usage_count`, `is_stale` | MV health tracker |
| `workload_stats` | `fingerprint` (PK), `execution_count`, `avg_time`, `avg_cost`, `last_plan` | Rolling workload stats |
| `column_stats` | `table_name`, `column_name`, `total_rows`, `distinct_values`, `min_value`, `max_value` | Selectivity data |
| `correlation_stats` | `table_name`, `column1`, `column2`, `correlation` | Column correlation |
| `mv_registry` | `mv_name`, `base_query`, `pattern` | MV pattern registry |

---

## Step 3 — Stored Procedure Translation

Each procedure is a direct translation: Cricket-domain column/table names → E-Commerce names. Logic is identical.

### `get_query_cost(IN q TEXT, OUT cost DOUBLE)`
**Translation:** All cost rules preserved. Column references change:
- `'%WHERE player_id%'` → `'%WHERE product_id%'`
- `'%JOIN%'` cost: +200 (unchanged)
- `'%GROUP BY%'` cost: +120 (unchanged)
- `'%ORDER BY%'` cost: +80 (unchanged)
- Selectivity lookup: `column_name = 'product_id'` (was `player_id`)

### `collect_column_stats()`
**Translation:** Collects stats for `order_fact` columns:
- `product_id`, `revenue`, `order_id`, `warehouse_id`, `date_id`
- (replaces: `player_id`, `runs`, `match_id`, `team_id`, `time_id`)

### `collect_all_stats()`
**Translation:** Calls `collect_column_stats()`, then computes Pearson correlation between `product_id` and `revenue` from `order_fact` (was: `player_id` and `runs` from `match_fact`).

### `optimized_execute(IN q TEXT)` — The Core Router

This is the final version of the procedure (the one with all 13 steps). **Translation plan:**

| Step | Action | Cricket Reference | E-Commerce Translation |
|---|---|---|---|
| 1 | Normalize query | `LOWER(TRIM(...))` | Identical |
| 2 | Fingerprint | Pattern keys: `G1`, `F1`, `J1`, `S1` | Pattern keys change to match E-Commerce column names |
| 3 | Register query | `query_master` INSERT | Identical table, identical logic |
| 4 | Classify | AGGREGATE / JOIN / FILTER / SIMPLE | Identical logic |
| 5 | Cost model | `get_query_cost()` call | New procedure, same call |
| 6 | Index score | `FILTER*0.4`, `JOIN*0.7` | Identical multipliers |
| 7 | Load workload stats | FROM `query_feedback` | Identical table name |
| 8 | MV eligibility | `'%group by player_id%' AND '%sum(runs)%'` | `'%group by product_id%' AND '%sum(revenue)%'` |
| 9 | MV score model | `(0.3*avg_cost) + (0.7*exec_count)` | Identical formula |
| 10 | Decision engine | Compare `mv_score`, `idx_score`, `base_cost` | Identical comparison logic |
| 11 | Execution timer | `UNIX_TIMESTAMP(NOW(6))` | Identical |
| 12 | Execute plan | `USE_MV` / `INDEX_SCAN` / `FULL_SCAN` | MV table name: `product_revenue_mv` |
| 13 | Logging | INSERT into `query_log` | Identical columns |
| 14 | Workload learning | `workload_stats` UPSERT | Identical schema |
| 15 | Feedback learning | `query_feedback` UPSERT | Identical schema |

**Fingerprint pattern translation:**
| Cricket Pattern | E-Commerce Pattern | Code |
|---|---|---|
| `group by player_id` (no team) | `group by product_id` (no warehouse) | `G1` |
| `group by player_id, team_id` | `group by product_id, warehouse_id` | `G2` |
| `where player_id` | `where product_id` | `F1` |
| `join` | `join` | `J1` |
| other | other | `S1` |

---

## Step 4 — Materialized Views & Triggers

### Three Materialized Views (Tables)

| MV Name | Replaces | Definition |
|---|---|---|
| `product_revenue_mv` | `player_stats_mv` | `SELECT product_id, SUM(revenue) AS total_revenue FROM order_fact GROUP BY product_id` |
| `product_warehouse_mv` | `player_team_mv` | `SELECT product_id, warehouse_id, SUM(revenue) AS total_revenue, COUNT(*) AS orders FROM order_fact GROUP BY product_id, warehouse_id` |
| `yearly_revenue_mv` | `yearly_stats_mv` | `SELECT d.year, SUM(f.revenue) AS total_revenue FROM order_fact f JOIN date_dim d ON f.date_id = d.date_id GROUP BY d.year` |

### Three Triggers (AFTER INSERT ON `order_fact`)

| Trigger | Replaces | Action |
|---|---|---|
| `update_product_mv` | `update_player_mv` | UPSERT into `product_revenue_mv` on `product_id` |
| `update_product_warehouse_mv` | `update_player_team_mv` | UPSERT into `product_warehouse_mv` on `(product_id, warehouse_id)` |
| `update_yearly_mv` | `update_yearly_mv` | Lookup `date_dim.year` then UPSERT into `yearly_revenue_mv` |

### `mv_registry` Entries
```
('product_revenue_mv',   'GROUP BY product_id',            'AGGREGATE_PRODUCT')
('product_warehouse_mv', 'GROUP BY product_id, warehouse_id', 'AGGREGATE_PRODUCT_WAREHOUSE')
('yearly_revenue_mv',    'GROUP BY year',                   'AGGREGATE_YEAR')
```

### `mv_metadata` Seed Rows
```
('product_revenue_mv',   NOW(), 0, FALSE)
('product_warehouse_mv', NOW(), 0, FALSE)
('yearly_revenue_mv',    NOW(), 0, FALSE)
```

---

## Step 5 — Views (Exact Translations)

| View | Replaces | Key Column Changes |
|---|---|---|
| `frequent_queries` | `frequent_queries` | No changes (uses `query_log`) |
| `slow_queries` | `slow_queries` | No changes |
| `heavy_queries` | `heavy_queries` | No changes |
| `query_performance` | `query_performance` | No changes |
| `workload_summary` | `workload_summary` | No changes |
| `optimizer_view` | `optimizer_view` | No changes |
| `selectivity_stats` | `selectivity_stats` | No changes |
| `query_classification` | `query_classification` | No changes |
| `index_candidates` | `index_candidates` | References `order_fact`, `product_id`, `warehouse_id` instead of `match_fact`, `player_id`, `team_id` |
| `index_recommendation_clean` | `index_recommendation_clean` | `product_id` instead of `player_id` |
| `mv_candidates` | `mv_candidates` | `'%SUM(revenue)%'` instead of `'%SUM(runs)%'` |
| `learning_progress_short` | `learning_progress_short` | No changes |
| `plan_evolution_short` | `plan_evolution_short` | No changes |
| `learned_best_plan` | `learned_best_plan` | No changes |

---

## Step 6 — The 3 Predefined Streamlit Queries

> [!IMPORTANT]
> The Streamlit UI is restricted to **exactly 3 predefined queries**. Each query is passed verbatim as a string to `CALL optimized_execute(...)` in Python. The UI does NOT allow free-form SQL input.

### Query 1 — Total Revenue by Product
**Label:** "Total Revenue by Product"
**Purpose:** Triggers `USE_MV` plan (routes through `product_revenue_mv`)
```sql
SELECT product_id, SUM(revenue) AS total_revenue
FROM order_fact
GROUP BY product_id
```

### Query 2 — Orders by Warehouse with Product Details (JOIN)
**Label:** "Revenue by Product & Warehouse (JOIN)"
**Purpose:** Triggers `HASH_JOIN_SIM` or `INDEX_SCAN` plan
```sql
SELECT p.product_name, w.warehouse_name, SUM(f.revenue) AS total_revenue, COUNT(*) AS order_count
FROM order_fact f
JOIN product_dim p ON f.product_id = p.product_id
JOIN warehouse_dim w ON f.warehouse_id = w.warehouse_id
GROUP BY p.product_name, w.warehouse_name
```

### Query 3 — Annual Revenue Trend
**Label:** "Annual Revenue Trend by Year"
**Purpose:** Triggers `AGGREGATE_PUSHDOWN` or `FULL_SCAN` plan
```sql
SELECT d.year, SUM(f.revenue) AS total_revenue, COUNT(*) AS total_orders
FROM order_fact f
JOIN date_dim d ON f.date_id = d.date_id
GROUP BY d.year
ORDER BY d.year
```

> [!NOTE]
> Query 1 will naturally route to `USE_MV` after 2+ executions (workload learning threshold from original code: `exec_count >= 2`). This demonstrates the adaptive behavior in the demo.

---

## Step 7 — File Tree

```
new project/
├── database_setup.sql       # All DDL: schema tables, metadata tables, MVs, triggers,
│                            # stored procedures, views — in correct dependency order
├── seed_data.py             # Python script: populates product_dim, warehouse_dim,
│                            # date_dim, order_fact (100-500 rows via faker/random)
│                            # Also calls CALL collect_all_stats()
├── app.py                   # Streamlit dashboard (3-query UI + optimizer metrics panels)
└── requirements.txt         # mysql-connector-python, streamlit, pandas, plotly
```

### `database_setup.sql` — Internal Order
1. `DROP DATABASE IF EXISTS autodb_ecommerce; CREATE DATABASE autodb_ecommerce;`
2. Dimension tables: `product_dim`, `warehouse_dim`, `date_dim`
3. Fact table: `order_fact`
4. Metadata/optimizer tables: `query_master`, `query_log`, `query_feedback`, `mv_metadata`, `workload_stats`, `column_stats`, `correlation_stats`, `mv_registry`
5. Materialized view tables: `product_revenue_mv`, `product_warehouse_mv`, `yearly_revenue_mv`
6. ALTER statements: primary keys on MVs, FK constraint on `query_log`
7. Triggers: `update_product_mv`, `update_product_warehouse_mv`, `update_yearly_mv`
8. Stored procedures: `get_query_cost`, `collect_column_stats`, `collect_all_stats`, `optimized_execute`
9. Views: all 14 views listed in Step 5
10. Seed metadata: `mv_metadata` rows, `mv_registry` rows

### `app.py` — Streamlit UI Scope
- **Sidebar:** MySQL connection config (host, user, password, db name)
- **Main heading:** "AutoDB: Adaptive E-Commerce Query Optimizer"
- **3 buttons**, one per query (no free-form SQL)
- **On button click:**
  1. Run `CALL optimized_execute('...')` via `mysql.connector`
  2. Display query result as a `st.dataframe`
  3. Display latest `query_log` row: plan chosen, cost, execution time, used_mv, used_index
- **Below buttons — Optimizer Metrics panel:**
  - `workload_stats` table
  - `plan_evolution_short` view
  - `mv_metadata` table (usage counts + staleness)
  - `index_candidates` view

### `requirements.txt`
```
streamlit
mysql-connector-python
pandas
plotly
```

---

## Step 8 — Execution Order During Build

1. Run `database_setup.sql` in MySQL (creates entire schema + optimizer engine)
2. Run `seed_data.py` (populates dimensions + 300-500 orders, calls `collect_all_stats()`)
3. Run `streamlit run app.py`
4. Click Query 1 ("Total Revenue by Product") at least 3 times via UI → observe plan escalates from `FULL_SCAN` → `AGGREGATE_PUSHDOWN` → `USE_MV`

---

## Verification Plan

### Automated (SQL)
```sql
-- Verify MV routing after repeated executions
SELECT plan_choice, COUNT(*) FROM query_log GROUP BY plan_choice;
SELECT fingerprint, execution_count, avg_time, last_plan FROM workload_stats;
SELECT * FROM learned_best_plan;
SELECT * FROM mv_metadata;
```

### Manual (Streamlit Demo)
1. Fresh run: Query 1 → expect `FULL_SCAN` or `AGGREGATE_PUSHDOWN`
2. 2nd click → expect same or `AGGREGATE_PUSHDOWN`
3. 3rd click → expect `USE_MV` (MV eligibility threshold met)
4. Query 2 → expect `HASH_JOIN_SIM` (cost > 250 due to JOIN + GROUP BY)
5. Query 3 → expect `AGGREGATE_PUSHDOWN` (GROUP BY + ORDER BY but no MV route)
6. Check "Optimizer Metrics" panel: `mv_metadata.usage_count` increments each time MV is used

---

## Open Questions

> [!NOTE]
> None at this time — all guardrails from the user request have been addressed. Awaiting approval to proceed with code generation.
