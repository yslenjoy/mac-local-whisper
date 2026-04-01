#!/Library/Developer/CommandLineTools/usr/bin/python3
"""
Whisper 语音输入工具
- 按住 Option(⌥) 键录音，松开后自动转写并粘贴到当前光标位置
- 支持 openai-whisper（CPU/MPS）和 mlx-whisper（Apple Silicon 推荐）

权限要求（首次运行会弹出提示）：
  系统设置 → 隐私与安全性 → 辅助功能 → 添加「终端」
  系统设置 → 隐私与安全性 → 麦克风 → 添加「终端」
"""

import sys
import queue
import threading
import time
import subprocess

import numpy as np
import sounddevice as sd

# ── 配置 ──────────────────────────────────────────────────────────
BACKEND     = "mlx"            # "whisper" 或 "mlx"（Apple Silicon 更快）
MODEL_NAME  = "large-v3"       # tiny / base / small / medium / large / large-v2 / large-v3
LANGUAGE    = "zh"             # "zh" 中文，None 自动检测
SAMPLE_RATE = 16000            # Whisper 固定 16kHz
TRIGGER_KEY = "alt_l"          # 触发键："alt_l"=左Option，"alt_r"=右Option，"ctrl"，"f5" 等
# ─────────────────────────────────────────────────────────────────

# ── 加载模型 ──────────────────────────────────────────────────────
print(f"[*] 加载 {BACKEND}/{MODEL_NAME} 模型，请稍候...")

if BACKEND == "mlx":
    import mlx_whisper
    MLX_REPO = f"mlx-community/whisper-{MODEL_NAME}-mlx"
    transcribe_fn = lambda audio: mlx_whisper.transcribe(
        audio, path_or_hf_repo=MLX_REPO, language=LANGUAGE,
        initial_prompt="以下是普通话的简体中文转录。"
    )
    print(f"[*] MLX 模型加载完成（{MLX_REPO}）")
else:
    import whisper
    _model = whisper.load_model(MODEL_NAME)
    transcribe_fn = lambda audio: _model.transcribe(
        audio, language=LANGUAGE, fp16=False, without_timestamps=True,
        initial_prompt="以下是普通话的简体中文转录。"
    )
    print(f"[*] Whisper {MODEL_NAME} 加载完成")

print(f"[*] 按住左 Option(⌥) 键开始录音，松开转写并粘贴。Ctrl+C 退出。\n")

# ── 运行时状态 ────────────────────────────────────────────────────
import pyperclip
from pynput import keyboard
from pynput.keyboard import Controller, Key

kb_ctrl        = Controller()
is_recording   = False
audio_chunks   = []
stream         = None
lock           = threading.Lock()
target_app     = None   # 按下热键时记录的 frontmost app
work_queue     = queue.Queue()  # 转写任务传回主线程，避免 daemon thread 中调用 torch 导致 segfault

# 解析触发键
KEY_MAP = {"alt": Key.alt, "alt_l": Key.alt_l, "alt_r": Key.alt_r,
           "ctrl": Key.ctrl, "cmd": Key.cmd,
           "shift": Key.shift, "f5": Key.f5, "f6": Key.f6}
_trigger = KEY_MAP.get(TRIGGER_KEY.lower(), Key.alt)


def get_frontmost_app():
    """获取当前 frontmost app 名称（用于转写后切回）"""
    r = subprocess.run(
        ['osascript', '-e',
         'tell application "System Events" to get name of first application process whose frontmost is true'],
        capture_output=True, text=True
    )
    return r.stdout.strip()


def paste_via_osascript(app_name, text):
    """按进程名激活 app，再用 pynput 发送 Cmd+V"""
    # 只用 osascript 激活窗口（不发按键，无需额外权限）
    subprocess.run(['osascript', '-e', f'''
        tell application "System Events"
            set frontmost of process "{app_name}" to true
        end tell
    '''])
    time.sleep(0.2)
    # 用 pynput Controller 发 Cmd+V（Terminal 辅助功能权限）
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

    # 静音检测
    if np.sqrt(np.mean(audio ** 2)) < 0.001:
        print("  (静音，已跳过)    ")
        return

    # 把 (audio, app) 交给主线程转写，避免在 daemon thread 调用 torch/C 扩展导致 segfault
    work_queue.put((audio, target_app))


# ── 热键监听 ──────────────────────────────────────────────────────
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
    """在主线程执行 whisper 转写，避免 daemon thread 中的 segfault"""
    result = transcribe_fn(audio)
    text = result["text"].strip()

    if not text:
        print("  (无识别结果)      ")
        return

    # 英文标点 → 中文全角标点
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

    # 末尾去掉句号（包括英文句号已被上面逻辑处理前的中文句号）
    text = text.rstrip("。")

    ts = time.strftime("%H:%M:%S")
    print(f"\n✓ [{app}] {ts}\n{text}")

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
    print("\n[*] 退出")
    listener.stop()
    sys.exit(0)
