# Whisper 语音输入

[English](README.md) | **中文**

按住**左 Option (⌥)** 键录音，松开自动转写并粘贴到当前光标位置。基于 mlx-whisper，针对 Apple Silicon 优化。

## 安装

```bash
pip install mlx-whisper sounddevice pyperclip pynput numpy
```

首次运行时会自动从 HuggingFace 下载模型（默认 `large-v3`），之后缓存本地。

## 使用

```bash
python voice_input.py
```

1. 按住**左 Option (⌥)** — 开始录音
2. 松开 — 自动转写，结果粘贴到光标处

## 权限配置（必须）

**系统设置 → 隐私与安全性**：

- **辅助功能** — 用于模拟 Cmd+V 粘贴
- **麦克风** — 用于录音

将你使用的终端（Terminal / iTerm2）添加到两个列表中。

## 配置项

编辑 `voice_input.py` 顶部：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `BACKEND` | `"mlx"` | `"mlx"`（Apple Silicon）或 `"whisper"`（CPU） |
| `MODEL_NAME` | `"large-v3"` | 模型大小，越大越准，推荐 `large-v3` |
| `LANGUAGE` | `"zh"` | `"zh"` 中文，`None` 自动检测 |
| `TRIGGER_KEY` | `"alt_l"` | 触发键，默认左 Option |
