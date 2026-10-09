from pathlib import Path
import string
import re
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
CLEAN = PROC / "clean"
EXPORTS = ROOT / "data" / "exports"
CLEAN.mkdir(parents=True, exist_ok=True)
EXPORTS.mkdir(parents=True, exist_ok=True)

TOL_PCT = 0.1  # reconciliation tolerance, in percent
KEYS = {
    "national_transactions": ["period", "category"],
    "state_transactions": ["state", "period", "category"],
    "state_totals": ["state", "period"],
    "district_transactions": ["state", "district", "period"],
    "state_users": ["state", "period"],
    "district_users": ["state", "district", "period"],
    "state_merchants": ["state", "period"],
    "district_merchants": ["state", "district", "period"],
}

results, exceptions = [], []


def fp(p):
    return f"{int(p) // 10} Q{int(p) % 10}"


def clean_state(s):
    s = re.sub(r"\s+", " ", s.strip().lower().replace("-", " ").replace("&", "and"))
    return string.capwords(s).replace(" And ", " and ")


def clean_district(s):
    return string.capwords(re.sub(r"\s+district$", "", s.strip().lower()))


def record(check, ok, detail="", level="FAIL"):
    status = "PASS" if ok else level
    results.append({"check": check, "status": status, "detail": detail})
    print(f"[{status}] {check}" + (f" - {detail}" if detail else ""))


# ---- load and standardize names ----
T = {}
for name in KEYS:
    df = pd.read_csv(PROC / f"{name}.csv")
    if "state" in df.columns:
        df["state"] = df["state"].map(clean_state)
    if "district" in df.columns:
        df["district"] = df["district"].map(clean_district)
    df["period"] = df["year"] * 10 + df["quarter"]
    T[name] = df

periods = sorted(T["national_transactions"]["period"].unique())

# ---- 1. nulls, duplicate keys, negatives ----
for name, df in T.items():
    nulls = int(df.isna().sum().sum())
    dups = int(df.duplicated(KEYS[name]).sum())
    num = df.select_dtypes("number").drop(columns=["year", "quarter", "period"])
    negs = int((num < 0).sum().sum())
    record(f"{name}: nulls / duplicate keys / negatives", nulls == dups == negs == 0,
           f"nulls={nulls}, dup_keys={dups}, negatives={negs}")


# ---- 2. completeness: every entity x period (x category) present ----
def find_missing(name):
    df, dims = T[name], KEYS[name]
    ent_cols = [c for c in dims if c not in ("period", "category")]
    exp = df[ent_cols].drop_duplicates().assign(_k=1) if ent_cols else pd.DataFrame({"_k": [1]})
    exp = exp.merge(pd.DataFrame({"period": periods, "_k": 1}), on="_k")
    if "category" in dims:
        exp = exp.merge(pd.DataFrame({"category": sorted(df["category"].unique()), "_k": 1}), on="_k")
    exp = exp.drop(columns="_k")
    m = exp.merge(df[dims], on=dims, how="left", indicator=True)
    return m[m["_merge"] == "left_only"][dims]


STRICT = ("national_transactions", "state_transactions", "state_totals")
for name in KEYS:
    miss = find_missing(name)
    detail = f"{len(miss)} missing"
    if len(miss):
        detail += f" (from {fp(miss.period.min())} to {fp(miss.period.max())})"
    record(f"{name}: completeness", len(miss) == 0, detail,
           level="FAIL" if name in STRICT else "WARN")
    if len(miss) and name in STRICT:
        print(miss.head(10).assign(period=miss.head(10)["period"].map(fp)).to_string(index=False))
    for r in miss.head(2000).to_dict("records"):
        exceptions.append({"check": f"{name}: completeness", **r})

# ---- 3. amounts: populated and plausible ----
for name, df in T.items():
    if "transaction_amount" in df.columns:
        nn = int(df["transaction_amount"].isna().sum())
        total = df["transaction_amount"].sum()
        record(f"{name}: amount populated", nn == 0 and total > 0,
               f"null={nn}, total={total:,.0f}")
        ticket = (df["transaction_amount"] / df["transaction_count"].replace(0, float("nan"))).median()
        record(f"{name}: median ticket size plausible", 100 <= ticket <= 20000,
               f"median = {ticket:,.0f} per transaction", level="WARN")


