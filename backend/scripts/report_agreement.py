"""
Reports algorithm-vs-human agreement from a CSV produced by
run_evaluation.py, AFTER a human has filled in the human_winner column.

This does not compute anything if human_winner is blank - it will just
report 0 labeled rows. That's intentional: there is no honest way to
report an agreement percentage without real human judgments.

Usage:
    python scripts/report_agreement.py data/eval_results.csv
"""

import csv
import sys


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/report_agreement.py <results.csv>")
        sys.exit(1)

    path = sys.argv[1]

    with open(path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    labeled = [r for r in rows if r.get("human_winner", "").strip()]

    print(f"Total debates run   : {len(rows)}")
    print(f"Human-labeled rows  : {len(labeled)}")

    if not labeled:
        print("\nNo human labels found yet - fill in the 'human_winner' "
              "column in the CSV, then re-run this script.")
        return

    algo_agree = sum(
        1 for r in labeled
        if r["human_winner"].strip().lower() == r["algorithm_winner"].strip().lower()
    )
    judge_agree = sum(
        1 for r in labeled
        if r["human_winner"].strip().lower() == r["judge_winner"].strip().lower()
    )

    print(f"\nWeighted-composite algorithm agreement with humans: "
          f"{algo_agree}/{len(labeled)} ({100 * algo_agree / len(labeled):.1f}%)")
    print(f"AI Judge (subjective) agreement with humans:        "
          f"{judge_agree}/{len(labeled)} ({100 * judge_agree / len(labeled):.1f}%)")


if __name__ == "__main__":
    main()
