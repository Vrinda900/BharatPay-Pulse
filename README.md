# BharatPay Pulse — Digital Payments Intelligence Platform

An end-to-end Business Intelligence project analyzing India's digital payments landscape using official PhonePe Pulse data. Built with **Python, SQLite, SQL, and Power BI** — from raw JSON to an automated ETL pipeline, a dimensional data warehouse, analytical SQL views, and a 4-page interactive dashboard.

**Author:** Vrinda Singhal

---

## What this project does

PhonePe publishes quarterly transaction, user, and merchant data for every state and district in India as open JSON data. This project turns that raw data into decision-ready business intelligence:

- **38.66 billion transactions** analyzed across **34 quarters** (Q1 2018 – Q2 2026)
- **36 states/UTs** and **783 districts** covered
- A fully reproducible pipeline: one command rebuilds everything from raw JSON to final dashboard-ready CSVs
- 4 Power BI pages covering national trends, state-level performance, growth segmentation, and auto-generated business insights

## Architecture

```
Official JSON (PhonePe Pulse)
        │
        ▼
  Python ETL (pandas)
        │
        ▼
  Data Quality Layer  ──► data/exports/data_quality_report.csv
        │
        ▼
  SQLite Data Warehouse (star schema)
        │
        ▼
  Advanced SQL Views (window functions, growth, concentration, segmentation)
        │
        ▼
  ┌─────────────┴─────────────┐
  ▼                           ▼
Power BI Dashboard      Automated Insight Generator (rule-based, no LLM)
(4 pages)                      │
                                ▼
                          data/exports/insights.md
```

### Data warehouse schema

A standard star schema in SQLite (`db/bharatpay.db`):

- **Dimensions:** `dim_time` (with calendar quarter *and* Indian fiscal year), `dim_state`, `dim_district`, `dim_category`
- **Facts:** `fact_national_txn`, `fact_state_category_txn`, `fact_state_txn` (has amounts), `fact_district_txn` (has amounts), `fact_state_footprint`, `fact_district_footprint` (registered users/merchants)
- **`dq_log`:** every zero-filled row and data anomaly found during the build, logged with its reason

### SQL views (`sql/`)

Eight analytical views built with window functions — YoY/QoQ growth, rolling 4-quarter averages, state rankings and rank movement, market share, HHI concentration index, and `NTILE`-based growth/size segmentation (Leader / Mature / Rising / Watchlist).

## Dashboard pages

| Page | What it shows |
|---|---|
| **Executive Pulse** | National KPIs, transaction trend with rolling average, payment category mix over time |
| **India State Pulse** | Geographic bubble map, top 10 states by volume, full state performance table |
| **Growth Intelligence** | Growth-vs-size scatter plot (segmented), market concentration (HHI) trend, fastest-growing states |
| **Business Insights** | Auto-generated key findings as insight cards, engagement (transactions per registered user) by state |

Screenshots of all four pages are in [`docs/`](docs/).

## Setup and running it yourself

### Prerequisites
- Python 3.10+
- Power BI Desktop (Windows) — optional, only needed to view/edit the dashboard

### 1. Clone and set up
```bash
git clone <your-repo-url>
cd BharatPay-Pulse
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 2. Get the data
This repo does not include the raw PhonePe data (it's large and excluded via `.gitignore`). Download it yourself:
```bash
git clone https://github.com/PhonePe/pulse.git
```
Copy the `aggregated`, `map`, and `top` folders from the cloned `pulse/data/` directory into `data/raw/phonepe_source/` in this project.

### 3. Run the full pipeline
```bash
python scripts\run_pipeline.py
```
This runs all five stages in order — extraction, data quality checks, warehouse build, SQL views, and insight generation — and stops immediately if any stage fails. Output lands in `data/processed/`, `db/bharatpay.db`, `data/exports/powerbi/`, and `data/exports/insights.md`.

### 4. Open the dashboard
Open `BharatPay_Pulse.pbix` in Power BI Desktop. If you've re-run the pipeline and the data has changed, use **Home → Refresh** to pull in the updated CSVs from `data/exports/powerbi/`.

## Project structure

```
BharatPay-Pulse/
├── data/
│   ├── raw/phonepe_source/     # raw PhonePe JSON (not committed — see Setup)
│   ├── processed/              # extracted + cleaned CSVs
│   └── exports/                # Power BI source CSVs, insights.md, data quality report
├── db/
│   └── bharatpay.db            # SQLite data warehouse
├── scripts/
│   ├── 01_extract.py           # JSON → 8 processed CSV tables
│   ├── 02_data_quality.py      # null/duplicate/reconciliation checks, name standardization
│   ├── 03_build_warehouse.py   # builds the star schema in SQLite
│   ├── 04_build_views.py       # applies SQL views, exports CSVs for Power BI
│   ├── 05_generate_insights.py # rule-based text insights from the SQL views
│   └── run_pipeline.py         # runs all of the above in order
├── sql/                        # the 8 analytical views, as .sql files
├── docs/                       # dashboard screenshots
├── requirements.txt
└── README.md
```

## Data limitations

Transparency about the data matters as much as the analysis itself. A few things worth knowing before trusting a number from this project at face value:

- **Scope:** this covers PhonePe's own transactions only, not all of India's UPI/digital payment volume. PhonePe is a large share of the market but not the whole of it.
- **No category-level rupee amounts.** The source JSON for category-level data (P2P/Retail/Utility) includes transaction *counts* only, not amounts, in this data release. Rupee amounts exist only as state/district totals (all categories combined), so average ticket size is calculated at the total level, not per category.
- **Category naming differs from PhonePe's own documentation.** The underlying data uses the labels `P2P`, `Retail`, and `Utility`; PhonePe's public README describes them as P2P, Business, and Utilities. This project uses the labels as they appear in the actual data files.
- **Merchant data coverage is incomplete in early quarters.** State-level merchant figures are missing before 2019 Q3; district-level merchant figures are sparse before 2022 Q4. These are left as NULL (not zero) in the warehouse and should be treated as unreliable before those dates.
- **Two anomalies in cumulative counts.** Registered-merchant figures show unexpected quarter-over-quarter decreases concentrated in 2023 Q1 (likely a data restatement), and registered-user figures show a similar pattern concentrated in 2026 Q2 (the most recent quarter in this dataset). Both are logged in `dq_log` inside the warehouse; neither is corrected or smoothed over, since the cause isn't confirmed.
- All of the above were found and verified through the automated data quality checks in `scripts/02_data_quality.py`, not assumed — see `data/exports/data_quality_report.csv` and `data/exports/data_quality_exceptions.csv` for the full detail.

## Data source and license

Data from the [PhonePe Pulse](https://github.com/PhonePe/pulse) open-data repository, licensed under [CDLA-Permissive-2.0](https://cdla.dev/permissive-2-0/). This project is an independent analysis built on that data and is not affiliated with or endorsed by PhonePe.
