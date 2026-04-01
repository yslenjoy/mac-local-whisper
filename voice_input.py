#!/usr/bin/env python3
"""
Whisper voice input for macOS — hold Option (⌥) to record,
release to transcribe and paste at the cursor.

Requires permissions in System Settings → Privacy & Security:
  - Accessibility (to simulate Cmd+V paste)
  - Microphone (to record audio)
"""

import sys
import json
import queue
import threading
import time
import subprocess
from pathlib import Path

import yaml
import numpy as np
import sounddevice as sd

# ── Load config ───────────────────────────────────────────────────
_cfg_path = Path(__file__).parent / "config.yaml"
with open(_cfg_path) as f:
    _cfg = yaml.safe_load(f)

BACKEND     = _cfg["backend"]
MODEL_NAME  = _cfg["model_name"]
LANGUAGE    = _cfg["language"]
SAMPLE_RATE = _cfg["sample_rate"]
TRIGGER_KEY = _cfg["trigger_key"]
# ─────────────────────────────────────────────────────────────────

# ── Load model ────────────────────────────────────────────────────
print(f"[*] Loading {BACKEND}/{MODEL_NAME} model...")

if BACKEND == "mlx":
    import mlx_whisper
    from huggingface_hub import snapshot_download, try_to_load_from_cache

    # turbo models use a different repo naming convention (no -mlx suffix)
    _MLX_REPOS = {
        "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    }
    MLX_REPO = _MLX_REPOS.get(MODEL_NAME, f"mlx-community/whisper-{MODEL_NAME}-mlx")

    # check cache before proceeding; prompt user if download is required
    _cached = try_to_load_from_cache(MLX_REPO, "config.json")
    if _cached is None:
        print(f"[!] Model '{MLX_REPO}' is not cached locally.")
        _ans = input("    Download now? This may take a few minutes. [y/N] ").strip().lower()
        if _ans != "y":
            print("[*] Aborted.")
            sys.exit(0)
        print(f"[*] Downloading {MLX_REPO}...")
        snapshot_download(MLX_REPO)
        print("[*] Download complete.")

    transcribe_fn = lambda audio: mlx_whisper.transcribe(
        audio, path_or_hf_repo=MLX_REPO, language=LANGUAGE,
        initial_prompt="以下是普通话的简体中文转录。"
    )
    print(f"[*] MLX model ready ({MLX_REPO})")
else:
    import whisper
    _model = whisper.load_model(MODEL_NAME)
    transcribe_fn = lambda audio: _model.transcribe(
        audio, language=LANGUAGE, fp16=False, without_timestamps=True,
        initial_prompt="以下是普通话的简体中文转录。"
    )
    print(f"[*] Whisper {MODEL_NAME} ready")

print(f"[*] Hold Left Option (⌥) to record, release to transcribe. Ctrl+C to quit.\n")

# ── Runtime state ─────────────────────────────────────────────────
import pyperclip
from pynput import keyboard
from pynput.keyboard import Controller, Key

kb_ctrl      = Controller()
is_recording = False
audio_chunks = []
stream       = None
lock         = threading.Lock()
target_app   = None
work_queue   = queue.Queue()  # pass work to main thread to avoid segfault in daemon threads

KEY_MAP = {"alt": Key.alt, "alt_l": Key.alt_l, "alt_r": Key.alt_r,
           "ctrl": Key.ctrl, "cmd": Key.cmd,
           "shift": Key.shift, "f5": Key.f5, "f6": Key.f6}
_trigger = KEY_MAP.get(TRIGGER_KEY.lower(), Key.alt)


def get_frontmost_app():
    """Return the name of the current frontmost application."""
    r = subprocess.run(
        ['osascript', '-e',
         'tell application "System Events" to get name of first application process whose frontmost is true'],
        capture_output=True, text=True
    )
    return r.stdout.strip()


def paste_via_osascript(app_name, text):
    """Bring app to front via osascript, then send Cmd+V via pynput."""
    subprocess.run(['osascript', '-e', f'''
        tell application "System Events"
            set frontmost of process "{app_name}" to true
        end tell
    '''])
    time.sleep(0.2)
    with kb_ctrl.pressed(Key.cmd):
        kb_ctrl.tap("v")


def start_recording():
    global is_recording, audio_chunks, stream, target_app
    with lock:
        if is_recording:
            return
        is_recording = True
        audio_chunks = []
        target_app   = get_frontmost_app()

    print("\n● 录音中...", flush=True)

    def _cb(indata, frames, t, status):
        if is_recording:
            audio_chunks.append(indata.copy())

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1,
        dtype="float32", callback=_cb, blocksize=1024,
    )
    stream.start()


def stop_and_transcribe():
    global is_recording, stream

    with lock:
        if not is_recording:
            return
        is_recording = False

    if stream:
        stream.stop()
        stream.close()
        stream = None

    if not audio_chunks:
        return

    print("◎ 转写中...", flush=True)

    audio = np.concatenate(audio_chunks, axis=0).flatten()

    if np.sqrt(np.mean(audio ** 2)) < 0.001:
        print("  (静音，已跳过)    ")
        return

    # hand off to main thread — calling torch/C extensions from a daemon thread causes segfault
    work_queue.put((audio, target_app))


# ── Hotkey listener ───────────────────────────────────────────────
_pressed = set()

def on_press(key):
    if key == _trigger and key not in _pressed:
        _pressed.add(key)
        threading.Thread(target=start_recording, daemon=True).start()

def on_release(key):
    if key == _trigger and key in _pressed:
        _pressed.discard(key)
        threading.Thread(target=stop_and_transcribe, daemon=True).start()


listener = keyboard.Listener(on_press=on_press, on_release=on_release)
listener.start()


def process_transcription(audio, app):
    """Run whisper transcription on the main thread to avoid daemon-thread segfault."""
    t0 = time.perf_counter()
    result = transcribe_fn(audio)
    elapsed = time.perf_counter() - t0

    text = result["text"].strip()

    if not text:
        print("  (无识别结果)      ")
        return

    # normalize punctuation: English → Chinese full-width
    PUNCT_MAP = {
        ",": "，",
        "?": "？",
        "!": "！",
        ":": "：",
        ";": "；",
        "(": "（",
        ")": "）",
    }
    for en, zh in PUNCT_MAP.items():
        text = text.replace(en, zh)

    text = text.rstrip("。")

    ts = time.strftime("%H:%M:%S")
    print(f"\n✓ [{app}] {ts}\n{text}\n{'─' * 30}\n  ⏱ {elapsed:.1f}s")

    pyperclip.copy(text)
    paste_via_osascript(app, text)


try:
    while True:
        try:
            audio, app = work_queue.get(timeout=0.1)
            process_transcription(audio, app)
        except queue.Empty:
            pass
except KeyboardInterrupt:
    print("\n[*] Exiting")
    listener.stop()
    sys.exit(0)
