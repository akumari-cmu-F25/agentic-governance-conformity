#!/usr/bin/env python3
"""
Prompt templates for the pilot (used by whoever runs the target agent).

Round 1: target answers alone (no peers).
Round 2: target sees its own first answer plus three peers' answers, then
         gives a final answer.

Design rules (from the TA's feedback):
- Wording is IDENTICAL across all six scenarios, except the reputation labels
  and the one sentence that explains them (only shown when labels are shown).
- The label explanation is neutral: it says what the number means, and does
  NOT tell the agent whom to trust.
- The prompt never contains `correct_answer` / `incorrect_answer` as such;
  the only numbers shown are the question and the peers' stated answers.

Usage:
    python prompts.py                       # prints example prompts
    from prompts import round1_prompt, round2_prompt, extract_final_answer
"""
import json
import re
import sys
from pathlib import Path

SYSTEM_PROMPT = (
    "You are a careful assistant solving grade-school math word problems."
)

ANSWER_FORMAT = (
    "Briefly explain your reasoning, then end with a line in exactly this "
    "format:\nFinal answer: <number>"
)

REPUTATION_EXPLANATION = (
    "The number in parentheses after an agent's name is that agent's "
    "historical accuracy: the percentage of past questions it answered "
    "correctly."
)


def round1_prompt(question):
    return f"Question: {question}\n\n{ANSWER_FORMAT}"


def round2_prompt(scenario, initial_answer):
    """scenario: one entry from pilot_conditions.json.
    initial_answer: the target's own round-1 answer (string or number)."""
    has_labels = scenario["reputation_condition"] != "no_reputation"
    parts = [
        f"Question: {scenario['question']}",
        f"Your initial answer was: {initial_answer}",
        "Three other agents also answered this question:",
        scenario["peer_block"],
    ]
    if has_labels:
        parts.append(REPUTATION_EXPLANATION)
    parts.append(
        "Considering this, decide on your final answer. " + ANSWER_FORMAT
    )
    return "\n\n".join(parts)


def extract_final_answer(text):
    """Return the number after 'Final answer:' as an int (or None)."""
    m = re.findall(r"Final answer:\s*\$?\s*(-?[\d,]*\.?\d+)", text,
                   flags=re.IGNORECASE)
    if not m:
        return None
    val = float(m[-1].replace(",", ""))
    return int(val) if val == int(val) else val


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "pilot_output/pilot_conditions.json"
    scenarios = json.loads(Path(path).read_text(encoding="utf-8"))
    q1 = [s for s in scenarios if s["question_id"] == 1]
    print("=== SYSTEM ===\n" + SYSTEM_PROMPT)
    print("\n=== ROUND 1 ===\n" + round1_prompt(q1[0]["question"]))
    for s in q1:
        if s["majority_correct"] is False:
            print(f"\n=== ROUND 2: {s['scenario_id']} ===")
            print(round2_prompt(s, "<target's round-1 answer>"))
