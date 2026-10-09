from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "bharatpay.db"
OUT = ROOT / "data" / "exports" / "insights.md"

MIN_VOLUME = 50_000_000  # ignore tiny states/UTs for growth leaderboards


def main():
    con = sqlite3.connect(DB)
    latest = con.execute("SELECT MAX(time_id) FROM dim_time").fetchone()[0]
    lines = ["# BharatPay Pulse — Auto-Generated Insights\n"]

    nat = con.execute("""SELECT quarter_label, txn_count, yoy_growth_pct, avg_ticket
                         FROM v_national_quarterly WHERE time_id = ?""", (latest,)).fetchone()
    lines.append(f"## National\nIn {nat[0]}, India recorded {nat[1]:,} PhonePe transactions, "
                 f"up {nat[2]}% year-on-year, at an average ticket size of ₹{nat[3]:,.0f}.\n")

    top = con.execute("""SELECT state_name, txn_count, share_pct, yoy_growth_pct, rank_change_yoy
                         FROM v_state_quarterly WHERE time_id = ? ORDER BY rank_in_quarter LIMIT 5""",
                       (latest,)).fetchall()
    lines.append("## Top states\n" + "\n".join(
        f"- {s} — {c:,} transactions ({p}% national share), {y}% YoY"
        + (f", moved up {r} rank(s)" if r and r > 0 else f", fell {abs(r)} rank(s)" if r and r < 0 else "")
        for s, c, p, y, r in top) + "\n")

    fast = con.execute("""SELECT state_name, yoy_growth_pct, txn_count FROM v_state_quarterly
                          WHERE time_id = ? AND txn_count >= ? AND yoy_growth_pct IS NOT NULL
                          ORDER BY yoy_growth_pct DESC LIMIT 5""", (latest, MIN_VOLUME)).fetchall()
    lines.append(f"## Fastest-growing states (min {MIN_VOLUME:,} txns/quarter)\n" + "\n".join(
        f"- {s}: {g}% YoY ({c:,} transactions)" for s, g, c in fast) + "\n")

    conc = con.execute("""SELECT quarter_label, hhi, top5_share_pct FROM v_state_concentration
                          WHERE time_id = ?""", (latest,)).fetchone()
    lines.append(f"## Market concentration\nAs of {conc[0]}, the state-level HHI is {conc[1]:,.0f} "
                 f"(top 5 states hold {conc[2]}% of volume). "
                 f"{'This indicates a concentrated market.' if conc[1] > 1500 else 'This indicates a competitive, unconcentrated market.'}\n")

    Path(OUT).write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(lines))
    con.close()


if __name__ == "__main__":
    main()