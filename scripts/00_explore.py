from pathlib import Path
import json

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "phonepe_source"
print("Total JSON files:", sum(1 for _ in RAW.rglob("*.json")))

for section in ["aggregated", "map", "top"]:
    for kind in ["transaction", "user", "merchant"]:
        files = sorted((RAW / section / kind).rglob("*.json"))
        if not files:
            print(f"{section}/{kind}: none")
            continue
        with open(files[0], encoding="utf-8") as f:
            data = json.load(f)["data"]
        print(f"{section}/{kind}: {len(files)} files | first: {files[0].relative_to(RAW)} | keys: {list(data.keys())}")

# Category names in the national file
nat = RAW / "aggregated/transaction/country/india/2024/1.json"
with open(nat, encoding="utf-8") as f:
    print([i["name"] for i in json.load(f)["data"]["transactionData"]])