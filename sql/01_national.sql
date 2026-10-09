DROP VIEW IF EXISTS v_national_quarterly;
CREATE VIEW v_national_quarterly AS
WITH q AS (
    SELECT t.time_id, t.year, t.quarter, t.quarter_label, t.fiscal_year, t.period_index,
           SUM(f.transaction_count) AS txn_count
    FROM fact_national_txn f
    JOIN dim_time t ON t.time_id = f.time_id
    GROUP BY t.time_id
),
a AS (
    SELECT time_id, SUM(transaction_amount) AS txn_amount
    FROM fact_state_txn
    GROUP BY time_id
),
j AS (
    SELECT q.*, a.txn_amount
    FROM q JOIN a ON a.time_id = q.time_id
)
SELECT
    time_id, year, quarter, quarter_label, fiscal_year, period_index,
    txn_count, txn_amount,
    ROUND(txn_amount / NULLIF(txn_count, 0), 2) AS avg_ticket,
    ROUND(100.0 * (txn_count - LAG(txn_count, 1) OVER w) / NULLIF(LAG(txn_count, 1) OVER w, 0), 2) AS qoq_growth_pct,
    ROUND(100.0 * (txn_count - LAG(txn_count, 4) OVER w) / NULLIF(LAG(txn_count, 4) OVER w, 0), 2) AS yoy_growth_pct,
    ROUND(100.0 * (txn_amount - LAG(txn_amount, 4) OVER w) / NULLIF(LAG(txn_amount, 4) OVER w, 0), 2) AS amount_yoy_growth_pct,
    CASE WHEN COUNT(*) OVER w4 = 4 THEN ROUND(AVG(txn_count) OVER w4, 0) END AS rolling_4q_avg
FROM j
WINDOW w  AS (ORDER BY period_index),
       w4 AS (ORDER BY period_index ROWS BETWEEN 3 PRECEDING AND CURRENT ROW);

DROP VIEW IF EXISTS v_national_category_mix;
CREATE VIEW v_national_category_mix AS
SELECT
    t.time_id, t.quarter_label, t.fiscal_year, t.period_index,
    c.category_name,
    f.transaction_count AS txn_count,
    ROUND(100.0 * f.transaction_count / SUM(f.transaction_count) OVER (PARTITION BY f.time_id), 2) AS share_pct,
    ROUND(100.0 * (f.transaction_count - LAG(f.transaction_count, 4) OVER w)
          / NULLIF(LAG(f.transaction_count, 4) OVER w, 0), 2) AS yoy_growth_pct
FROM fact_national_txn f
JOIN dim_time t     ON t.time_id = f.time_id
JOIN dim_category c ON c.category_id = f.category_id
WINDOW w AS (PARTITION BY f.category_id ORDER BY t.period_index);