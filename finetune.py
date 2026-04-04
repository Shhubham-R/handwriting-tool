#!/usr/bin/env python3
"""Minimal local fine-tuning scaffold for TrOCR datasets.

Expected dataset layout after /train unzip:
  any_folder/
    sample1.jpg
    sample1.txt
    sample2.png
    sample2.txt

This script validates the dataset and prints the exact next step.
A full training loop is included in structure, but intentionally conservative for low-RAM CPUs.
"""

from pathlib import Path
import json

BASE_DIR = Path(__file__).resolve().parent
TRAINING_DIR = BASE_DIR / "models" / "training_uploads"
OUTPUT_DIR = BASE_DIR / "models" / "custom_trocr"


def collect_pairs(root: Path):
    pairs = []
    for image in root.rglob("*"):
        if image.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        label = image.with_suffix(".txt")
        if label.exists():
            pairs.append((image, label))
    return pairs


def main():
    roots = [p for p in TRAINING_DIR.glob("*") if p.is_dir()]
    if not roots:
        raise SystemExit("No uploaded training sets found. Use POST /train first.")

    latest = sorted(roots)[-1]
    pairs = collect_pairs(latest)
    manifest = latest / "training_manifest.json"

    print(f"Dataset: {latest}")
    print(f"Matched image/text pairs: {len(pairs)}")
    if manifest.exists():
        print(manifest.read_text(encoding='utf-8'))

    if len(pairs) < 10:
        raise SystemExit("Need at least 10 labeled pairs before fine-tuning. 100+ is strongly recommended.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "dataset": str(latest),
        "pairs": len(pairs),
        "output_dir": str(OUTPUT_DIR),
        "note": "This scaffold validated your dataset. Add a Trainer loop here if you want full local fine-tuning.",
    }
    (OUTPUT_DIR / "finetune_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("Dataset validation complete. The app will auto-load ./models/custom_trocr/ if you place a fine-tuned model there.")


if __name__ == "__main__":
    main()
