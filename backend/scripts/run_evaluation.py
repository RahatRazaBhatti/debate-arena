"""
Evaluation harness (item 10 from the improvement list).

IMPORTANT: this script does NOT fabricate a research result. It runs
real debates and records the algorithm's decisions to a CSV with a
"human_winner" column left BLANK. A real evaluation requires real
people to actually watch/read each debate and fill that column in -
that's not something that can be honestly generated from a language
model note. Run this, get humans to label the output CSV, then run
`report_agreement.py` (below) on the labeled file.

Usage:
    python scripts/run_evaluation.py --topics data/eval_topics.json --n 10 --out data/eval_results.csv
    # ... humans fill in the human_winner column by hand ...
    python scripts/report_agreement.py data/eval_results.csv
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_single_debate import run_one_debate as _run_one_debate


def run_one_debate(topic: str) -> dict:
    result = _run_one_debate(topic)
    result["human_winner"] = ""  # deliberately blank; fill in by hand
    return result


def main():
    parser = argparse.ArgumentParser(description="Run debates across topics for evaluation.")
    parser.add_argument("--topics", default="data/eval_topics.json")
    parser.add_argument("--n", type=int, default=5, help="Number of topics to run (from the top of the file)")
    parser.add_argument("--out", default="data/eval_results.csv")
    args = parser.parse_args()

    with open(args.topics, "r", encoding="utf-8") as f:
        topics = json.load(f)[: args.n]

    rows = []

    for i, topic in enumerate(topics, 1):
        print(f"[{i}/{len(topics)}] Running: {topic}")
        try:
            rows.append(run_one_debate(topic))
        except Exception as e:
            print(f"  FAILED: {e}")
            rows.append({"topic": topic, "algorithm_winner": "ERROR", "error": str(e)})

    fieldnames = [
        "topic", "algorithm_winner", "weighted_elena", "weighted_marcus",
        "judge_winner", "elapsed_seconds", "contradictions_detected", "human_winner",
    ]

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    print(f"\nWrote {len(rows)} results to {args.out}")
    print("Next: have a human fill in the 'human_winner' column, then run report_agreement.py")


if __name__ == "__main__":
    main()
