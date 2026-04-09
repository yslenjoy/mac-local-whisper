#!/usr/bin/env python3
"""
Human review for manifest.jsonl entries.

Usage:
    python3 finetune/review.py                    # review all mismatch entries
    python3 finetune/review.py --status corrected # spot-check corrected entries
    python3 finetune/review.py --data-dir ~/path/to/data

Keys during review:
    a  — accept api text  (final_text = api text, review = "accepted")
    r  — reject api text  (final_text = local_text, review = "rejected")
    e  — edit manually    (type your correction, review = "edited")
    s  — skip this entry
    q  — quit and save

After review, use export.py to produce (audio, final_text) training pairs.
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import readline  # enables arrow-key navigation and backspace in input()
except ImportError:
    pass

DEFAULT_DATA_DIR = Path.home() / "Documents/Developer/whisper-finetune-data"

# ── ANSI colours ──────────────────────────────────────────────────────────────

_RED   = "\033[31m"
_GREEN = "\033[32m"
_CYAN  = "\033[36m"
_BOLD  = "\033[1m"
_DIM   = "\033[2m"
_RESET = "\033[0m"

def _c(text, *codes): return "".join(codes) + text + _RESET
def bold(t): return _c(t, _BOLD)
def dim(t):  return _c(t, _DIM)
def red(t):  return _c(t, _RED)
def green(t): return _c(t, _GREEN)
def cyan(t): return _c(t, _CYAN)


# ── Diff highlight ────────────────────────────────────────────────────────────

def _char_diff(a: str, b: str):
    """Return (a_highlighted, b_highlighted) with differing chars marked."""
    import difflib
    # word-level diff for readability
    a_words = a.split()
    b_words = b.split()
    matcher = difflib.SequenceMatcher(None, a_words, b_words)
    a_parts, b_parts = [], []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        a_chunk = " ".join(a_words[i1:i2])
        b_chunk = " ".join(b_words[j1:j2])
        if tag == "equal":
            a_parts.append(a_chunk)
            b_parts.append(b_chunk)
        elif tag == "replace":
            a_parts.append(red(a_chunk) if a_chunk else "")
            b_parts.append(green(b_chunk) if b_chunk else "")
        elif tag == "delete":
            a_parts.append(red(a_chunk))
        elif tag == "insert":
            b_parts.append(green(b_chunk))
    return " ".join(p for p in a_parts if p), " ".join(p for p in b_parts if p)


# ── Manifest I/O ──────────────────────────────────────────────────────────────

def load_manifest(path: Path) -> list[dict]:
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def save_manifest(path: Path, entries: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── Review loop ───────────────────────────────────────────────────────────────

def review_entry(entry: dict, idx: int, total: int) -> str | None:
    """Show one entry and return the user's key, or None to quit."""
    print()
    print("─" * 60)
    ts = entry.get("timestamp", "")[:19]
    dur = entry.get("duration_s", 0)
    status = entry.get("status", "")
    prev_review = entry.get("review", "")
    print(bold(f"[{idx}/{total}]") + dim(f"  {ts}  {dur:.1f}s  status={status}" +
          (f"  prev={prev_review}" if prev_review else "")))
    print()

    local = entry.get("local_text", "").strip()
    api   = entry.get("text", "").strip()

    local_hi, api_hi = _char_diff(local, api)

    print(f"  {_c('local', _BOLD, _RED)}  : {local_hi or dim('(empty)')}")
    print(f"  {_c('api  ', _BOLD, _GREEN)}: {api_hi   or dim('(empty)')}")

    if not api:
        print(dim("  (no api text — use 'r' to keep local, or 'e' to edit)"))

    print()
    prompt = f"  [{cyan('a')}]ccept-api  [{cyan('r')}]eject-api  [{cyan('e')}]dit  [{cyan('s')}]kip  [{cyan('q')}]uit : "
    try:
        key = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return "q"
    return key


def do_edit(entry: dict):
    """Let user type a manual correction. Empty Enter = cancel."""
    local = entry.get("local_text", "").strip()
    api   = entry.get("text", "").strip()
    print(f"  local : {local}")
    print(f"  api   : {api}")
    print(dim("  (Enter empty to cancel)"))
    try:
        correction = input("  correction> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if not correction:
        print(dim("  (cancelled)"))
        return
    try:
        confirm = input(f"  save {cyan(repr(correction))} ? [y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if confirm == "y":
        entry["final_text"] = correction
        entry["review"] = "edited"
        print(green("  saved (edited)"))
    else:
        print(dim("  (cancelled)"))


def main():
    parser = argparse.ArgumentParser(description="Human review for manifest.jsonl")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--status", default="mismatch",
                        help="Which entries to review: mismatch, corrected, raw, all "
                             "(default: mismatch)")
    args = parser.parse_args()

    manifest_path = args.data_dir / "manifest.jsonl"
    if not manifest_path.exists():
        sys.exit(f"manifest.jsonl not found: {manifest_path}")

    entries = load_manifest(manifest_path)

    if args.status == "all":
        candidates = list(range(len(entries)))
    else:
        candidates = [
            i for i, e in enumerate(entries)
            if e.get("status") == args.status
        ]

    # Un-reviewed first; already reviewed at end
    candidates.sort(key=lambda i: (entries[i].get("review") is not None))

    total = len(candidates)
    if total == 0:
        print(f"No entries with status='{args.status}'.")
        return

    reviewed_this_run = 0
    already_reviewed  = sum(1 for i in candidates if entries[i].get("review"))
    print(f"\n{bold('manifest:')} {len(entries)} total, "
          f"{total} with status={args.status} "
          f"({already_reviewed} already reviewed, {total - already_reviewed} pending)")
    print(dim("  Tip: 'e' to manually correct, 'r' to keep local Whisper output\n"))

    for order, idx in enumerate(candidates, 1):
        entry = entries[idx]
        key = review_entry(entry, order, total)

        if key == "q":
            break
        elif key == "a":
            api_text = entry.get("text", "").strip()
            if api_text:
                entry["final_text"] = api_text
                entry["review"] = "accepted"
                reviewed_this_run += 1
                print(green("  saved (accepted api)"))
            else:
                print(red("  no api text — use 'e' to edit or 'r' to keep local"))
        elif key == "r":
            entry["final_text"] = entry.get("local_text", "").strip()
            entry["review"] = "rejected"
            reviewed_this_run += 1
            print(green("  saved (rejected — using local)"))
        elif key == "e":
            before = entry.get("review")
            do_edit(entry)
            if entry.get("review") != before:
                reviewed_this_run += 1
        elif key == "s":
            print(dim("  skipped"))
        else:
            print(dim(f"  unknown key '{key}' — skipped"))

        # Save after every decision so progress isn't lost on crash
        save_manifest(manifest_path, entries)

    print()
    print(f"Done. Reviewed {reviewed_this_run} entries this run.")
    total_reviewed = sum(1 for e in entries if e.get("review"))
    total_mismatch = sum(1 for e in entries if e.get("status") == "mismatch")
    print(f"Overall: {total_reviewed}/{total_mismatch} mismatch entries reviewed.")


if __name__ == "__main__":
    main()
