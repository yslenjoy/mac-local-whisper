记录已知 bug、待办功能和设计方向。完成的条目移至「已完成」并保留原优先级标注。

---

# P0

- [ ] 架构：post-processing 规则（标点替换、末尾处理等）硬编码在主流程里，应拆到独立模块/配置，和 pipeline 解耦，方便扩展自定义规则

# P1

# P2

# 代排期

- [ ] 流式输出：mlx-whisper 无 decoder hook，无法逐 token 输出；需换 faster-whisper（有 segment generator）但会失去 Apple Silicon 加速；现阶段性价比低，暂缓

---

# 已完成

- [x] P0 · 尾字符乱码（2026-04-01）：regex 过滤不可打印字符及连续重复的非正常符号
- [x] P0 · 句间标点（2026-04-01）：末尾句号替换为空格，连续录音粘贴后句子之间有自然间隔
- [x] P0 · 标点（2026-04-01）：末尾去句号，英文标点全部替换为中文全角
- [x] P0 · 稳定性 segfault（2026-04-01）：转写移至主线程通过 queue 执行，避免 daemon thread 调用 torch/C 扩展
- [x] P1 · 改成 mlx-whisper（2026-04-01）：BACKEND=mlx，MODEL_NAME=large-v3-turbo，补 initial_prompt
- [x] P1 · 长句识别不准（2026-04-01）：模型 medium → large-v3-turbo
