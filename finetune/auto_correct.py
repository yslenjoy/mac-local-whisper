#!/usr/bin/env python3
"""
Batch-correct manifest.jsonl entries using Volcengine ASR API.

Usage:
    python3 finetune/auto_correct.py
    python3 finetune/auto_correct.py --data-dir ~/path/to/data
    python3 finetune/auto_correct.py --limit 10 --dry-run

For each 'raw' entry: calls Volcengine, compares with local_text,
marks status as 'corrected' (consistent) or 'mismatch' (differs).

Credentials: ~/Downloads/credentials/volcengine-speech.json
  {"app_id": "...", "access_token": "..."}
"""

import argparse
import asyncio
import gzip
import json
import re
import struct
import subprocess
import sys
import uuid
from pathlib import Path

import websockets

# ── Constants ────────────────────────────────────────────────────────────────

VOLC_ENDPOINT = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
RESOURCE_ID = "volc.seedasr.sauc.duration"
SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2
CHUNK_DURATION_MS = 200
CHUNK_SIZE = SAMPLE_RATE * BYTES_PER_SAMPLE * CHUNK_DURATION_MS // 1000  # 6400 bytes

CREDENTIALS_PATH = Path.home() / "Downloads/credentials/volcengine-speech.json"
DEFAULT_DATA_DIR = Path.home() / "Documents/Developer/whisper-finetune-data"

# Similarity threshold: >= this → 'corrected', else 'mismatch'
SIMILARITY_THRESHOLD = 0.85


# ── Volcengine binary protocol (from type4me/scripts/test_asr.py) ─────────────

def _encode_header(msg_type: int, flags: int, serial: int, compress: int) -> bytes:
    b0 = (0x01 << 4) | 0x01
    b1 = (msg_type << 4) | (flags & 0x0F)
    b2 = (serial << 4) | (compress & 0x0F)
    return bytes([b0, b1, b2, 0x00])


def _encode_message(msg_type: int, flags: int, serial: int, compress: int, payload: bytes) -> bytes:
    header = _encode_header(msg_type, flags, serial, compress)
    return header + struct.pack(">I", len(payload)) + payload


def _encode_audio(pcm_data: bytes, is_last: bool) -> bytes:
    flags = 0b0010 if is_last else 0b0000
    return _encode_message(0b0010, flags, 0b0000, 0b0000, pcm_data)


def _decode_response(data: bytes) -> dict | None:
    if len(data) < 4:
        return None
    b1, b2 = data[1], data[2]
    msg_type = (b1 >> 4) & 0x0F
    flags = b1 & 0x0F
    serial = (b2 >> 4) & 0x0F
    compress = b2 & 0x0F
    header_size = (data[0] & 0x0F) * 4
    offset = header_size
    if flags in (0b0001, 0b0011):
        offset += 4
    if len(data) < offset + 4:
        return None
    payload_size = struct.unpack(">I", data[offset:offset + 4])[0]
    offset += 4
    payload = data[offset:offset + payload_size]
    if msg_type == 0x0F:
        if compress == 0b0001:
            try:
                payload = gzip.decompress(payload)
            except Exception:
                pass
        if serial == 0b0001:
            try:
                return {"_error": True, **json.loads(payload)}
            except Exception:
                pass
        return {"_error": True}
    if compress == 0b0001:
        payload = gzip.decompress(payload)
    if serial == 0b0001 and payload:
        return json.loads(payload)
    return None


# ── Audio conversion ──────────────────────────────────────────────────────────

def convert_to_pcm(audio_path: Path) -> bytes:
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(audio_path),
         "-ar", str(SAMPLE_RATE), "-ac", "1",
         "-f", "s16le", "-acodec", "pcm_s16le", "pipe:1"],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg: {result.stderr.decode()[:200]}")
    return result.stdout


# ── Volcengine ASR ────────────────────────────────────────────────────────────

