from pathlib import Path
import sqlite3
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "data" / "processed" / "clean"
DB_PATH = ROOT / "db" / "bharatpay.db"
DB_PATH.parent.mkdir(exist_ok=True)

SCHEMA = """
CREATE TABLE dim_time (
    time_id       INTEGER PRIMARY KEY,           -- year*10 + quarter, e.g. 20182
    year          INTEGER NOT NULL,
    quarter       INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    quarter_label TEXT NOT NULL,                 -- 'Q2 2018' (calendar quarter)
    fiscal_year   TEXT NOT NULL,                 -- Indian FY, Apr-Mar, e.g. 'FY2018-19'
    quarter_start TEXT NOT NULL,                 -- ISO date
    period_index  INTEGER NOT NULL UNIQUE        -- 1..N, handy for rolling windows
);
CREATE TABLE dim_state (
    state_id   INTEGER PRIMARY KEY,
    state_name TEXT NOT NULL UNIQUE
);
CREATE TABLE dim_district (
    district_id   INTEGER PRIMARY KEY,
    state_id      INTEGER NOT NULL REFERENCES dim_state(state_id),
    district_name TEXT NOT NULL,
    UNIQUE (state_id, district_name)
);
CREATE TABLE dim_category (
    category_id   INTEGER PRIMARY KEY,
    category_name TEXT NOT NULL UNIQUE
);

CREATE TABLE fact_national_txn (
    time_id INTEGER NOT NULL REFERENCES dim_time(time_id),
    category_id INTEGER NOT NULL REFERENCES dim_category(category_id),
    transaction_count INTEGER NOT NULL,
    PRIMARY KEY (time_id, category_id)
);
CREATE TABLE fact_state_category_txn (
    state_id INTEGER NOT NULL REFERENCES dim_state(state_id),
    time_id INTEGER NOT NULL REFERENCES dim_time(time_id),
    category_id INTEGER NOT NULL REFERENCES dim_category(category_id),
    transaction_count INTEGER NOT NULL,
    PRIMARY KEY (state_id, time_id, category_id)
);
CREATE TABLE fact_state_txn (            -- all categories combined; only level with amounts
    state_id INTEGER NOT NULL REFERENCES dim_state(state_id),
    time_id INTEGER NOT NULL REFERENCES dim_time(time_id),
    transaction_count INTEGER NOT NULL,
    transaction_amount REAL NOT NULL,
    PRIMARY KEY (state_id, time_id)
);
CREATE TABLE fact_district_txn (
    district_id INTEGER NOT NULL REFERENCES dim_district(district_id),
    time_id INTEGER NOT NULL REFERENCES dim_time(time_id),
    transaction_count INTEGER NOT NULL,
    transaction_amount REAL NOT NULL,
    PRIMARY KEY (district_id, time_id)
);
-- registered_* are cumulative counts (stocks): never SUM across quarters.
-- registered_merchants is NULL where the source has no merchant data (not zero).
CREATE TABLE fact_state_footprint (
    state_id INTEGER NOT NULL REFERENCES dim_state(state_id),
    time_id INTEGER NOT NULL REFERENCES dim_time(time_id),
    registered_users INTEGER NOT NULL,
    registered_merchants INTEGER,
    PRIMARY KEY (state_id, time_id)
);
CREATE TABLE fact_district_footprint (
    district_id INTEGER NOT NULL REFERENCES dim_district(district_id),
    time_id INTEGER NOT NULL REFERENCES dim_time(time_id),
    registered_users INTEGER NOT NULL,
    registered_merchants INTEGER,
    PRIMARY KEY (district_id, time_id)
);
CREATE TABLE dq_log (
    log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_type  TEXT NOT NULL,
    state_id    INTEGER,
    district_id INTEGER,
    time_id     INTEGER,
    category_id INTEGER,
    detail      TEXT
);
CREATE INDEX idx_fsc_time ON fact_state_category_txn(time_id);
CREATE INDEX idx_fst_time ON fact_state_txn(time_id);
CREATE INDEX idx_fdt_time ON fact_district_txn(time_id);
CREATE INDEX idx_fsf_time ON fact_state_footprint(time_id);
CREATE INDEX idx_fdf_time ON fact_district_footprint(time_id);
"""

NAMES = ["national_transactions", "state_transactions", "state_totals",
         "district_transactions", "state_users", "district_users",
         "state_merchants", "district_merchants"]


def read(name):
    df = pd.read_csv(CLEAN / f"{name}.csv")
    df["time_id"] = df["year"] * 10 + df["quarter"]
    return df.drop(columns=["year", "quarter"])


def fiscal_year(y, q):
    start = y if q >= 2 else y - 1
    return f"FY{start}-{str(start + 1)[-2:]}"


