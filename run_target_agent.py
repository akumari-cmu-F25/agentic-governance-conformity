#!/usr/bin/env python3
"""
Person 2 - Target agent simulation (Claude).

For each of the 90 scenarios in pilot_output/pilot_conditions.json:
  Round 1: target answers the question alone        (fresh API call)
  Round 2: target sees its own answer + 3 peers      (fresh API call)

Memory isolation: every API call sends a brand-new `messages` list containing
only that one prompt. Nothing is shared between scenarios or between rounds;
the only link from Round 1 to Round 2 is the parsed initial answer that
prompts.round2_prompt() writes into the Round 2 text.

Config comes from .env (ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_EFFORT).
Values in .env override anything already exported in your shell.

Outputs (in --out-dir, default results/):
  target_agent_results.jsonl  full audit trail (prompts + raw responses), appended per scenario
  target_agent_results.csv    90-row table for Person 3, rebuilt from the JSONL

Usage:
  .venv/bin/python run_target_agent.py                 # full run (resumes if interrupted)
  .venv/bin/python run_target_agent.py --limit 2       # smoke test on first 2 scenarios
  .venv/bin/python run_target_agent.py --retry-failed  # re-run rows that errored / didn't parse
  .venv/bin/python run_target_agent.py --rebuild-csv   # regenerate CSV from JSONL only
"""
import argparse
import csv
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from prompts import SYSTEM_PROMPT, extract_final_answer, round1_prompt, round2_prompt

HERE = Path(__file__).resolve().parent
DEFAULT_CONDITIONS = HERE / "pilot_output" / "pilot_conditions.json"
EFFORTS = ["low", "medium", "high", "xhigh", "max"]

REPUTATION_NAMES = {
    "no_reputation": "No Reputation",
    "high_rep_majority": "High-Rep Majority",
    "high_rep_minority": "High-Rep Minority",
}

CSV_COLUMNS = [
    "scenario_id", "question_id", "gsm8k_test_index", "question",
    "condition_name", "reputation_condition", "majority_correct", "high_rep_group",
    "peer_order_roles",
    "incorrect_answer", "majority_answer", "minority_answer",
    "target_initial_answer", "target_final_answer",
    "initial_parse_ok", "final_parse_ok",
    "initial_stop_reason", "final_stop_reason", "fallback_used",
    "initial_raw_response", "final_raw_response",
    "model", "served_model", "effort", "timestamp", "error",
]


def condition_name(s):
    rep = REPUTATION_NAMES.get(s["reputation_condition"], s["reputation_condition"])
    maj = "Majority Correct" if s["majority_correct"] else "Majority Incorrect"
    return f"{rep}, {maj}"


class TargetAgent:
    def __init__(self, model, effort, use_fallbacks):
        # SDK retries 408/409/429/5xx + connection errors with exponential backoff.
        self.client = anthropic.Anthropic(max_retries=6)
        self.model = model
        self.effort = effort
        self.use_fallbacks = use_fallbacks

    def ask(self, user_prompt):
        """One stateless call: a fresh messages list holding only this prompt."""
        kwargs = dict(
            model=self.model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            output_config={"effort": self.effort},
            messages=[{"role": "user", "content": user_prompt}],
        )
        if self.use_fallbacks:
            resp = self.client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                **kwargs,
            )
        else:
            resp = self.client.messages.create(**kwargs)

        text = "".join(b.text for b in resp.content if b.type == "text")
        iterations = getattr(resp.usage, "iterations", None) or []
        fallback_used = any(getattr(it, "type", "") == "fallback_message" for it in iterations)
        return {
            "text": text,
            "stop_reason": resp.stop_reason,
            "served_model": resp.model,
            "fallback_used": fallback_used,
            "request_id": resp._request_id,
            "usage": {
                "input_tokens": resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
            },
        }


def run_scenario(agent, s):
    record = {
        "scenario_id": s["scenario_id"],
        "model": agent.model,
        "effort": agent.effort,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "error": "",
    }
    try:
        # Round 1 - alone
        p1 = round1_prompt(s["question"])
        r1 = agent.ask(p1)
        a1 = extract_final_answer(r1["text"])

        # Round 2 - with peers (new, independent call)
        p2 = round2_prompt(s, a1 if a1 is not None else "(no answer given)")
        r2 = agent.ask(p2)
        a2 = extract_final_answer(r2["text"])

        record.update(
            round1_prompt=p1, round1=r1, target_initial_answer=a1,
            round2_prompt=p2, round2=r2, target_final_answer=a2,
        )
    except anthropic.APIError as e:
        record["error"] = f"{type(e).__name__}: {e}"
    return record


def load_done(jsonl_path):
    done = {}
    if jsonl_path.exists():
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                done[rec["scenario_id"]] = rec  # last write wins
    return done


