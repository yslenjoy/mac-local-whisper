#!/usr/bin/env python3
"""
Export manifest.jsonl to train/val JSONL files for Whisper fine-tuning.

Usage:
    python3 finetune/export.py
    python3 finetune/export.py --data-dir ~/path/to/data
    python3 finetune/export.py --val-ratio 0.2 --seed 42
"""

import argparse
import json
import random
import re
import sys
from pathlib import Path

DEFAULT_DATA_DIR = Path.home() / "Documents/Developer/whisper-finetune-data"


def load_manifest(path: Path) -> list[dict]:
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def get_final_text(entry: dict) -> str | None:
    """Return the best available transcription text for an entry."""
    # reviewed entries: use final_text
    if entry.get("final_text"):
        return entry["final_text"].strip()
    # corrected by API: use api text
    if entry.get("status") == "corrected" and entry.get("text"):
        return entry["text"].strip()
    return None


def load_vocab_overrides(data_dir: Path) -> dict[str, str]:
    """Load vocab_overrides.json if it exists."""
    path = data_dir / "vocab_overrides.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def apply_vocab(text: str, overrides: dict[str, str]) -> str:
    """Apply vocabulary overrides to text."""
    for wrong, correct in overrides.items():
        text = re.sub(re.escape(wrong), correct, text, flags=re.IGNORECASE)
    return text


def main():
    parser = argparse.ArgumentParser(description="Export manifest to train/val JSONL")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--val-ratio", type=float, default=0.15,
                        help="Fraction of data for validation (default: 0.15)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for shuffle (default: 42)")
    args = parser.parse_args()

    manifest_path = args.data_dir / "manifest.jsonl"
    if not manifest_path.exists():
        sys.exit(f"manifest.jsonl not found: {manifest_path}")

    entries = load_manifest(manifest_path)
    vocab = load_vocab_overrides(args.data_dir)
    if vocab:
        print(f"Loaded {len(vocab)} vocab overrides")

    # Filter and build export records
    records = []
    skipped = {"no_text": 0, "no_audio": 0}

    for entry in entries:
        text = get_final_text(entry)
        if not text:
            skipped["no_text"] += 1
            continue

        audio_path = args.data_dir / entry["audio"]
        if not audio_path.exists():
            skipped["no_audio"] += 1
            print(f"  WARNING: audio not found: {audio_path}")
            continue

        if vocab:
            text = apply_vocab(text, vocab)

        records.append({
            "audio": str(audio_path.resolve()),
            "transcription": text,
        })

    if not records:
        sys.exit("No records to export.")

    # Shuffle and split
    random.seed(args.seed)
    random.shuffle(records)

    n_val = max(1, int(len(records) * args.val_ratio))
    val_records = records[:n_val]
    train_records = records[n_val:]

    # Write output
    out_dir = args.data_dir / "dataset"
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, recs in [("train", train_records), ("val", val_records)]:
        path = out_dir / f"{name}.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\nExported {len(records)} records:")
    print(f"  train: {len(train_records)} → {out_dir / 'train.jsonl'}")
    print(f"  val:   {len(val_records)} → {out_dir / 'val.jsonl'}")
    if skipped["no_text"]:
        print(f"  skipped (no text): {skipped['no_text']}")
    if skipped["no_audio"]:
        print(f"  skipped (no audio): {skipped['no_audio']}")


if __name__ == "__main__":
    main()
