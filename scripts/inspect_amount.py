from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "phonepe_source"

targets = [
    RAW / "aggregated" / "transaction" / "country" / "india",
    RAW / "map" / "transaction" / "hover" / "country" / "india",
]

for folder in targets:
    files = sorted(p for p in folder.glob("*/*.json"))   # <year>/<quarter>.json
    print(f"\n=== {folder.relative_to(RAW)}  ({len(files)} files) ===")
    if not files:
        print("No files found - check that this folder exists.")
        continue
    latest = files[-1]
    print("File:", latest.relative_to(RAW))
    data = json.load(open(latest, encoding="utf-8"))["data"]
    print(json.dumps(data, indent=1)[:900])