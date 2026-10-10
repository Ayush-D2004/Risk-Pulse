#!/usr/bin/env python3
"""
RiskPulse Data Downloader & Reconstructor
-----------------------------------------
Automates downloading historical datasets and precomputed pipeline artifacts
from Google Drive and reconstructs the expected repository directory layout:
  - data/processed/full_dataset-release.csv
  - data/processed/reduced_dataset-release.csv
  - data/pipeline_output/* (e.g. canonical_events.csv, guard_scored.csv, etc.)
"""

import os
import sys
import shutil
import zipfile
import subprocess
from pathlib import Path

# ==========================================
# CONFIGURATION
# ==========================================
GDRIVE_FILE_ID = "1jm-49S-1m6m1u74ll8p_mOl7ooHAtSiP"
GDRIVE_URL = f"https://drive.google.com/uc?id={GDRIVE_FILE_ID}"
ZIP_FILENAME = "RiskPulse_Historical_Data.zip"
BASE_DATA_DIR = Path("data")

def ensure_gdown():
    """Ensures gdown is installed for reliable Google Drive large-file downloads."""
    try:
        import gdown
    except ImportError:
        print("📦 'gdown' is not installed. Installing it now...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "gdown"])
        import gdown
    return gdown

def determine_target_path(member_path: str) -> Path | None:
    """
    Intelligently maps any archived file path inside the zip into the exact
    canonical directory structure expected by the RiskPulse project.
    """
    normalized = member_path.replace("\\", "/").strip("/")
    filename = os.path.basename(normalized)
    
    # Ignore hidden system files like __MACOSX, .DS_Store, etc.
    if "__MACOSX" in normalized or filename.startswith("."):
        return None

    # 1. Map raw/processed dataset CSVs directly to data/processed/
    if filename == "full_dataset-release.csv":
        return BASE_DATA_DIR / "processed" / "full_dataset-release.csv"
    if filename == "reduced_dataset-release.csv":
        return BASE_DATA_DIR / "processed" / "reduced_dataset-release.csv"

    # 2. Map pipeline outputs to data/pipeline_output/
    if "pipeline_output" in normalized:
        subparts = normalized.split("pipeline_output/", 1)
        subpath = subparts[1] if len(subparts) > 1 and subparts[1] else filename
        return BASE_DATA_DIR / "pipeline_output" / subpath

    # 3. Handle processed folder if nested
    if "processed" in normalized:
        subparts = normalized.split("processed/", 1)
        subpath = subparts[1] if len(subparts) > 1 and subparts[1] else filename
        return BASE_DATA_DIR / "processed" / subpath

    # 4. Fallback: preserve relative structure inside data/
    return BASE_DATA_DIR / normalized

def main():
    print("=" * 70)
    print("🚀 RiskPulse Automated Historical Data Downloader")
    print("=" * 70)
    print(f"🔗 Google Drive File ID: {GDRIVE_FILE_ID}")
    print(f"📁 Target Base Directory: {BASE_DATA_DIR.resolve()}\n")

    gdown = ensure_gdown()

    # Step 1: Download ZIP from Google Drive
    print(f"📥 [1/3] Downloading historical package from Google Drive...")
    try:
        gdown.download(GDRIVE_URL, ZIP_FILENAME, quiet=False)
    except Exception as e:
        print(f"\n❌ Error downloading file via gdown: {e}")
        print("\n💡 Manual Fallback:")
        print(f"You can manually download the zip from:")
        print(f"  https://drive.google.com/file/d/{GDRIVE_FILE_ID}/view?usp=sharing")
        print(f"Save it as '{ZIP_FILENAME}' in this folder and re-run this script.")
        sys.exit(1)

    if not os.path.exists(ZIP_FILENAME):
        print(f"\n❌ Download failed: '{ZIP_FILENAME}' not found.")
        sys.exit(1)

    zip_size_mb = os.path.getsize(ZIP_FILENAME) / (1024 * 1024)
    print(f"✅ Download complete! File size: {zip_size_mb:.2f} MB\n")

    # Step 2: Extract & Reconstruct Directory Structure
    print(f"📦 [2/3] Extracting & reconstructing directory layout...")
    extracted_files = []

    try:
        with zipfile.ZipFile(ZIP_FILENAME, "r") as zip_ref:
            members = zip_ref.infolist()
            total_members = len([m for m in members if not m.is_dir()])
            count = 0

            for member in members:
                if member.is_dir():
                    continue

                target_path = determine_target_path(member.filename)
                if not target_path:
                    continue

                # Create destination directory
                target_path.parent.mkdir(parents=True, exist_ok=True)

                # Extract file
                with zip_ref.open(member) as src, open(target_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)

                file_size_mb = os.path.getsize(target_path) / (1024 * 1024)
                extracted_files.append((target_path, file_size_mb))
                count += 1
                print(f"  [{count}/{total_members}] ➡️  {target_path} ({file_size_mb:.2f} MB)")

    except zipfile.BadZipFile:
        print("\n❌ Error: The downloaded file is not a valid zip archive.")
        print("Please check Google Drive permissions (ensure access is set to 'Anyone with the link').")
        sys.exit(1)

    # Step 3: Cleanup temporary zip
    print(f"\n🧹 [3/3] Cleaning up temporary archive '{ZIP_FILENAME}'...")
    try:
        os.remove(ZIP_FILENAME)
    except OSError:
        pass

    # Step 4: Verification & Final Report
    print("\n" + "=" * 70)
    print("✅ RECONSTRUCTION SUMMARY & VERIFICATION")
    print("=" * 70)

    key_checks = [
        ("Full Historical Dataset", BASE_DATA_DIR / "processed" / "full_dataset-release.csv"),
        ("Reduced Historical Dataset", BASE_DATA_DIR / "processed" / "reduced_dataset-release.csv"),
        ("Canonical Events Output", BASE_DATA_DIR / "pipeline_output" / "canonical_events.csv"),
    ]

    all_ok = True
    for label, path in key_checks:
        if path.exists():
            size_mb = os.path.getsize(path) / (1024 * 1024)
            print(f"  ✓ {label:<28}: Found ({size_mb:.2f} MB) -> {path}")
        else:
            print(f"  ⚠️ {label:<28}: Not found at {path}")
            all_ok = False

    print("\n🎉 All set! The dataset is ready for offline pipeline execution:")
    print("  python src/pipeline/run_pipeline.py --input data/processed/full_dataset-release.csv --output-dir data/pipeline_output")
    print("=" * 70)

if __name__ == "__main__":
    main()
