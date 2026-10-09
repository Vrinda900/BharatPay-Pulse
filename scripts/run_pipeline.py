from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

STEPS = [
    "01_extract.py",
    "02_data_quality.py",
    "03_build_warehouse.py",
    "04_build_views.py",
    "05_generate_insights.py",
]


def main():
    print("=" * 60)
    print("BharatPay Pulse — Full Pipeline Run")
    print("=" * 60)
    for step in STEPS:
        path = SCRIPTS / step
        print(f"\n--- Running {step} ---")
        result = subprocess.run([sys.executable, str(path)], cwd=ROOT)
        if result.returncode != 0:
            print(f"\n[FAILED] {step} exited with code {result.returncode}. Stopping pipeline.")
            sys.exit(1)
    print("\n" + "=" * 60)
    print("Pipeline complete. Check data/exports/ and db/bharatpay.db")
    print("=" * 60)


if __name__ == "__main__":
    main()