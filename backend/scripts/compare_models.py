"""
Multi-model comparison harness (item 11 from the improvement list).

IMPORTANT: like run_evaluation.py, this does NOT report any numbers on
its own - it runs real debates against whichever models you actually
have API access to and writes the results to a CSV. I have credentials
for exactly the one Groq model in your .env and can't honestly fabricate
comparative quality/factuality/cost numbers for models I've never called.
Run this yourself with your own keys/budget to get real numbers.

Each model runs in its OWN subprocess (see run_single_debate.py) so the
cached LLM client (arena/config.py's module-level `llm`) doesn't leak
between models within a single process - that also gives clean, isolated
latency measurements per debate.

Usage:
    python scripts/compare_models.py \\
        --models llama-3.1-8b-instant llama-3.3-70b-versatile \\
        --topics data/eval_topics.json --n 5 --out data/model_comparison.csv

Any model string you pass must be one your MODEL_PROVIDER (Groq by
default) actually serves. To compare against a different backend
entirely, point GROQ_API_KEY/MODEL_PROVIDER at it in .env first.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def run_in_subprocess(topic: str, model_name: str) -> dict:
    env = os.environ.copy()
    env["MODEL_NAME"] = model_name

    start = time.time()

    try:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "run_single_debate.py"), "--topic", topic],
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        elapsed = time.time() - start

        if proc.returncode != 0:
            return {
                "model": model_name,
                "topic": topic,
                "error": proc.stderr[-500:],
                "elapsed_seconds": round(elapsed, 1),
            }

        # The node functions print a lot of debug info; the JSON result
        # is always the LAST non-empty stdout line (see run_single_debate.py).
        lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]

        if not lines:
            return {"model": model_name, "topic": topic, "error": "no output", "elapsed_seconds": round(elapsed, 1)}

        result = json.loads(lines[-1])
        result["model"] = model_name
        result["elapsed_seconds"] = round(elapsed, 1)
        return result

    except subprocess.TimeoutExpired:
        return {"model": model_name, "topic": topic, "error": "timeout", "elapsed_seconds": 300}
    except Exception as e:
        return {
            "model": model_name,
            "topic": topic,
            "error": str(e),
            "elapsed_seconds": round(time.time() - start, 1),
        }


def main():
    parser = argparse.ArgumentParser(description="Compare debate latency/decisions across models.")
    parser.add_argument("--models", nargs="+", required=True, help="Model names your provider serves")
    parser.add_argument("--topics", default="data/eval_topics.json")
    parser.add_argument("--n", type=int, default=3)
    parser.add_argument("--out", default="data/model_comparison.csv")
    args = parser.parse_args()

    with open(args.topics, "r", encoding="utf-8") as f:
        topics = json.load(f)[: args.n]

    rows = []
    total = len(args.models) * len(topics)
    done = 0

    for model in args.models:
        for topic in topics:
            done += 1
            print(f"[{done}/{total}] model={model} topic={topic[:50]}")
            rows.append(run_in_subprocess(topic, model))

    fieldnames = [
        "model", "topic", "algorithm_winner", "weighted_elena", "weighted_marcus",
        "judge_winner", "elapsed_seconds", "contradictions_detected", "error",
    ]

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    print(f"\nWrote {len(rows)} rows to {args.out}")
    print("Latency is measured directly and is real. Argument-quality/factuality")
    print("differences between models still need your own read-through, or run")
    print("each model's CSV through report_agreement.py against the same human labels.")


if __name__ == "__main__":
    main()