async def recognize(pcm_data: bytes, app_id: str, access_token: str) -> str:
    uid = f"autocorrect-{uuid.uuid4().hex[:8]}"
    headers = {
        "X-Api-App-Key": app_id,
        "X-Api-Access-Key": access_token,
        "X-Api-Resource-Id": RESOURCE_ID,
        "X-Api-Connect-Id": str(uuid.uuid4()),
    }
    payload = json.dumps({
        "user": {"uid": uid},
        "audio": {"format": "pcm", "codec": "raw", "rate": SAMPLE_RATE, "bits": 16, "channel": 1},
        "request": {
            "model_name": "bigmodel",
            "enable_punc": True,
            "enable_ddc": True,
            "enable_nonstream": True,
            "show_utterances": True,
            "result_type": "full",
            "end_window_size": 3000,
            "force_to_speech_time": 1000,
        },
    }).encode()

    req_msg = _encode_message(0b0001, 0b0000, 0b0001, 0b0000, payload)

    async with websockets.connect(VOLC_ENDPOINT, additional_headers=headers) as ws:
        await ws.send(req_msg)

        offset = 0
        while offset < len(pcm_data):
            chunk = pcm_data[offset:offset + CHUNK_SIZE]
            is_last = (offset + CHUNK_SIZE >= len(pcm_data))
            await ws.send(_encode_audio(chunk, is_last))
            offset += CHUNK_SIZE
            if not is_last:
                await asyncio.sleep(CHUNK_DURATION_MS / 1000 * 0.5)

        final_text = ""
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=15)
                if not isinstance(msg, bytes):
                    continue
                parsed = _decode_response(msg)
                if parsed is None:
                    continue
                if parsed.get("_error"):
                    break
                result = parsed.get("result", parsed)
                utts = result.get("utterances", [])
                definite = [u["text"] for u in utts if u.get("definite")]
                if definite:
                    final_text = "".join(definite)
                elif result.get("text"):
                    final_text = result["text"]
        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
            pass

    return final_text.strip()


# ── Similarity ────────────────────────────────────────────────────────────────

_PUNCT = re.compile(r'[\s\u3000-\u303f\uff00-\uffef\u2000-\u206f.,!?;:，。！？；：、…—\u201c\u201d\u2018\u2019「」【】《》\'"‐-]+')

def _normalize(text: str) -> str:
    """Strip punctuation and spaces for comparison."""
    return _PUNCT.sub("", text).lower()


def _similarity(a: str, b: str) -> float:
    """Character-level similarity ratio."""
    a, b = _normalize(a), _normalize(b)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    # LCS-based ratio (same as difflib.SequenceMatcher idea, simple version)
    longer = max(len(a), len(b))
    matches = sum(ca == cb for ca, cb in zip(a, b))
    # Penalize length difference
    length_penalty = abs(len(a) - len(b)) / longer
    return max(0.0, matches / longer - length_penalty * 0.5)


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


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Batch-correct manifest.jsonl via Volcengine ASR")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                        help=f"Directory containing manifest.jsonl (default: {DEFAULT_DATA_DIR})")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max number of raw entries to process this run")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would happen without modifying manifest")
    args = parser.parse_args()

    # Load credentials
    if not CREDENTIALS_PATH.exists():
        sys.exit(f"Credentials not found: {CREDENTIALS_PATH}")
    creds = json.loads(CREDENTIALS_PATH.read_text())
    app_id = creds.get("app_id", "")
    access_token = creds.get("access_token", "")
    if not app_id or not access_token:
        sys.exit("credentials.json missing app_id or access_token")

    # Load manifest
    manifest_path = args.data_dir / "manifest.jsonl"
    if not manifest_path.exists():
        sys.exit(f"manifest.jsonl not found: {manifest_path}")

    entries = load_manifest(manifest_path)
    raw_entries = [e for e in entries if e.get("status") == "raw" and not e.get("text")]

    if not raw_entries:
        print("No raw entries to process.")
        return

    to_process = raw_entries[:args.limit] if args.limit else raw_entries
    print(f"manifest: {len(entries)} total, {len(raw_entries)} raw+empty → processing {len(to_process)}")
    if args.dry_run:
        print("[dry-run] no changes will be written\n")

    # Build index for in-place update
    entry_index = {id(e): i for i, e in enumerate(entries)}

    n_corrected = n_mismatch = n_error = 0
    SAVE_EVERY = 5

    for i, entry in enumerate(to_process, 1):
        audio_path = args.data_dir / entry["audio"]
        ts = entry.get("timestamp", "")[:19]
        print(f"[{i}/{len(to_process)}] {entry['audio']}  ({ts})")
        print(f"  local : {entry['local_text']}")

        try:
            pcm = convert_to_pcm(audio_path)
            api_text = await recognize(pcm, app_id, access_token)
        except Exception as e:
            print(f"  ERROR : {e}\n")
            n_error += 1
            continue

        sim = _similarity(entry["local_text"], api_text)
        status = "corrected" if sim >= SIMILARITY_THRESHOLD else "mismatch"

        print(f"  api   : {api_text}")
        print(f"  sim={sim:.2f}  →  {status}\n")

        if not args.dry_run:
            idx = entry_index[id(entry)]
            entries[idx]["text"] = api_text
            entries[idx]["status"] = status
            if i % SAVE_EVERY == 0:
                save_manifest(manifest_path, entries)
                print(f"  [saved {i} entries]\n")

        if status == "corrected":
            n_corrected += 1
        else:
            n_mismatch += 1

    # Final write
    if not args.dry_run:
        save_manifest(manifest_path, entries)

    print(f"Done. corrected={n_corrected}  mismatch={n_mismatch}  error={n_error}")
    if n_mismatch:
        print(f"Run review.py to inspect mismatch entries.")


if __name__ == "__main__":
    asyncio.run(main())
