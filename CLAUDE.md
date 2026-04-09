# whisper-voice-input

macOS 语音输入工具，按住 Option 键录音，松开自动转写粘贴。

## 重要约定

**README 双语同步**：中文版在 `README.md`（主），英文版在 `README_en.md`。修改任意一处功能、配置、安装步骤时，必须同时更新两个文件，保持内容一致。

## 分支规则

- **main**：核心转写流程（voice_input.py 转写逻辑、config.yaml 转写部分、README）
- **finetune**：微调数据管道（finetune/ 目录、config.yaml 的 finetune block、voice_input.py 里的 finetune hook）

## 项目结构

- `voice_input.py` — 主程序，所有注释必须用英文
- `config.yaml` — 用户配置文件（backend / model / language / trigger_key / initial_prompt）
- `README.md` — 中文主文档；`README_en.md` — 英文版，两者必须同步
- `FUTURE.md` — bug 记录和待办事项；完成后移至「已完成」并保留原优先级标注（如 `P0 ·`），注明日期

## 微调数据标注流程

**触发时机**：跑完 `python3 finetune/auto_correct.py` 之后，有新的 `status=mismatch` 条目时。

流程：
1. `auto_correct.py` — raw → corrected / mismatch
2. **Claude Code 批量修正 mismatch**（见下方 prompt）
3. `export.py` — 生成训练格式

**mismatch 批量修正 prompt**（有新 mismatch 时执行）：

> 读 `~/Documents/Developer/whisper-finetune-data/manifest.jsonl` 里所有 `status=mismatch` 且没有 `review` 字段的条目，根据 `local_text` 和 `api_text` 推断最准确的转写，写回 `final_text`，`review` 标 `"ai"`。背景：普通话+英文混合语音转写，说话人是程序员，常见词汇：fine-tune、type4me、火山引擎、豆包、main 分支、finetune 分支、repo、Claude Code 等。两个版本都可能有错，优先修正专有名词和重复字。

---

## 当前配置

- Backend：mlx-whisper（Apple Silicon）
- 默认模型：large-v3-turbo
- 触发键：左 Option (⌥)
- 转写在主线程执行（通过 queue），避免 daemon thread segfault
- 启动时 warm-up 推理，确保首次转写无延迟
- UI 语言随 `language` 配置切换（zh 输出中文日志，其他输出英文）
- `initial_prompt` 在 config.yaml 配置，支持中英混合场景
