"""Save audio + transcription pairs for fine-tuning data collection."""

import json
import struct
import time
import wave
from pathlib import Path

import numpy as np


def save_sample(audio: np.ndarray, text: str, sample_rate: int, cfg: dict):
    """Save one (audio, text) pair to disk and append to manifest.

    Args:
        audio: float32 numpy array, mono, at sample_rate Hz.
        text: cleaned transcription text from local Whisper.
        sample_rate: audio sample rate (typically 16000).
        cfg: the finetune config block from config.yaml.
    """
    duration_s = len(audio) / sample_rate

    if duration_s < cfg.get("min_duration_s", 0.5):
        return
    if duration_s > cfg.get("max_duration_s", 30):
        return

    out_dir = Path(cfg["output_dir"]).expanduser()
    audio_dir = out_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%d_%H%M%S")
    fmt = cfg.get("audio_format", "wav")
    audio_filename = f"{ts}.{fmt}"
    audio_path = audio_dir / audio_filename

    # avoid overwrite if multiple samples in the same second
    counter = 1
    while audio_path.exists():
        audio_filename = f"{ts}_{counter}.{fmt}"
        audio_path = audio_dir / audio_filename
        counter += 1

    # write WAV using stdlib — no extra dependency
    pcm = (audio * 32767).astype(np.int16)
    with wave.open(str(audio_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())

    record = {
        "audio": f"audio/{audio_filename}",
        "local_text": text,
        "text": "",
        "status": "raw",
        "duration_s": round(duration_s, 2),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    manifest_path = out_dir / "manifest.jsonl"
    with open(manifest_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
