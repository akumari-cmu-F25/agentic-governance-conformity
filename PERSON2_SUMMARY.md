# Person 2: Target Agent Simulation

**Approach:** I ran the same 90-scenario simulation (15 questions × 6 conditions) on two Claude configurations: a stronger model at medium effort (`claude-opus-5-5`, medium) and a weaker model at low effort (`claude-haiku-5-5`, low). Everything else was identical: questions, prompts, peer answers and procedure. Any difference between the two result sets comes from the model and effort level alone.

## What I did

1. **Built on Person 1's setup.** I used Samiyah's `pilot_output/pilot_conditions.json` (90 scenarios) as input and her `prompts.py` templates unchanged. The script imports the prompt functions directly, so the wording cannot drift from her version.

2. **Chose Claude as the target agent.** Calls go through the official Anthropic Python SDK (v2.8.0) in a project-local Python 3.12 environment (`.venv`).

3. **Wrote `run_target_agent.py`.** It loads all 90 scenarios and processes each one in two rounds.

4. **Round 1 (alone):** the question is sent with `round1_prompt()`, and the agent's initial answer is extracted from its "Final answer: <number>" line.

5. **Round 2 (with peers):** the question, the agent's own initial answer, and the three peers' answers (with reputation labels where the condition has them) are sent with `round2_prompt()`. The agent's final answer is extracted the same way.

6. **Kept memory isolated.** Every API call is a brand-new conversation containing only that one prompt. Nothing carries over between scenarios or between conditions of the same question. The only link from Round 1 to Round 2 is the initial answer written into the Round 2 prompt text.

7. **Kept the configuration fixed and recorded.** The API key, model and effort level are set in a git-ignored `.env` file (or as command-line options). Current Claude models don't accept a temperature setting, so the model and effort level define each run. Both are recorded in every output row, along with the model that actually answered.

8. **Made the runs reliable.** Failed API calls are retried automatically. Each scenario is saved as soon as it finishes, so an interrupted run resumes where it stopped. `--retry-failed` re-runs only rows that errored or produced no readable answer.

9. **Produced two result sets.** Both runs completed all 90 scenarios with 0 API errors, 0 unreadable answers and 0 refusals:
   - `results/`: `claude-opus-5-5`, medium effort
   - `results_haiku_low/`: `claude-haiku-5-5`, low effort

10. **Packaged the handoff for Person 3.** Each folder contains:
    - `target_agent_results.csv`: 90 rows with question ID and text, condition name and variables, the target's initial and final answers, and the full responses.
    - `target_agent_results.jsonl`: the exact prompts sent and the raw model responses.
    - `README.md`: what each column means and how the run was configured.

    The output is raw data only. Person 3 computes the analysis (accuracy, answer-switching, and who the agent conformed to), using the correct answers in Samiyah's `pilot_output/pilot_questions.csv`.

## How to re-run
```bash
.venv/bin/python run_target_agent.py                                                   # settings from .env
.venv/bin/python run_target_agent.py --model claude-haiku-5-5 --effort low --out-dir results_haiku_low
```
