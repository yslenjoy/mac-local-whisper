#!/usr/bin/env python3
"""
LoRA fine-tune Whisper on exported train/val JSONL.

Usage:
    python3 finetune/train.py
    python3 finetune/train.py --data-dir ~/path/to/data --epochs 10
    python3 finetune/train.py --base-model openai/whisper-large-v3-turbo

Prerequisites:
    pip install transformers datasets torch torchaudio peft accelerate
"""

import argparse
import json
import sys
from pathlib import Path

import struct
import wave

import numpy as np
import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
    WhisperForConditionalGeneration,
    WhisperProcessor,
)

DEFAULT_DATA_DIR = Path.home() / "Documents/Developer/whisper-finetune-data"
DEFAULT_MODEL = "openai/whisper-small"  # use small to fit in Mac memory; swap to large-v3-turbo for cloud


# ── Data loading ──────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def build_dataset(jsonl_path: Path) -> Dataset:
    """Load JSONL into a HuggingFace Dataset (audio as file path, loaded in collator)."""
    records = load_jsonl(jsonl_path)
    return Dataset.from_dict({
        "audio_path": [r["audio"] for r in records],
        "transcription": [r["transcription"] for r in records],
    })


# ── Data collator ─────────────────────────────────────────────────────────────

class WhisperDataCollator:
    """Collate audio + text into model inputs. Loads audio via torchaudio."""

    def __init__(self, processor: WhisperProcessor):
        self.processor = processor

    def __call__(self, features: list[dict]) -> dict:
        audio_arrays = []
        for f in features:
            with wave.open(f["audio_path"], "rb") as wf:
                n_frames = wf.getnframes()
                raw = wf.readframes(n_frames)
                pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            audio_arrays.append(pcm)
        transcriptions = [f["transcription"] for f in features]

        # Audio → mel spectrogram
        inputs = self.processor.feature_extractor(
            audio_arrays, sampling_rate=16000, return_tensors="pt"
        )

        # Text → token ids
        labels = self.processor.tokenizer(
            transcriptions, return_tensors="pt", padding=True
        )
        # Replace padding token id with -100 so it's ignored in loss
        label_ids = labels.input_ids.masked_fill(
            labels.attention_mask.ne(1), -100
        )
        return {
            "input_features": inputs.input_features,
            "labels": label_ids,
        }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LoRA fine-tune Whisper")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--base-model", default=DEFAULT_MODEL)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    args = parser.parse_args()

    dataset_dir = args.data_dir / "dataset"
    train_jsonl = dataset_dir / "train.jsonl"
    val_jsonl = dataset_dir / "val.jsonl"
    output_dir = args.data_dir / "model"

    if not train_jsonl.exists():
        sys.exit(f"train.jsonl not found: {train_jsonl}\nRun export.py first.")

    # ── Device ────────────────────────────────────────────────────────────────
    if torch.cuda.is_available():
        device = "cuda"
    elif torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
    print(f"Device: {device}")

    # ── Load model & processor ────────────────────────────────────────────────
    print(f"Loading model: {args.base_model}")
    processor = WhisperProcessor.from_pretrained(args.base_model)
    model = WhisperForConditionalGeneration.from_pretrained(
        args.base_model, torch_dtype=torch.float32
    )

    # Force Chinese + transcribe task
    model.config.forced_decoder_ids = processor.get_decoder_prompt_ids(
        language="zh", task="transcribe"
    )
    model.config.suppress_tokens = []

    # ── LoRA ──────────────────────────────────────────────────────────────────
    print(f"Applying LoRA (rank={args.lora_rank}, alpha={args.lora_alpha})")
    lora_config = LoraConfig(
        r=args.lora_rank,
        lora_alpha=args.lora_alpha,
        target_modules=["q_proj", "v_proj"],
        lora_dropout=0.05,
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # ── Dataset ───────────────────────────────────────────────────────────────
    print("Loading datasets...")
    train_ds = build_dataset(train_jsonl)
    val_ds = build_dataset(val_jsonl) if val_jsonl.exists() else None
    print(f"  train: {len(train_ds)}  val: {len(val_ds) if val_ds else 0}")

    collator = WhisperDataCollator(processor)

    # ── Training ──────────────────────────────────────────────────────────────
    training_args = Seq2SeqTrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        learning_rate=args.lr,
        warmup_steps=50,
        logging_steps=10,
        eval_strategy="epoch" if val_ds else "no",
        save_strategy="epoch",
        save_total_limit=3,
        fp16=False,  # MPS doesn't support fp16 training well
        gradient_checkpointing=True,  # trade compute for memory
        report_to="none",
        remove_unused_columns=False,
        label_names=["labels"],
        predict_with_generate=False,
    )

    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=collator,
    )

    print(f"\nStarting training ({args.epochs} epochs)...")
    trainer.train()

    # ── Save ──────────────────────────────────────────────────────────────────
    # Merge LoRA weights back into base model and save
    print("\nMerging LoRA weights...")
    merged_model = model.merge_and_unload()

    merged_dir = args.data_dir / "model-merged"
    merged_dir.mkdir(parents=True, exist_ok=True)
    merged_model.save_pretrained(str(merged_dir))
    processor.save_pretrained(str(merged_dir))

    print(f"\nDone! Merged model saved to: {merged_dir}")
    print(f"\nNext step: convert to mlx format:")
    print(f"  python -m mlx_whisper.convert --model {merged_dir} --output {args.data_dir / 'model-mlx'}")


if __name__ == "__main__":
    main()
