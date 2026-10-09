
from pathlib import Path
import json
import pandas as pd

# Locate project root automatically
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Official PhonePe source folder
SOURCE_FOLDER = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "phonepe_source"
    / "aggregated"
    / "transaction"
    / "country"
    / "india"
)

# Output folder
OUTPUT_FOLDER = PROJECT_ROOT / "data" / "processed"
OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

records = []

# Read every year folder (2018, 2019...)
for year_folder in sorted(SOURCE_FOLDER.iterdir()):
    # Skip files and non-year folders like "state"
    if not year_folder.is_dir() or not year_folder.name.isdigit():
        continue

    year = int(year_folder.name)
    # Read every quarter file (1.json, 2.json...)
    for json_file in sorted(year_folder.glob("*.json")):
        quarter = int(json_file.stem)

        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Extract every payment type
        for item in data["data"]["transactionData"]:
            instrument = item["paymentInstruments"][0]

            records.append(
                {
                "year": year,
                "quarter": quarter,
                "payment_type": item["name"],
                "instrument_type": instrument.get("type", "Unknown"),
                "transaction_count": instrument.get("count", 0),
                }
            )

# Create DataFrame
df = pd.DataFrame(records)

# Save our own processed dataset
output_file = OUTPUT_FOLDER / "transactions_master.csv"
df.to_csv(output_file, index=False)

print("=" * 40)
print("Extraction Complete")
print("=" * 40)
print(f"Rows Created : {len(df):,}")
print(f"Years Covered: {df['year'].min()} - {df['year'].max()}")
print(f"Payment Types: {df['payment_type'].nunique()}")
print(f"Saved To     : {output_file}")