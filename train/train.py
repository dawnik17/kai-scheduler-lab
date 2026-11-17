"""
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True CUDA_VISIBLE_DEVICES=0 torchrun --nproc_per_node=1 train.py
"""

import os

os.environ.setdefault("HF_HOME", "/sadata/nikkothari/cache/hf")

from transformers import AutoTokenizer, AutoModelForCausalLM, Trainer, TrainingArguments
from transformers import DataCollatorForLanguageModeling
from datasets import load_dataset
from pathlib import Path
import logging
import sys
import torch

RANK = os.environ.get("RANK", "0")
MAIN = RANK == "0"

logging.basicConfig(
    format=f"%(asctime)s [rank {RANK}] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO if MAIN else logging.WARNING,
    stream=sys.stdout,
)
logger = logging.getLogger("train")
logging.getLogger("httpx").setLevel(logging.WARNING)

OUTPUT_DIR = "/sadata/nikkothari/kai-scheduler-lab/train/ckpts/"
MODEL_NAME = "google/gemma-4-E2B-it"
DATA_NAME = "trl-lib/Capybara"
MAX_LENGTH = 4096
PER_DEVICE_BATCH_SIZE = 2


def main():
    if MAIN:
        Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    logger.info("Model: %s | Dataset: %s | Output: %s | Max length: %d", MODEL_NAME, DATA_NAME, OUTPUT_DIR, MAX_LENGTH)
    logger.info("World size: %s", os.environ.get("WORLD_SIZE", "1"))

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        dtype=torch.bfloat16,
    )
    n_params = sum(p.numel() for p in model.parameters())
    n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info("Loaded %s: %.2fB params (%.2fB trainable)", type(model).__name__, n_params / 1e9, n_trainable / 1e9)

    # Dataset
    train_dataset = load_dataset(DATA_NAME, split="train")
    eval_dataset = load_dataset(DATA_NAME, split="test")
    logger.info("Loaded %d train / %d eval examples", len(train_dataset), len(eval_dataset))

    # Tokenize Dataset
    tokenize_function = lambda messages: tokenizer.apply_chat_template(
        messages["messages"],
        tokenize=True,
        return_dict=True,
        truncation=True,
        max_length=MAX_LENGTH,
        padding=False,
        add_generation_prompt=False,
    )

    remove_columns = list(train_dataset[0].keys())
    train_tokenized_dataset = train_dataset.map(
        tokenize_function, batched=True, remove_columns=remove_columns
    )
    eval_tokenized_dataset = eval_dataset.map(
        tokenize_function, batched=True, remove_columns=remove_columns
    )

    for split, ds in [("train", train_tokenized_dataset), ("eval", eval_tokenized_dataset)]:
        lengths = [len(ids) for ids in ds["input_ids"]]
        logger.info(
            "Tokenized %s: %d tokens, mean %.0f / max %d per example, %d truncated at %d",
            split, sum(lengths), sum(lengths) / len(lengths), max(lengths),
            sum(l >= MAX_LENGTH for l in lengths), MAX_LENGTH,
        )

    train_tokenized_dataset = list(train_tokenized_dataset)
    eval_tokenized_dataset = list(eval_tokenized_dataset)

    # Data Collator
    collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False,
        pad_to_multiple_of=8,
        return_tensors="pt",
    )

    # Training Arguments
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        eval_strategy="steps",
        eval_steps=100,
        save_strategy="steps",
        save_steps=100,
        save_total_limit=2,
        learning_rate=2e-5,
        per_device_train_batch_size=PER_DEVICE_BATCH_SIZE,
        per_device_eval_batch_size=PER_DEVICE_BATCH_SIZE,
        num_train_epochs=3,
        bf16=True,
        report_to="tensorboard",
        gradient_checkpointing=True,
        logging_steps=10,
        logging_first_step=True,
        log_level="info",
        log_level_replica="warning",
        ddp_find_unused_parameters=True,
    )

    # Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_tokenized_dataset,
        eval_dataset=eval_tokenized_dataset,
        data_collator=collator,
        processing_class=tokenizer,
    )

    logger.info("Starting training")

    # Trainer writes trainer_state.json last, so a checkpoint without it was cut off mid-save (e.g. by preemption).
    complete = [c for c in Path(OUTPUT_DIR).glob("checkpoint-*") if (c / "trainer_state.json").exists()]
    last_checkpoint = str(max(complete, key=lambda c: int(c.name.split("-")[1]))) if complete else None

    train_result = trainer.train(resume_from_checkpoint=last_checkpoint)
    trainer.log_metrics("train", train_result.metrics)
    trainer.save_metrics("train", train_result.metrics)
    trainer.save_model()

    if MAIN:
        tokenizer.save_pretrained(training_args.output_dir)
    logger.info("Saved final model and tokenizer to %s", training_args.output_dir)


if __name__ == "__main__":
    main()