# ---- 4. reconciliation ----
def reconcile(label, child, parent, keys, vals):
    c = child.groupby(keys)[vals].sum(min_count=1)
    p = parent.groupby(keys)[vals].sum(min_count=1)
    j = c.join(p, lsuffix="_child", rsuffix="_parent", how="inner")
    dcols = []
    for v in vals:
        base = j[v + "_parent"].replace(0, float("nan"))
        j[v + "_diff_pct"] = (j[v + "_child"] - j[v + "_parent"]) / base * 100
        dcols.append(v + "_diff_pct")
    bad = j[(j[dcols].abs() > TOL_PCT).any(axis=1)]
    n_uncomparable = int(j[dcols].isna().any(axis=1).sum())
    worst = j[dcols].abs().max()
    worst_txt = ", ".join(f"{c.replace('_diff_pct', '')} {worst[c]:.4f}%" for c in dcols)
    record(f"reconcile {label}", bad.empty and n_uncomparable == 0,
           f"max diff: {worst_txt}; {len(bad)}/{len(j)} groups exceed {TOL_PCT}%; "
           f"{n_uncomparable} uncomparable")
    if not bad.empty:
        bad.reset_index().to_csv(EXPORTS / f"dq_recon_{label.replace(' ', '_')}.csv", index=False)


COUNT = ["transaction_count"]
reconcile("state categories to national", T["state_transactions"], T["national_transactions"],
          ["period", "category"], COUNT)
reconcile("state totals to national", T["state_totals"], T["national_transactions"], ["period"], COUNT)
reconcile("state totals to state categories", T["state_totals"], T["state_transactions"],
          ["state", "period"], COUNT)
reconcile("districts to state totals", T["district_transactions"], T["state_totals"],
          ["state", "period"], COUNT + ["transaction_amount"])

# ---- 5. key alignment across tables, and state-name consistency ----
pairs = [("state_transactions", "state_totals", ["state", "period"]),
         ("state_transactions", "state_users", ["state", "period"]),
         ("state_transactions", "state_merchants", ["state", "period"]),
         ("district_transactions", "district_users", ["state", "district", "period"]),
         ("district_transactions", "district_merchants", ["state", "district", "period"])]
for a, b, keys in pairs:
    m = T[a][keys].drop_duplicates().merge(T[b][keys].drop_duplicates(),
                                           on=keys, how="outer", indicator=True)
    off = m[m["_merge"] != "both"]
    record(f"key alignment: {a} vs {b}", off.empty,
           f"{(off['_merge'] == 'left_only').sum()} only in {a}, "
           f"{(off['_merge'] == 'right_only').sum()} only in {b}", level="WARN")
    for r in off.head(2000).to_dict("records"):
        exceptions.append({"check": f"key alignment {a} vs {b}", **r})

base = set(T["state_transactions"]["state"])
for name, df in T.items():
    if "state" in df.columns and name != "state_transactions":
        diff = set(df["state"]) ^ base
        record(f"state names: {name} vs state_transactions", not diff,
               f"differences: {sorted(diff)}" if diff else f"{len(set(df['state']))} states")

# ---- 6. registered users/merchants (cumulative) should not decrease ----
for name, col in [("state_users", "registered_users"), ("state_merchants", "registered_merchants"),
                  ("district_users", "registered_users"), ("district_merchants", "registered_merchants")]:
    grp = KEYS[name][:-1]
    df = T[name].sort_values(grp + ["period"]).copy()
    df["change"] = df.groupby(grp)[col].diff()
    bad = df[df["change"] < 0]
    top = bad["period"].map(fp).value_counts().head(3).to_dict()
    record(f"{name}: {col} never decreases", bad.empty,
           f"{len(bad)} decreases (worst {df['change'].min():,.0f}); most in {top}", level="WARN")
    for r in bad.head(500)[grp + ["period", "change"]].to_dict("records"):
        exceptions.append({"check": f"{name}: decrease", **r})

# ---- write outputs ----
for name, df in T.items():
    df.drop(columns="period").to_csv(CLEAN / f"{name}.csv", index=False)
report = pd.DataFrame(results)
report.to_csv(EXPORTS / "data_quality_report.csv", index=False)
if exceptions:
    pd.DataFrame(exceptions).to_csv(EXPORTS / "data_quality_exceptions.csv", index=False)
print("\nSummary:\n" + report["status"].value_counts().to_string())