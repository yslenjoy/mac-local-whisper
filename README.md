# Whisper Voice Input

**English** | [中文](README_zh.md)

Hold **Option (⌥)** to record, release to transcribe and paste at the cursor — powered by [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) on Apple Silicon.

> **Apple Silicon only (M1/M2/M3/M4).** Intel Macs are not supported.

## Requirements

- macOS with Apple Silicon (M1 or later)
- Python 3.9+

## Installation

```bash
git clone https://github.com/yslenjoy/whisper-voice-input.git
cd whisper-voice-input
pip3 install mlx-whisper sounddevice pyperclip pynput numpy pyyaml
```

The model (`large-v3` by default) is downloaded automatically from HuggingFace on first run.

## Usage

```bash
python3 voice_input.py
```

1. Hold **Left Option (⌥)** — recording starts
2. Release — transcription begins, result is pasted at your cursor

## Permissions (required)

The script needs two permissions under **System Settings → Privacy & Security**. Note: this is **not** the top-level "Accessibility" menu in the sidebar — scroll down to find "Privacy & Security".

### Microphone

1. System Settings → Privacy & Security → **Microphone**
2. Click **+**, navigate to `/Applications/Utilities/Terminal.app` (or your terminal of choice) and add it
3. Make sure the toggle next to it is **on**

### Accessibility

1. System Settings → Privacy & Security → **Accessibility**
2. Click **+**, add your terminal app the same way
3. Make sure the toggle is **on**

> If a toggle is greyed out, click the lock icon at the bottom of the window and authenticate first.
>
> After granting permissions, **restart your terminal** and run the script again — macOS does not apply new permissions to a running process.

## Configuration

Edit the top of `voice_input.py`:

| Variable | Default | Description |
|---|---|---|
| `BACKEND` | `"mlx"` | `"mlx"` (Apple Silicon) or `"whisper"` (CPU) |
| `MODEL_NAME` | `"large-v3-turbo"` | See model table below |
| `LANGUAGE` | `"zh"` | `"zh"` for Mandarin, `None` for auto-detect |
| `TRIGGER_KEY` | `"alt_l"` | `"alt_l"` / `"alt_r"` / `"ctrl"` / `"f5"` etc. |

### Model options

| Model | Speed | Accuracy | Notes |
|---|---|---|---|
| `large-v3-turbo` | ★★★★★ | ★★★★☆ | **Recommended.** 6x faster than large-v3, accuracy on par with large-v2 |
| `large-v3` | ★★☆☆☆ | ★★★★★ | Most accurate, slow |
| `large-v2` | ★★☆☆☆ | ★★★★☆ | Slightly faster than v3 |
| `medium` | ★★★★☆ | ★★★☆☆ | Good balance for older hardware |
| `small` | ★★★★★ | ★★☆☆☆ | Fast, lower accuracy |
