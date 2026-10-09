DROP VIEW IF EXISTS v_state_quarterly;
CREATE VIEW v_state_quarterly AS
WITH base AS (
    SELECT s.state_id, s.state_name, t.time_id, t.year, t.quarter, t.quarter_label,
           t.fiscal_year, t.period_index,
           f.transaction_count AS txn_count, f.transaction_amount AS txn_amount
    FROM fact_state_txn f
    JOIN dim_state s ON s.state_id = f.state_id
    JOIN dim_time  t ON t.time_id  = f.time_id
),
calc AS (
    SELECT b.*,
        ROUND(txn_amount / NULLIF(txn_count, 0), 2) AS avg_ticket,
        ROUND(100.0 * txn_count / SUM(txn_count) OVER (PARTITION BY time_id), 3) AS share_pct,
        RANK() OVER (PARTITION BY time_id ORDER BY txn_count DESC) AS rank_in_quarter,
        ROUND(100.0 * (txn_count - LAG(txn_count, 1) OVER w) / NULLIF(LAG(txn_count, 1) OVER w, 0), 2) AS qoq_growth_pct,
        ROUND(100.0 * (txn_count - LAG(txn_count, 4) OVER w) / NULLIF(LAG(txn_count, 4) OVER w, 0), 2) AS yoy_growth_pct,
        ROUND(100.0 * (txn_amount - LAG(txn_amount, 4) OVER w) / NULLIF(LAG(txn_amount, 4) OVER w, 0), 2) AS amount_yoy_growth_pct,
        CASE WHEN COUNT(*) OVER w4 = 4 THEN ROUND(AVG(txn_count) OVER w4, 0) END AS rolling_4q_avg
    FROM base b
    WINDOW w  AS (PARTITION BY state_id ORDER BY period_index),
           w4 AS (PARTITION BY state_id ORDER BY period_index ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)
)
SELECT c.*,
       LAG(rank_in_quarter, 4) OVER w AS rank_prev_year,
       LAG(rank_in_quarter, 4) OVER w - rank_in_quarter AS rank_change_yoy   -- positive = moved up
FROM calc c
WINDOW w AS (PARTITION BY state_id ORDER BY period_index);

DROP VIEW IF EXISTS v_state_fy;
CREATE VIEW v_state_fy AS
WITH fy AS (
    SELECT s.state_id, s.state_name, t.fiscal_year,
           COUNT(*) AS quarters,
           SUM(f.transaction_count) AS txn_count,
           SUM(f.transaction_amount) AS txn_amount
    FROM fact_state_txn f
    JOIN dim_state s ON s.state_id = f.state_id
    JOIN dim_time  t ON t.time_id  = f.time_id
    GROUP BY s.state_id, t.fiscal_year
)
SELECT fy.*,
    ROUND(txn_amount / NULLIF(txn_count, 0), 2) AS avg_ticket,
    CASE WHEN quarters = 4 AND LAG(quarters) OVER w = 4
         THEN ROUND(100.0 * (txn_count - LAG(txn_count) OVER w) / NULLIF(LAG(txn_count) OVER w, 0), 2)
    END AS yoy_growth_pct   -- only between two complete fiscal years
FROM fy
WINDOW w AS (PARTITION BY state_id ORDER BY fiscal_year);

DROP VIEW IF EXISTS v_state_concentration;
CREATE VIEW v_state_concentration AS
SELECT time_id, quarter_label, period_index,
       COUNT(*) AS states,
       ROUND(SUM(share_pct * share_pct), 1) AS hhi,   -- 0..10,000 scale
       ROUND(SUM(CASE WHEN rank_in_quarter <= 5  THEN share_pct END), 2) AS top5_share_pct,
       ROUND(SUM(CASE WHEN rank_in_quarter <= 10 THEN share_pct END), 2) AS top10_share_pct
FROM v_state_quarterly
GROUP BY time_id, quarter_label, period_index;

DROP VIEW IF EXISTS v_state_segments;
CREATE VIEW v_state_segments AS
WITH scored AS (
    SELECT state_id, state_name, time_id, quarter_label, period_index,
           txn_count, share_pct, yoy_growth_pct, avg_ticket,
           NTILE(4) OVER (PARTITION BY time_id ORDER BY txn_count DESC)      AS size_quartile,    -- 1 = largest
           NTILE(4) OVER (PARTITION BY time_id ORDER BY yoy_growth_pct DESC) AS growth_quartile   -- 1 = fastest
    FROM v_state_quarterly
    WHERE yoy_growth_pct IS NOT NULL
)
SELECT scored.*,
    CASE WHEN size_quartile <= 2 AND growth_quartile <= 2 THEN 'Leader'
     WHEN size_quartile <= 2                          THEN 'Mature'
     WHEN growth_quartile <= 2                        THEN 'Rising'
     ELSE 'Watchlist' END AS segment
FROM scored;

-- registered_users / registered_merchants are cumulative counts, not per-quarter activity.
-- Merchant columns are NULL before 2019 Q3; the 2023 Q1 merchant counts show decreases (see dq_log).
DROP VIEW IF EXISTS v_state_engagement;
CREATE VIEW v_state_engagement AS
SELECT s.state_name, t.time_id, t.quarter_label, t.period_index,
       x.transaction_count AS txn_count,
       p.registered_users, p.registered_merchants,
       ROUND(1.0 * x.transaction_count / NULLIF(p.registered_users, 0), 2) AS txn_per_registered_user,
       ROUND(1.0 * x.transaction_count / NULLIF(p.registered_merchants, 0), 2) AS txn_per_merchant,
       ROUND(1000.0 * p.registered_merchants / NULLIF(p.registered_users, 0), 2) AS merchants_per_1000_users
FROM fact_state_txn x
JOIN fact_state_footprint p ON p.state_id = x.state_id AND p.time_id = x.time_id
JOIN dim_state s ON s.state_id = x.state_id
JOIN dim_time  t ON t.time_id  = x.time_id;