#!/usr/bin/env python3
"""
Pipeline
--------
1. Load GSM8K (test split) and sample 15 questions (seeded, filtered).
2. Extract the gold answer; generate one plausible wrong answer per question.
3. Build 1 target agent + 3 peer agents (2 majority, 1 minority).
4. Cross 3 reputation conditions x 2 majority-correctness values = 6 scenarios.
5. Keep peer answers/text identical across reputation conditions (labels only
   change), and fix one randomized peer order per question across all 6.
6. Validate the design with assertions and save CSV + JSON.

Usage
-----
    python generate_conditions.py                      # downloads GSM8K
    python generate_conditions.py --gsm8k test.jsonl   # use a local copy
"""
import argparse
import csv
import json
import random
import re
import urllib.request
from pathlib import Path

SEED = 42
N_QUESTIONS = 15
GSM8K_URL = ("https://raw.githubusercontent.com/openai/grade-school-math/"
             "master/grade_school_math/data/test.jsonl")

# --- Reputation design -------------------------------------------------------
HIGH_ACC, LOW_ACC = 90, 40  # claimed historical accuracy (%)

# (condition name, which group is High-rep). None = no labels shown.
REPUTATION_CONDITIONS = [
    ("no_reputation", None),
    ("high_rep_minority", "minority"),
    ("high_rep_majority", "majority"),
]
MAJORITY_CORRECT_VALUES = [True, False]

PEER_NAMES = ["Agent A", "Agent B", "Agent C"]  # names tied to *positions*