def main():
    T = {n: read(n) for n in NAMES}

    # ---------- dimensions ----------
    t = (pd.read_csv(CLEAN / "national_transactions.csv")[["year", "quarter"]]
         .drop_duplicates().sort_values(["year", "quarter"]).reset_index(drop=True))
    dim_time = pd.DataFrame({
        "time_id": t["year"] * 10 + t["quarter"],
        "year": t["year"], "quarter": t["quarter"],
        "quarter_label": "Q" + t["quarter"].astype(str) + " " + t["year"].astype(str),
        "fiscal_year": [fiscal_year(y, q) for y, q in zip(t["year"], t["quarter"])],
        "quarter_start": [f"{y}-{(q - 1) * 3 + 1:02d}-01" for y, q in zip(t["year"], t["quarter"])],
        "period_index": range(1, len(t) + 1),
    })

    states = sorted(set().union(*[set(T[n]["state"]) for n in NAMES if "state" in T[n].columns]))
    dim_state = pd.DataFrame({"state_id": range(1, len(states) + 1), "state": states})

    pairs = (pd.concat([T[n][["state", "district"]] for n in NAMES if "district" in T[n].columns])
             .drop_duplicates().sort_values(["state", "district"]).reset_index(drop=True))
    pairs["district_id"] = pairs.index + 1
    dim_district = pairs.merge(dim_state, on="state")

    cats = sorted(T["national_transactions"]["category"].unique())
    dim_category = pd.DataFrame({"category_id": range(1, len(cats) + 1), "category": cats})

    def with_state_id(df):
        out = df.merge(dim_state, on="state", how="left", validate="m:1")
        assert out["state_id"].notna().all()
        return out.drop(columns="state")

    def with_district_id(df):
        out = df.merge(dim_district[["district_id", "state", "district"]],
                       on=["state", "district"], how="left", validate="m:1")
        assert out["district_id"].notna().all()
        return out.drop(columns=["state", "district"])

    def with_category_id(df):
        out = df.merge(dim_category, on="category", how="left", validate="m:1")
        assert out["category_id"].notna().all()
        return out.drop(columns="category")

    dq_parts = []

    # ---------- facts ----------
    f_nat = with_category_id(T["national_transactions"])

    sc = with_category_id(with_state_id(T["state_transactions"]))
    grid = pd.MultiIndex.from_product(
        [dim_state["state_id"], dim_time["time_id"], dim_category["category_id"]],
        names=["state_id", "time_id", "category_id"])
    sc = sc.set_index(["state_id", "time_id", "category_id"]).reindex(grid)
    filled = sc[sc["transaction_count"].isna()].reset_index()[["state_id", "time_id", "category_id"]]
    filled["issue_type"] = "zero-filled state/category row (absent in source)"
    dq_parts.append(filled)
    f_sc = sc.fillna(0).astype({"transaction_count": "int64"}).reset_index()

    f_st = with_state_id(T["state_totals"])

    dt, du = with_district_id(T["district_transactions"]), with_district_id(T["district_users"])
    skel = pd.concat([dt[["district_id", "time_id"]], du[["district_id", "time_id"]]]).drop_duplicates()
    f_dt = skel.merge(dt, on=["district_id", "time_id"], how="left")
    filled = f_dt[f_dt["transaction_count"].isna()][["district_id", "time_id"]].copy()
    filled["issue_type"] = "zero-filled district transactions (users exist, no txn record)"
    dq_parts.append(filled)
    f_dt = f_dt.fillna({"transaction_count": 0, "transaction_amount": 0.0})
    f_dt["transaction_count"] = f_dt["transaction_count"].astype("int64")

    f_sf = (with_state_id(T["state_users"])
            .merge(with_state_id(T["state_merchants"]), on=["state_id", "time_id"], how="left"))
    f_df = du.merge(with_district_id(T["district_merchants"]),
                    on=["district_id", "time_id"], how="left")
    for df in (f_sf, f_df):
        df["registered_merchants"] = df["registered_merchants"].astype("Int64")

    # cumulative counts that go down -> log them
    for df, key in ((f_sf, "state_id"), (f_df, "district_id")):
        for metric in ("registered_users", "registered_merchants"):
            d = df.sort_values([key, "time_id"]).copy()
            d["change"] = d.groupby(key)[metric].diff().astype("float64")
            bad = d[d["change"] < 0][[key, "time_id", "change"]].copy()
            bad["issue_type"] = f"{metric} decreased vs previous quarter"
            bad["detail"] = bad["change"].map(lambda c: f"change = {c:,.0f}")
            dq_parts.append(bad.drop(columns="change"))

    dq_log = pd.concat(dq_parts, ignore_index=True)
    for col in ("state_id", "district_id", "time_id", "category_id", "detail"):
        if col not in dq_log.columns:
            dq_log[col] = None
    dq_log = dq_log[["issue_type", "state_id", "district_id", "time_id", "category_id", "detail"]]

    # ---------- write ----------
    DB_PATH.unlink(missing_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)

    def load(table, df):
        df.to_sql(table, con, if_exists="append", index=False)

    load("dim_time", dim_time)
    load("dim_state", dim_state.rename(columns={"state": "state_name"}))
    load("dim_district", dim_district[["district_id", "state_id", "district"]]
         .rename(columns={"district": "district_name"}))
    load("dim_category", dim_category.rename(columns={"category": "category_name"}))
    load("fact_national_txn", f_nat[["time_id", "category_id", "transaction_count"]])
    load("fact_state_category_txn", f_sc[["state_id", "time_id", "category_id", "transaction_count"]])
    load("fact_state_txn", f_st[["state_id", "time_id", "transaction_count", "transaction_amount"]])
    load("fact_district_txn", f_dt[["district_id", "time_id", "transaction_count", "transaction_amount"]])
    load("fact_state_footprint", f_sf[["state_id", "time_id", "registered_users", "registered_merchants"]])
    load("fact_district_footprint", f_df[["district_id", "time_id", "registered_users", "registered_merchants"]])
    load("dq_log", dq_log)
    con.commit()

    # ---------- verify ----------
    print(f"Built {DB_PATH}\n")
    for (tbl,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' "
                              "AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        n = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"{tbl:<26}{n:>9,}")

    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    mismatch = con.execute("""
        SELECT COUNT(*) FROM (
          SELECT time_id, SUM(transaction_count) c FROM fact_national_txn GROUP BY time_id) n
        JOIN (SELECT time_id, SUM(transaction_count) c FROM fact_state_txn GROUP BY time_id) s
          USING (time_id) WHERE n.c <> s.c""").fetchone()[0]
    print(f"\nForeign-key violations: {len(fk)}")
    print(f"Quarters where state total != national total: {mismatch}")
    con.close()


if __name__ == "__main__":
    main()