# finetune/ — Whisper 微调数据管道

用日常录音数据微调本地 Whisper 模型，改善中英混合、专有名词识别效果。

---

## 整体流程

```
日常使用 voice_input.py
    │
    ▼
collector.py          ← 每次转写后自动保存音频 + 文本
    │  存到 manifest.jsonl (status: raw)
    ▼
auto_correct.py       ← 批量调火山引擎 ASR API 校正
    │  status: corrected (一致) / mismatch (有差异)
    ▼
mismatch 条目 ──→ Claude Code 批量修正 (review: "ai")
corrected 条目 ──→ 直接用 api_text，无需处理
    │
    ▼
export.py             ← 过滤、分割 train/val，输出 JSONL
    │  whisper-finetune-data/dataset/train.jsonl + val.jsonl
    ▼
train.py              ← LoRA 微调，约 10 分钟 (Mac MPS)
    │  输出: whisper-finetune-data/model-merged/
    ▼
mlx 转换              ← 转成 mlx 格式，接回 voice_input.py
    │  python -m mlx_whisper.convert ...
    ▼
config.yaml 改 model 路径 → 使用微调后的模型
```

---

## 文件说明

### `collector.py`
**作用**：在每次转写成功后，把音频和文本自动保存下来，积累训练数据。

**怎么触发**：不用手动运行。`voice_input.py` 里有一个 hook，松开录音键转写完成后自动调用。

**输出**：
- `audio/YYYYMMDD_HHMMSS.wav` — 原始音频，16kHz mono WAV
- `manifest.jsonl` — 每条追加一行，格式见下方

**manifest.jsonl 字段说明**：
```jsonc
{
  "audio": "audio/20260407_185714.wav",  // 相对路径
  "local_text": "那妈在妈...",            // 本地 Whisper 识别结果（原始，可能有错）
  "text": "",                            // 商业 API 校正结果（auto_correct 后填入）
  "status": "raw",                       // raw / corrected / mismatch
  "duration_s": 13.44,
  "timestamp": "2026-04-07T18:57:14",
  "final_text": "在吗在吗...",           // 最终权威文本（review 后填入，训练用这个）
  "review": "accepted"                   // accepted / rejected / edited / ai
}
```

---

### `auto_correct.py`
**作用**：把 `status: raw` 的条目发给火山引擎豆包 ASR API，对比本地结果，判断是否一致。

**运行**：
```bash
python3 finetune/auto_correct.py
python3 finetune/auto_correct.py --limit 20   # 只处理前 20 条
python3 finetune/auto_correct.py --dry-run    # 只打印不写入
```

**需要**：`~/Downloads/credentials/volcengine-speech.json`，含 `app_id` + `access_token`。

**逻辑**：
1. 读所有 `status: raw` 的条目
2. 把音频发给火山引擎，拿到 `api_text`
3. 对比 `local_text` 和 `api_text`（去标点后字符级相似度）
4. 相似度 ≥ 0.85 → `status: corrected`，`text` = api_text
5. 相似度 < 0.85 → `status: mismatch`，`text` = api_text，需要人工或 AI 确认

---

### `review.py`
**作用**：交互式人工复查 mismatch 条目，决定用哪个版本的文本作为训练数据。

**运行**：
```bash
python3 finetune/review.py                    # 默认复查 mismatch
python3 finetune/review.py --status corrected # 抽查 corrected 条目
```

**操作键**：
- `a` — 接受 api_text（api 对）
- `r` — 拒绝 api，用 local_text（本地 Whisper 对）
- `e` — 手动输入正确文本
- `s` — 跳过
- `q` — 退出并保存

**实际用法**：大多数情况下 mismatch 直接交给 Claude Code 批量处理（见 CLAUDE.md 里的 prompt），`review.py` 作为兜底。

---

### `export.py`
**作用**：从 manifest.jsonl 筛出可用数据，生成训练用的 JSONL 文件。

**运行**：
```bash
python3 finetune/export.py
python3 finetune/export.py --val-ratio 0.2   # 20% 做验证集（默认 15%）
```

**筛选规则**（按优先级）：
1. 有 `final_text` 的条目（经过 review 的）→ 用 `final_text`
2. `status: corrected` 的条目 → 用 `text`（api_text）
3. 其余（raw、无文本）→ 跳过

**输出**：
- `whisper-finetune-data/dataset/train.jsonl`
- `whisper-finetune-data/dataset/val.jsonl`

每行格式：
```json
{"audio": "/abs/path/to/audio.wav", "transcription": "最终文本"}
```

---

### `train.py`
**作用**：用 LoRA 对 Whisper 做参数高效微调。

**什么是 LoRA**：不更新全部参数（太大），而是在特定层旁边加一个小的"旁路矩阵"，只训练这个旁路（约 0.4% 的参数）。训练完再合并回原模型。好处是显存占用小、训练快。

**运行**：
```bash
# 激活训练专用 conda 环境（首次需先创建）
conda activate whisper-ft
# 首次创建：conda create -n whisper-ft python=3.11 -y && pip install -r finetune/requirements-train.txt

# 训练（默认用 whisper-small，Mac 本地约 10 分钟）
HF_ENDPOINT=https://hf-mirror.com python3 finetune/train.py

# 用大模型（需要云 GPU）
HF_ENDPOINT=https://hf-mirror.com python3 finetune/train.py \
  --base-model openai/whisper-large-v3-turbo --epochs 5
```

**参数说明**：
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--base-model` | `openai/whisper-small` | 基础模型（small 适合本地，large-v3-turbo 适合云端）|
| `--epochs` | 10 | 训练轮数 |
| `--batch-size` | 1 | 每批样本数（Mac 内存有限，保持 1）|
| `--lora-rank` | 16 | LoRA 秩，越大拟合能力越强但显存更多 |
| `--data-dir` | `~/Documents/Developer/whisper-finetune-data` | 数据目录 |

**训练过程**：每个 epoch 结束打印 loss（越小越好），同时跑一次 val set 评估。

**输出**：
- `whisper-finetune-data/model/` — 训练 checkpoints（每 epoch 保存）
- `whisper-finetune-data/model-merged/` — 合并 LoRA 后的完整模型

---

## 模型回流（训练完后）

训练完是 HuggingFace PyTorch 格式，还不能直接给 `voice_input.py` 用。需要转成 mlx 格式：

```bash
# 安装转换工具（如果没装过）
pip install mlx-whisper

# 转换
python -m mlx_whisper.convert \
  --model ~/Documents/Developer/whisper-finetune-data/model-merged \
  --output ~/Documents/Developer/whisper-finetune-data/model-mlx
```

转换完后修改 `config.yaml`：
```yaml
model: ~/Documents/Developer/whisper-finetune-data/model-mlx
```

重启 `voice_input.py` 即可使用微调后的模型。

---

## 数据存储位置

所有数据都在 `~/Documents/Developer/whisper-finetune-data/`（git 之外，不会误提交）：

```
whisper-finetune-data/
├── audio/              # 原始 WAV 音频
├── manifest.jsonl      # 所有条目的元数据（核心文件）
├── dataset/
│   ├── train.jsonl     # export 后的训练集
│   └── val.jsonl       # export 后的验证集
├── model/              # 训练 checkpoints
├── model-merged/       # 合并 LoRA 后的完整模型
├── model-mlx/          # 转换后的 mlx 格式（接回 voice_input.py 用）
└── vocab_overrides.json  # 可选：特定词汇替换规则
```
