from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).resolve().parent.parent

sample_file = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "phonepe_source"
    / "aggregated"
    / "transaction"
    / "country"
    / "india"
    / "2018"
    / "1.json"
)

with open(sample_file, "r", encoding="utf-8") as f:
    data = json.load(f)

print(data["data"]["transactionData"][0])