# Whisper 语音输入

按住 **Option(⌥)** 键录音，松开自动识别并粘贴到当前光标位置。

## 首次使用

```bash
# 安装依赖
/Library/Developer/CommandLineTools/usr/bin/python3 -m pip install sounddevice pyperclip pynput numpy scipy

# 运行
/Library/Developer/CommandLineTools/usr/bin/python3 ~/Documents/Developer/whisper-voice-input/voice_input.py
```

## 权限（必须）

macOS 需要授权两项权限（首次运行会弹出提示）：
- **辅助功能**：用于模拟键盘粘贴
- **麦克风**：用于录音

在「系统设置 → 隐私与安全性」中手动添加「终端」。

## 配置

编辑 `voice_input.py` 顶部：
- `MODEL_NAME`：模型大小（tiny/base/small/medium/large）
- `LANGUAGE`：`"zh"` 中文，`None` 自动检测
- `TRIGGER_KEY`：触发按键，默认 Option 键

## 注意

- CPU 运行 medium 模型，3秒音频约需 5-10 秒转写
- 想更快可换 `small` 模型或安装 `faster-whisper`
