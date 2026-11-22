# Target agent results: Run 1

## Files
- `target_agent_results.csv`: 90 rows (15 questions × 6 conditions), one per scenario.
- `target_agent_results.jsonl`: full audit trail with the exact prompts sent and the raw model responses for each round.

## Run configuration
| Setting | Value |
|---|---|
| Model | `claude-opus-5-5` (the `served_model` column shows the model that actually answered each row) |
| Effort | `medium` |
| Temperature | not settable on current Claude models |
| Prompts | `prompts.py` (Samiyah's templates, imported unchanged) |
| Isolation | every API call is a fresh, single-message conversation; Round 2 only sees the parsed Round 1 answer via `round2_prompt()` |
| Run status | 0 API errors, 0 parse failures, 0 refusal fallbacks |

## Columns
| Column | Meaning |
|---|---|
| `scenario_id`, `question_id`, `gsm8k_test_index` | Row identifiers; `question_id` joins to `pilot_output/pilot_questions.csv` |
| `question` | Question text |
| `condition_name` | Readable condition label, e.g. "High-Rep Majority, Majority Incorrect" |
| `reputation_condition`, `majority_correct`, `high_rep_group`, `peer_order_roles` | Condition variables, copied from `pilot_conditions.json` |
| `incorrect_answer`, `majority_answer`, `minority_answer` | Copied unchanged from `pilot_conditions.json` (correct answers: see `pilot_output/pilot_questions.csv`) |
| `target_initial_answer` | Round 1 answer (target alone) |
| `target_final_answer` | Round 2 answer (after seeing the peers) |
| `initial_parse_ok` / `final_parse_ok` | `False` means no "Final answer: <number>" was found in that round's response |
| `initial_stop_reason` / `final_stop_reason` | API stop reason (`end_turn` is a normal completion) |
| `fallback_used` | `True` if another model answered after a refusal |
| `initial_raw_response` / `final_raw_response` | Full model text for each round |
| `model`, `served_model`, `effort`, `timestamp`, `error` | Run provenance |

Answers were extracted with `extract_final_answer()` from `prompts.py`.
