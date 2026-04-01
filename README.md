# Whisper Voice Input

**English** | [中文](README_zh.md)

Hold **Option (⌥)** to record, release to transcribe and paste at the cursor — powered by [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) on Apple Silicon.

## Requirements

- macOS with Apple Silicon (M1/M2/M3)
- Python 3.9+

## Installation

```bash
pip install mlx-whisper sounddevice pyperclip pynput numpy
```

The model (`large-v3` by default) is downloaded automatically from HuggingFace on first run.

## Usage

```bash
python voice_input.py
```

1. Hold **Left Option (⌥)** — recording starts
2. Release — transcription begins, result is pasted at your cursor

## Permissions (required)

In **System Settings → Privacy & Security**:

- **Accessibility** — needed to simulate Cmd+V paste
- **Microphone** — needed to record audio

Add your terminal app (Terminal / iTerm2) to both lists.

## Configuration

Edit the top of `voice_input.py`:

| Variable | Default | Description |
|---|---|---|
| `BACKEND` | `"mlx"` | `"mlx"` (Apple Silicon) or `"whisper"` (CPU) |
| `MODEL_NAME` | `"large-v3"` | `tiny` / `base` / `small` / `medium` / `large` / `large-v3` |
| `LANGUAGE` | `"zh"` | `"zh"` for Mandarin, `None` for auto-detect |
| `TRIGGER_KEY` | `"alt_l"` | `"alt_l"` / `"alt_r"` / `"ctrl"` / `"f5"` etc. |
