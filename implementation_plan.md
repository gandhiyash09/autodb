# AutoDB: Cost-Based Optimizer & Workload Expansion Upgrade

This document outlines the comprehensive execution plan to upgrade AutoDB from a heuristic/rule-based router to a fully robust, modular cost-based optimizer (CBO) simulation suitable for an academic systems project.

## Goal Description
The objective is to replace static rule-based query routing with a dynamic cost-based model that calculates relative execution costs for different access paths (`FULL_SCAN`, `INDEX_SCAN`, `USE_MV`, `AGGREGATE_PUSHDOWN`). The system will also be expanded to support dynamic Materialized View (MV) lifecycle management (creation, tracking, and staleness refreshing), a dynamic index recommendation engine, and baseline performance comparisons via `normal_execute`. Finally, the monolithic file structure will be refactored into a clean, separated application geometry.

## User Review Required
> [!IMPORTANT]
> **Dynamic MV Strategy:** Currently, MVs are maintained via real-time triggers. To support dynamic *creation* of MVs on-the-fly when a query hits 5 executions, we will shift to a "Refresh-on-Demand" strategy. Triggers on `order_fact` will only mark `is_stale = TRUE` in `mv_metadata`. The optimizer will then perform a standard query route while asynchronously (or synchronously) rebuilding the MV, rather than the triggers updating row-by-row on the fly. This better mimics real-world enterprise databases. Do you approve of transitioning from real-time trigger updates to a staleness + refresh-on-demand model?

## Proposed Changes

---

### Phase 1: Architectural Refactor
We will decouple the monolithic files into distinct layers.

#### [NEW] `sql/setup.sql`
- Contains all base relation schemas (`order_fact`, `date_dim`, etc.)
- Defines updated metadata tracking schemas:
  - Add `query_explanation` and `normal_execution_time` to `query_log`
  - Update `mv_metadata` schema (`query_fingerprint` mapped to dynamic MVs)
  - Create tables for AI explanation logs and Index Recommendations

#### [NEW] `sql/procedures.sql`
- Contains the rewritten `optimized_execute` using new cost math.
- Contains the new `normal_execute` which runs raw SQL natively and logs baseline time.
- Contains dynamic MV compilation procedures `CREATE TABLE my_dynamic_mv AS SELECT...`

#### [NEW] `backend/workload_generator.py`
- Replaces `seed_data.py` with expanded scope.
- Populates dimensions and fact tables (15,000+ rows).
- Randomly generates between 100-300 diverse queries (Filters, Group By, Join mixed).
- Simulates initial history execution sequentially to trigger AutoDB's dynamic threshold training prior to the UI opening.

#### [NEW] `backend/optimizer_logic.py`
- Migrates the python-specific workload analysis (such as Graph AI Explanations building) out of Streamlit into a manageable module.

#### [MODIFY] `dashboard/app.py`
- Moves existing `app.py` into a visualization sub-folder.
- Overhauls UI to display:
  - Baseline vs Optimized Time (Performance Improvement %)
  - Dynamic Index Generator Recommendations
  - Query Cost / AI Explanation block output mapped per query

#### [DELETE] `database_setup.sql`, `seed_data.py`, `app.py` (Base Level)
- Clean up the root directory and delete the monolithic prototypes.

---

### Phase 2: Cost-Based Optimizer (CBO) Models

Inside `procedures.sql`, `get_query_cost()` will be rewritten utilizing base cardinality logic spanning the 4 plan trajectories:
- `FULL_SCAN`: `total_rows * 1.0`
- `INDEX_SCAN`: `total_rows * selectivity * 0.2`
- `MATERIALIZED VIEW`: `mv_rows * 0.05`
- `AGGREGATE_PUSHDOWN`: `total_rows * 0.3`

The lowest numerical valuation mandates the selected `final_plan`. `selectivity` dynamically pulls from `column_stats`.

---

### Phase 3: Dynamic View & Index Engines

1. **Materialized Views:**
   When `optimized_execute` handles a query structure that repeats > 5 times, it will spawn a dynamic materialized table (e.g., `mv_hash123`) and map it inside `mv_metadata`. 
   If `order_fact` is inserted, all MVs flag as `is_stale = TRUE`. When queried again, AutoDB evaluates if the cost of refreshing the MV is cheaper than a `FULL_SCAN`.

2. **Index Recommendations:**
   We will update `workload_stats` and the recommendation view. When a query is highly frequent AND has high calculated `base_cost` natively, AutoDB logs a `CREATE INDEX xyz` syntactical recommendation along with pre-Index VS post-Index hypothetical cost ratios!

---

### Phase 4: Explanation Modeler (AI Layer)

For every query routed through AutoDB, a Python daemon script (or SQL conditional generator) constructs a human-readable justification logic map (`"USE_MV selected because Base Cost (5000) > MV Cost (150)"`) and writes it back to `query_log` for Streamlit to cleanly project to end users upon executing UI actions.

---

## Open Questions

1. **Dashboard Refactoring limitations:** Should the Streamlit UI remain limited to executing *predefined* buttons simulating the generated 100-300 background queries, or do you want the interactive `Text Area` input to persist for users testing their own arbitrary injections?
2. **Dynamic MV Mapping Constraints:** Is there a maximum threshold to how many dynamic MVs AutoDB is permitted to spawn if the workload script generates 300 highly varied aggregations? Capping the MV creation strictly at the highest repetition tiers (e.g. only 5 tables max) helps prevent database cluster clutter.

## Verification Plan

### Automated Tests
1. Execute `backend/workload_generator.py` sequentially pushing all 300 queries.
2. Interrogate `mv_metadata` to verify dynamic MV tables successfully spin up in MySQL post-threshold processing.
3. Compare `normal_execution_time` vs `optimized_execution_time` averages using straight SQL extraction validation scripts.

### Manual Verification
1. Click predefined aggregate requests inside the Streamlit WebApp.
2. Visually verify the Graph logic renders the AI generated `Explanation Text`.
3. Check the Index Suggestion metadata table for actionable syntax.
