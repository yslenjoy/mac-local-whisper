# Whisper 语音输入

[English](README.md) | **中文**

按住**左 Option (⌥)** 键录音，松开自动转写并粘贴到当前光标位置。基于 mlx-whisper，针对 Apple Silicon 优化。

> **仅支持 Apple Silicon（M1/M2/M3/M4）**，不支持 Intel 芯片的 Mac。

## 安装

```bash
git clone https://github.com/yslenjoy/whisper-voice-input.git
cd whisper-voice-input
pip3 install mlx-whisper sounddevice pyperclip pynput numpy pyyaml
```

首次运行时会自动从 HuggingFace 下载模型（默认 `large-v3`），之后缓存本地。

## 使用

```bash
python3 voice_input.py
```

1. 按住**左 Option (⌥)** — 开始录音
2. 松开 — 自动转写，结果粘贴到光标处

## 权限配置（必须）

脚本需要两项权限，均在**系统设置 → 隐私与安全性**下配置。注意：不是左侧边栏顶部的「辅助功能」菜单，要往下滚动找到「隐私与安全性」。

### 麦克风

1. 系统设置 → 隐私与安全性 → **麦克风**
2. 点击 **+**，找到 `/Applications/Utilities/Terminal.app`（或你使用的终端）并添加
3. 确认旁边的开关已**打开**

### 辅助功能

1. 系统设置 → 隐私与安全性 → **辅助功能**
2. 点击 **+**，同样添加你的终端 app
3. 确认开关已**打开**

> 如果开关是灰色无法点击，先点击窗口底部的锁图标解锁再操作。
>
> 授权后需要**重启终端**再运行脚本 —— macOS 不会对已运行的进程生效新权限。

## 配置项

编辑 `voice_input.py` 顶部：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `BACKEND` | `"mlx"` | `"mlx"`（Apple Silicon）或 `"whisper"`（CPU） |
| `MODEL_NAME` | `"large-v3-turbo"` | 见下方模型表格 |
| `LANGUAGE` | `"zh"` | `"zh"` 中文，`None` 自动检测 |
| `TRIGGER_KEY` | `"alt_l"` | 触发键，默认左 Option |

### 模型选择

| 模型 | 速度 | 准确度 | 说明 |
|---|---|---|---|
| `large-v3-turbo` | ★★★★★ | ★★★★☆ | **推荐**。比 large-v3 快 6 倍，准确度接近 large-v2 |
| `large-v3` | ★★☆☆☆ | ★★★★★ | 最准，速度慢 |
| `large-v2` | ★★☆☆☆ | ★★★★☆ | 比 v3 略快 |
| `medium` | ★★★★☆ | ★★★☆☆ | 老设备的折中选择 |
| `small` | ★★★★★ | ★★☆☆☆ | 速度最快，准确度一般 |
