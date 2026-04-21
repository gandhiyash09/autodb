# AutoDB Version 3: Dynamic Adaptive Optimizer & EXPLAIN Upgrades

This implementation plan covers the introduction of adaptive learning to the Cost-Based Optimizer (CBO), MySQL 8.0 REGEXP Query Fingerprinting, explicit plan competition enforcement, EXPLAIN metadata gathering, and further telemetry improvements to error handling and dashboard scaling.

## User Review Required
> [!IMPORTANT]
> **EXPLAIN Gathering Location:** Running `EXPLAIN` inside a MySQL stored procedure and parsing the output into local variables natively requires creating and dropping Temporary Tables continuously (`INSERT INTO temp_explain EXPLAIN...`), which adds severe simulated disk overhead and instability to the procedure. **I propose shifting the `EXPLAIN` extraction to the Python layer (`app.py` and `workload_generator.py`)**. Python will execute the `EXPLAIN` statement first, capture the `rows` and `key` values, and seamlessly pass them into the stored procedure like so: `CALL optimized_execute(query_text, explain_rows, explain_key)`. Do you approve of this approach to keep the SQL procedure clean and performant?

## Proposed Changes

---

### [MODIFY] `sql/setup.sql` 
- **[NEW] `plan_cost_model` table:** Will store `{plan_name, avg_execution_time, cost_multiplier}`. Initialized with baseline multipliers (1.0 for FULL_SCAN, 0.2 for INDEX_SCAN, 0.05 for USE_MV, 0.3 for AGGREGATE) and dynamically updated.
- **[MODIFY] `query_log` table:** Add `explain_rows INT`, `explain_key VARCHAR(50)`, and `error_msg TEXT`.

---

### [MODIFY] `sql/procedures.sql` 
- **[MODIFY] `optimized_execute(IN q TEXT, IN exp_rows INT, IN exp_key VARCHAR(50))`:**
  - **Adaptive Costs:** Pull dynamic multiplier rules from `plan_cost_model` rather than using static constants. After execution, `UPDATE plan_cost_model` using a rolling average of `actual_execution_time` to adjust the weight.
  - **Literal Stripping:** Utilize MySQL 8's `REGEXP_REPLACE(q, '[0-9]+', '?')` and `REGEXP_REPLACE(q, '\'.*?\'', '?')` to completely sanitize filters, mapping structurally identical queries (`WHERE id = 5` and `WHERE id = 10`) to the EXACT same fingerprint string for superior MV thresholds.
  - **Enforced Competition:** Always calculate `ALL` potential trajectories including `USE_MV`. `final_plan` will strictly bind to `LEAST()` matching cost integer ensuring MVs don't automatically override a computationally cheaper Index Scan if one manifests dynamically.

---

### [MODIFY] `backend/workload_generator.py` 
- Extract the `EXPLAIN` tuple mapping prior to calling the optimized routines to cleanly satisfy the signature validation.
- Implement explicit string catch exceptions bypassing the system failure crash.

---

### [MODIFY] `dashboard/app.py` 
- Pre-parse `EXPLAIN` internally exactly like the workload generator does via the terminal GUI.
- **Visuals Upgrade:** Append Top 5 Slow Queries (calculated analytically), explicit Plan Shift over time graphs, and MV usage hit patterns natively using Streamlit mapping architectures.

## Open Questions

If `plan_cost_model` multipliers drastically drift because an environmental anomaly causes an `INDEX_SCAN` pipeline to choke on local constraints (ballooning its metric above a `FULL_SCAN`), do you want a floor/ceiling threshold applied to the adaptive modifier (e.g. `multiplier` can never exceed 1.5 or drop below 0.01) so it doesn't break baseline optimization logic?

## Verification Plan

### Automated Tests
Execute `backend/workload_generator.py`. Visually monitor MySQL database metadata fields:
1. `SELECT * FROM plan_cost_model` should reveal weights deviating slightly from 1.0 (adaptive learning is active).
2. `SELECT explain_rows, explain_key FROM query_log LIMIT 10;` will confirm Python successfully bridged real trace logic into the backend CBO.

### Manual Verification
Launch `dashboard/app.py`. Check the 'Slow Queries' metric block, and inject custom filtered text variables to verify the fingerprint engine maps `"id = 200"` exactly identical to `"id = 99"`.
