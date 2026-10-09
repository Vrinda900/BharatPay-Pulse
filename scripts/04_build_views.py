from pathlib import Path
import sqlite3
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "bharatpay.db"
SQL_DIR = ROOT / "sql"
EXPORT_DIR = ROOT / "data" / "exports" / "powerbi"


def main():
    con = sqlite3.connect(DB)
    for f in sorted(SQL_DIR.glob("*.sql")):
        con.executescript(f.read_text(encoding="utf-8"))
        print("applied", f.name)

    print("\nView row counts")
    views = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='view' ORDER BY name")]
    for v in views:
        n = con.execute(f"SELECT COUNT(*) FROM {v}").fetchone()[0]
        print(f"  {v:<26}{n:>8,}")

    bad = con.execute("""
        SELECT COUNT(*) FROM (SELECT time_id, ROUND(SUM(share_pct), 1) AS s
                              FROM v_state_quarterly GROUP BY time_id)
        WHERE s NOT BETWEEN 99.9 AND 100.1""").fetchone()[0]
    print(f"\nQuarters where state shares don't sum to ~100%: {bad}")

    print("\nNational, last 5 quarters (quarter, count, YoY %, rolling 4Q avg, avg ticket)")
    for r in con.execute("""SELECT quarter_label, txn_count, yoy_growth_pct, rolling_4q_avg, avg_ticket
                            FROM v_national_quarterly ORDER BY period_index DESC LIMIT 5"""):
        print(" ", r)

    print("\nTop 5 states, latest quarter (state, count, share %, YoY %, rank, rank change)")
    for r in con.execute("""SELECT state_name, txn_count, share_pct, yoy_growth_pct, rank_in_quarter, rank_change_yoy
                            FROM v_state_quarterly
                            WHERE time_id = (SELECT MAX(time_id) FROM dim_time)
                            ORDER BY rank_in_quarter LIMIT 5"""):
        print(" ", r)

    print("\nConcentration, latest quarter (HHI, top-5 share %)")
    print(" ", con.execute("""SELECT quarter_label, hhi, top5_share_pct FROM v_state_concentration
                              ORDER BY period_index DESC LIMIT 1""").fetchone())

    # ---- export every view to CSV for Power BI ----
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    for v in views:
        pd.read_sql(f"SELECT * FROM {v}", con).to_csv(EXPORT_DIR / f"{v}.csv", index=False)
    print(f"\nExported {len(views)} views to {EXPORT_DIR}")

    con.close()


if __name__ == "__main__":
    main()