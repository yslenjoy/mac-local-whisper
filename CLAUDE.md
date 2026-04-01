# whisper-voice-input

macOS 语音输入工具，按住 Option 键录音，松开自动转写粘贴。

## 重要约定

**README 双语同步**：中文版在 `README.md`（主），英文版在 `README_en.md`。修改任意一处功能、配置、安装步骤时，必须同时更新两个文件，保持内容一致。

## 项目结构

- `voice_input.py` — 主程序，所有注释必须用英文
- `config.yaml` — 用户配置文件（backend / model / language / trigger_key / initial_prompt）
- `README.md` — 中文主文档；`README_en.md` — 英文版，两者必须同步
- `FUTURE.md` — bug 记录和待办事项，完成后打勾并注明日期

## 当前配置

- Backend：mlx-whisper（Apple Silicon）
- 默认模型：large-v3-turbo
- 触发键：左 Option (⌥)
- 转写在主线程执行（通过 queue），避免 daemon thread segfault
- 启动时 warm-up 推理，确保首次转写无延迟
- UI 语言随 `language` 配置切换（zh 输出中文日志，其他输出英文）
- `initial_prompt` 在 config.yaml 配置，支持中英混合场景
