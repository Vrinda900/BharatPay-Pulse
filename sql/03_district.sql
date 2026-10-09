DROP VIEW IF EXISTS v_district_quarterly;
CREATE VIEW v_district_quarterly AS
WITH base AS (
    SELECT d.district_id, d.district_name, s.state_id, s.state_name,
           t.time_id, t.quarter_label, t.fiscal_year, t.period_index,
           f.transaction_count AS txn_count, f.transaction_amount AS txn_amount
    FROM fact_district_txn f
    JOIN dim_district d ON d.district_id = f.district_id
    JOIN dim_state    s ON s.state_id    = d.state_id
    JOIN dim_time     t ON t.time_id     = f.time_id
)
SELECT b.*,
    ROUND(txn_amount / NULLIF(txn_count, 0), 2) AS avg_ticket,
    ROUND(100.0 * txn_count / NULLIF(SUM(txn_count) OVER (PARTITION BY state_id, time_id), 0), 2) AS share_of_state_pct,
    RANK() OVER (PARTITION BY state_id, time_id ORDER BY txn_count DESC) AS rank_in_state,
    RANK() OVER (PARTITION BY time_id ORDER BY txn_count DESC) AS rank_national,
    ROUND(100.0 * (txn_count - LAG(txn_count, 4) OVER w) / NULLIF(LAG(txn_count, 4) OVER w, 0), 2) AS yoy_growth_pct
FROM base b
WINDOW w AS (PARTITION BY district_id ORDER BY period_index);