def build_csv(scenarios, records, csv_path):
    rows = []
    for s in scenarios:
        rec = records.get(s["scenario_id"])
        if rec is None:
            continue
        r1, r2 = rec.get("round1", {}), rec.get("round2", {})
        a1, a2 = rec.get("target_initial_answer"), rec.get("target_final_answer")
        rows.append({
            "scenario_id": s["scenario_id"],
            "question_id": s["question_id"],
            "gsm8k_test_index": s["gsm8k_test_index"],
            "question": s["question"],
            "condition_name": condition_name(s),
            "reputation_condition": s["reputation_condition"],
            "majority_correct": s["majority_correct"],
            "high_rep_group": s["high_rep_group"],
            "peer_order_roles": s["peer_order_roles"],
            "incorrect_answer": s["incorrect_answer"],
            "majority_answer": s["majority_answer"],
            "minority_answer": s["minority_answer"],
            "target_initial_answer": "" if a1 is None else a1,
            "target_final_answer": "" if a2 is None else a2,
            "initial_parse_ok": a1 is not None,
            "final_parse_ok": a2 is not None,
            "initial_stop_reason": r1.get("stop_reason", ""),
            "final_stop_reason": r2.get("stop_reason", ""),
            "fallback_used": bool(r1.get("fallback_used") or r2.get("fallback_used")),
            "initial_raw_response": r1.get("text", ""),
            "final_raw_response": r2.get("text", ""),
            "model": rec["model"],
            "served_model": r2.get("served_model") or r1.get("served_model", ""),
            "effort": rec["effort"],
            "timestamp": rec["timestamp"],
            "error": rec.get("error", ""),
        })
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return rows


def main():
    # override=True: the key in .env wins over any old ANTHROPIC_API_KEY exported in the shell.
    load_dotenv(HERE / ".env", override=True)

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--conditions", type=Path, default=DEFAULT_CONDITIONS)
    ap.add_argument("--out-dir", type=Path, default=HERE / "results")
    ap.add_argument("--model", default=os.environ.get("CLAUDE_MODEL", "").strip() or "claude-opus-5-5",
                    help="Overrides CLAUDE_MODEL from .env.")
    ap.add_argument("--effort", default=os.environ.get("CLAUDE_EFFORT", "").strip() or "medium",
                    choices=EFFORTS, help="Overrides CLAUDE_EFFORT from .env.")
    ap.add_argument("--no-fallbacks", action="store_true",
                    help="Disable server-side refusal fallback (another model answering if Claude declines).")
    ap.add_argument("--workers", type=int, default=4, help="Scenarios run in parallel (each is still isolated).")
    ap.add_argument("--limit", type=int, help="Only run the first N scenarios (smoke test).")
    ap.add_argument("--retry-failed", action="store_true", help="Re-run scenarios that errored or failed to parse.")
    ap.add_argument("--rebuild-csv", action="store_true", help="Only rebuild the CSV from existing JSONL.")
    args = ap.parse_args()

    scenarios = json.loads(args.conditions.read_text(encoding="utf-8"))
    if args.limit:
        scenarios = scenarios[: args.limit]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = args.out_dir / "target_agent_results.jsonl"
    csv_path = args.out_dir / "target_agent_results.csv"

    done = load_done(jsonl_path)

    if not args.rebuild_csv:
        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            sys.exit("ANTHROPIC_API_KEY is empty - paste your Claude key into .env first.")

        def needs_run(s):
            rec = done.get(s["scenario_id"])
            if rec is None:
                return True
            if args.retry_failed:
                return bool(rec.get("error")) or rec.get("target_initial_answer") is None \
                    or rec.get("target_final_answer") is None
            return False

        todo = [s for s in scenarios if needs_run(s)]
        print(f"{len(scenarios) - len(todo)} already done, {len(todo)} to run "
              f"(model={args.model}, effort={args.effort}, workers={args.workers})")

        agent = TargetAgent(args.model, args.effort, use_fallbacks=not args.no_fallbacks)
        lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=args.workers) as pool, \
                jsonl_path.open("a", encoding="utf-8") as out:
            futures = {pool.submit(run_scenario, agent, s): s for s in todo}
            for i, fut in enumerate(as_completed(futures), 1):
                rec = fut.result()
                with lock:
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    out.flush()
                done[rec["scenario_id"]] = rec
                status = rec["error"] or (f"R1={rec.get('target_initial_answer')} "
                                          f"R2={rec.get('target_final_answer')}")
                print(f"[{i}/{len(todo)}] {rec['scenario_id']}: {status}", flush=True)

    rows = build_csv(scenarios, done, csv_path)
    errors = sum(1 for r in rows if r["error"])
    parse_fail = sum(1 for r in rows if not r["error"] and not (r["initial_parse_ok"] and r["final_parse_ok"]))
    fallbacks = sum(1 for r in rows if r["fallback_used"])
    print(f"\nWrote {len(rows)} rows -> {csv_path}")
    print(f"  API errors: {errors}   parse failures: {parse_fail}   fallback used: {fallbacks}")
    if errors or parse_fail:
        print("  Re-run with --retry-failed to retry those rows.")
    return 0 if len(rows) == len(scenarios) and not errors else 1


if __name__ == "__main__":
    sys.exit(main())