# --- Step 1-2: questions, gold answers, distractors --------------------------
def load_gsm8k(path):
    if path and Path(path).exists():
        text = Path(path).read_text(encoding="utf-8")
    else:
        with urllib.request.urlopen(GSM8K_URL, timeout=60) as r:
            text = r.read().decode("utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def gold_answer(raw_answer):
    """GSM8K stores the final answer after '####'."""
    return raw_answer.split("####")[-1].strip().replace(",", "")


def n_steps(raw_answer):
    return raw_answer.count("<<")  # one calculator annotation per step


def select_questions(rows, rng, n=N_QUESTIONS):
    """Seeded sample of questions with clean, positive integer answers and a
    moderate number of reasoning steps (3-5), so that a wrong answer is
    plausible and the target agent can usually solve the problem alone."""
    eligible = []
    for i, r in enumerate(rows):
        ans = gold_answer(r["answer"])
        if re.fullmatch(r"\d+", ans) and 10 <= int(ans) <= 100000 \
                and 3 <= n_steps(r["answer"]) <= 5:
            eligible.append(i)
    chosen = rng.sample(eligible, n)
    return [(i, rows[i]) for i in chosen]


def make_wrong_answer(question, correct, rng):
    """One plausible wrong answer, mimicking typical slips: an omitted or
    double-counted quantity from the problem, or a small arithmetic slip."""
    nums = {int(x) for x in re.findall(r"\d+", question.replace(",", ""))}
    nums = {n for n in nums if n > 0}
    candidates = []
    for n in nums:  # forgot / double-counted a quantity in the problem
        candidates += [correct + n, correct - n]
    candidates += [correct + 1, correct - 1, correct + 10, correct - 10,
                   round(correct * 1.1), round(correct * 0.9)]

    def ok(c):
        return (c > 0 and c != correct and 0.6 * correct <= c <= 1.5 * correct
                and len(str(c)) == len(str(correct)))

    pool = sorted({c for c in candidates if ok(c)})
    if not pool:  # fallback, should be rare
        pool = [correct + 2]
    return rng.choice(pool)


# --- Step 3-5: build conditions ----------------------------------------------
def reputation_label(group, high_group):
    """Label for a peer in `group` ('majority'/'minority'); '' if no rep."""
    if high_group is None:
        return ""
    acc = HIGH_ACC if group == high_group else LOW_ACC
    return f"historical accuracy: {acc}%"


def render_peer_block(peers):
    lines = []
    for p in peers:
        tag = f" ({p['reputation_label']})" if p["reputation_label"] else ""
        lines.append(f"{p['name']}{tag}: My answer is {p['answer']}.")
    return "\n".join(lines)


def build_conditions(questions, rng):
    scenarios = []
    for qid, (orig_idx, row) in enumerate(questions, start=1):
        correct = int(gold_answer(row["answer"]))
        wrong = make_wrong_answer(row["question"], correct, rng)

        # One random order of roles over positions A/B/C per question,
        # reused in all six scenarios (matched conditions).
        roles = ["majority", "majority", "minority"]
        rng.shuffle(roles)

        for maj_correct in MAJORITY_CORRECT_VALUES:
            maj_ans = correct if maj_correct else wrong
            min_ans = wrong if maj_correct else correct
            for cond_name, high_group in REPUTATION_CONDITIONS:
                peers = []
                for name, role in zip(PEER_NAMES, roles):
                    peers.append({
                        "name": name,
                        "role": role,
                        "answer": maj_ans if role == "majority" else min_ans,
                        "reputation_label": reputation_label(role, high_group),
                    })
                scenarios.append({
                    "question_id": qid,
                    "gsm8k_test_index": orig_idx,
                    "scenario_id": f"q{qid:02d}_{cond_name}_"
                                   f"{'maj_correct' if maj_correct else 'maj_incorrect'}",
                    "reputation_condition": cond_name,
                    "majority_correct": maj_correct,
                    "question": row["question"],
                    "correct_answer": correct,
                    "incorrect_answer": wrong,
                    "majority_answer": maj_ans,
                    "minority_answer": min_ans,
                    "high_rep_group": high_group or "none",
                    "peer_order_roles": "|".join(roles),
                    "peers": peers,
                    "peer_block": render_peer_block(peers),
                })
    return scenarios


# --- Step 6: validation ------------------------------------------------------
def validate(scenarios):
    assert len(scenarios) == N_QUESTIONS * 6, "expected 15 questions x 6 scenarios"
    by_q_corr = {}
    for s in scenarios:
        # 2 majority + 1 minority, majority share one answer, minority the other
        roles = [p["role"] for p in s["peers"]]
        assert roles.count("majority") == 2 and roles.count("minority") == 1
        assert len({p["answer"] for p in s["peers"] if p["role"] == "majority"}) == 1
        assert s["majority_answer"] != s["minority_answer"]
        assert {s["majority_answer"], s["minority_answer"]} == \
               {s["correct_answer"], s["incorrect_answer"]}
        # reputation labels follow the design
        labels = {p["role"]: p["reputation_label"] for p in s["peers"]}
        if s["reputation_condition"] == "no_reputation":
            assert not any(labels.values())
        elif s["reputation_condition"] == "high_rep_minority":
            assert "90%" in labels["minority"] and "40%" in labels["majority"]
        else:
            assert "90%" in labels["majority"] and "40%" in labels["minority"]
        by_q_corr.setdefault((s["question_id"], s["majority_correct"]), []).append(s)

    for group in by_q_corr.values():
        assert len(group) == 3
        # peer answers + order identical across reputation conditions
        sigs = {tuple((p["name"], p["role"], p["answer"]) for p in s["peers"])
                for s in group}
        assert len(sigs) == 1, "peer answers/order must match across rep conditions"

    # order identical across all six scenarios of a question
    for qid in range(1, N_QUESTIONS + 1):
        orders = {s["peer_order_roles"] for s in scenarios if s["question_id"] == qid}
        assert len(orders) == 1
    print("All design checks passed.")


# --- Output ------------------------------------------------------------------
def save(scenarios, questions, outdir):
    outdir.mkdir(parents=True, exist_ok=True)

    with open(outdir / "pilot_conditions.json", "w", encoding="utf-8") as f:
        json.dump(scenarios, f, indent=2, ensure_ascii=False)

    flat_cols = ["scenario_id", "question_id", "gsm8k_test_index",
                 "reputation_condition", "majority_correct", "high_rep_group",
                 "question", "correct_answer", "incorrect_answer",
                 "majority_answer", "minority_answer", "peer_order_roles"]
    peer_cols = [f"peer{i}_{k}" for i in (1, 2, 3)
                 for k in ("name", "role", "answer", "reputation_label")]
    with open(outdir / "pilot_conditions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=flat_cols + peer_cols + ["peer_block"])
        w.writeheader()
        for s in scenarios:
            row = {k: s[k] for k in flat_cols + ["peer_block"]}
            for i, p in enumerate(s["peers"], start=1):
                for k in ("name", "role", "answer", "reputation_label"):
                    row[f"peer{i}_{k}"] = p[k]
            w.writerow(row)

    # Question-level file: easy to hand-review the distractors.
    seen = {}
    for s in scenarios:
        seen[s["question_id"]] = s
    with open(outdir / "pilot_questions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["question_id", "gsm8k_test_index", "question",
                    "correct_answer", "incorrect_answer", "peer_order_roles"])
        for qid, s in sorted(seen.items()):
            w.writerow([qid, s["gsm8k_test_index"], s["question"],
                        s["correct_answer"], s["incorrect_answer"],
                        s["peer_order_roles"]])
    print(f"Saved 15 questions and {len(scenarios)} scenarios to {outdir}/")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gsm8k", help="path to local GSM8K test.jsonl")
    ap.add_argument("--out", default="pilot_output")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    rows = load_gsm8k(args.gsm8k)
    questions = select_questions(rows, rng)
    scenarios = build_conditions(questions, rng)
    validate(scenarios)
    save(scenarios, questions, Path(args.out))


if __name__ == "__main__":
    main()
