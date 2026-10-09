from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "phonepe_source"
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)


def india_root(section, kind):
    base = RAW / section / kind
    if section == "map":
        base = base / "hover"
    return base / "country" / "india"


def iter_period_files(folder):
    """Yield (year, quarter, path) for <folder>/<year>/<quarter>.json."""
    for year_dir in sorted(folder.iterdir()):
        if year_dir.is_dir() and year_dir.name.isdigit():
            for f in sorted(year_dir.glob("*.json")):
                yield int(year_dir.name), int(f.stem), f


def state_dirs(root):
    return [d for d in sorted((root / "state").iterdir()) if d.is_dir()]


def load(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)["data"]


def txn_rows(data, year, quarter, **extra):
    # aggregated files carry counts only (no amount) in this release
    for item in data["transactionData"]:
        for inst in item["paymentInstruments"]:
            yield {**extra, "year": year, "quarter": quarter,
                   "category": item["name"],
                   "transaction_count": inst.get("count")}


def national_transactions():
    root = india_root("aggregated", "transaction")
    rows = []
    for y, q, f in iter_period_files(root):
        rows.extend(txn_rows(load(f), y, q))
    return pd.DataFrame(rows)


def state_transactions():
    root = india_root("aggregated", "transaction")
    rows = []
    for sd in state_dirs(root):
        for y, q, f in iter_period_files(sd):
            rows.extend(txn_rows(load(f), y, q, state=sd.name))
    return pd.DataFrame(rows)


def state_totals():
    """State-level count AND amount (all categories combined), from country-level hover files."""
    root = india_root("map", "transaction")
    rows = []
    for y, q, f in iter_period_files(root):
        for d in load(f)["hoverDataList"]:
            for m in d["metric"]:
                rows.append({"state": d["name"], "year": y, "quarter": q,
                             "transaction_count": m.get("count"),
                             "transaction_amount": m.get("amount")})
    return pd.DataFrame(rows)


def district_transactions():
    root = india_root("map", "transaction")
    rows = []
    for sd in state_dirs(root):
        for y, q, f in iter_period_files(sd):
            for d in load(f)["hoverDataList"]:
                for m in d["metric"]:
                    rows.append({"state": sd.name, "district": d["name"],
                                 "year": y, "quarter": q,
                                 "transaction_count": m.get("count"),
                                 "transaction_amount": m.get("amount")})
    return pd.DataFrame(rows)


def hover_entities(kind, level):
    """Users or merchants from map/hover files, at state or district level."""
    root = india_root("map", kind)
    rows = []
    if level == "state":
        sources = [(None, root)]
    else:
        sources = [(sd.name, sd) for sd in state_dirs(root)]
    for state_name, folder in sources:
        for y, q, f in iter_period_files(folder):
            for name, vals in load(f)["hoverData"].items():
                row = {"year": y, "quarter": q}
                if level == "state":
                    row["state"] = name
                else:
                    row["state"], row["district"] = state_name, name
                row.update(vals)
                rows.append(row)
    df = pd.DataFrame(rows)
    return df.rename(columns={
        "registeredCount": "registered_users" if kind == "user" else "registered_merchants",
        "appOpens": "app_opens"})


if __name__ == "__main__":
    tables = {
        "national_transactions": national_transactions,
        "state_transactions": state_transactions,
        "state_totals": state_totals,
        "district_transactions": district_transactions,
        "state_users": lambda: hover_entities("user", "state"),
        "district_users": lambda: hover_entities("user", "district"),
        "state_merchants": lambda: hover_entities("merchant", "state"),
        "district_merchants": lambda: hover_entities("merchant", "district"),
    }
    for name, fn in tables.items():
        df = fn()
        df.to_csv(OUT / f"{name}.csv", index=False)
        print(f"{name:<24} rows={len(df):>8,} | {df['year'].min()}-{df['year'].max()} | cols={list(df.columns)}")