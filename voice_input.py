#!/usr/bin/env python3
"""
Whisper voice input for macOS — hold Option (⌥) to record,
release to transcribe and paste at the cursor.

Requires permissions in System Settings → Privacy & Security:
  - Accessibility (to simulate Cmd+V paste)
  - Microphone (to record audio)
"""

import sys
import re
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

BACKEND        = _cfg["backend"]
MODEL_NAME     = _cfg["model_name"]
LANGUAGE       = _cfg["language"]
SAMPLE_RATE    = _cfg["sample_rate"]
TRIGGER_KEY    = _cfg["trigger_key"]
INITIAL_PROMPT = _cfg.get("initial_prompt", "")
# ─────────────────────────────────────────────────────────────────

# ── UI strings (language-aware) ───────────────────────────────────
_zh = LANGUAGE == "zh"

def _msg(zh_text, en_text):
    return zh_text if _zh else en_text

# ── Load model ────────────────────────────────────────────────────
print(_msg(f"[*] 正在加载 {BACKEND}/{MODEL_NAME} 模型...",
           f"[*] Loading {BACKEND}/{MODEL_NAME} model..."))

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
        print(_msg(f"[!] 模型 '{MLX_REPO}' 未缓存。",
                   f"[!] Model '{MLX_REPO}' is not cached locally."))
        _ans = input(_msg("    现在下载？可能需要几分钟。[y/N] ",
                          "    Download now? This may take a few minutes. [y/N] ")).strip().lower()
        if _ans != "y":
            print(_msg("[*] 已取消。", "[*] Aborted."))
            sys.exit(0)
        print(_msg(f"[*] 正在下载 {MLX_REPO}...", f"[*] Downloading {MLX_REPO}..."))
        snapshot_download(MLX_REPO)
        print(_msg("[*] 下载完成。", "[*] Download complete."))

    transcribe_fn = lambda audio: mlx_whisper.transcribe(
        audio, path_or_hf_repo=MLX_REPO, language=LANGUAGE,
        initial_prompt=INITIAL_PROMPT
    )

    # warm up: force model weights to load now so first real transcription is instant
    transcribe_fn(np.zeros(SAMPLE_RATE, dtype=np.float32))
    print(_msg(f"[*] 模型加载完成（{MLX_REPO}）", f"[*] MLX model ready ({MLX_REPO})"))
else:
    import whisper
    _model = whisper.load_model(MODEL_NAME)
    transcribe_fn = lambda audio: _model.transcribe(
        audio, language=LANGUAGE, fp16=False, without_timestamps=True,
        initial_prompt=INITIAL_PROMPT
    )
    print(_msg(f"[*] 模型加载完成（Whisper {MODEL_NAME}）", f"[*] Whisper {MODEL_NAME} ready"))

_key_label = {"alt_l": "左 Option (⌥)", "alt_r": "右 Option (⌥)"}.get(TRIGGER_KEY, TRIGGER_KEY) if _zh else \
             {"alt_l": "Left Option (⌥)", "alt_r": "Right Option (⌥)"}.get(TRIGGER_KEY, TRIGGER_KEY)
print(_msg(f"\n✓ 准备就绪 — 按住{_key_label}开始录音，松开转写并粘贴。Ctrl+C 退出。\n",
           f"\n✓ Ready — hold {_key_label} to record, release to transcribe. Ctrl+C to quit.\n"))

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
    # strip trailing hallucinated garbage (non-printable / repeated non-CJK symbols)
    text = re.sub(r'[\x00-\x08\x0b-\x1f\x7f-\x9f]+', '', text)
    text = re.sub(r'([^\w\u4e00-\u9fff ])\1{3,}', '', text).strip()

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

    text = text.rstrip("。") + " "

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
