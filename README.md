# Agentic Governance: Conformity Pilot

As AI agents increasingly work alongside other agents, a governance question arises: **does an agent keep its own correct judgment, or does it give in to what other agents say?** This pilot studies that question with a controlled experiment. A target AI agent solves grade-school math problems (GSM8K) on its own, then sees answers from three "peer" agents. Some peers are wrong, and some carry reputation labels (historical accuracy scores). We record whether the agent changes its answer.

The same experiment was run on two Claude configurations, a stronger model at medium effort (`claude-opus-5-5`) and a weaker model at low effort (`claude-haiku-5-5`), so their behaviour can be compared under identical conditions.

![Pipeline](diagrams/pipeline.png)

## Design
- **15 GSM8K questions × 6 conditions = 90 scenarios.**
- **Reputation:** none, high-reputation majority, or high-reputation minority.
- **Majority:** either correct or incorrect.
- **Round 1:** the agent answers alone.
- **Round 2:** the agent sees its own answer plus three peer answers, then gives a final answer.
- **Memory isolation:** every API call is a fresh conversation, so nothing carries over between scenarios.

## Team roles
| Role | Work | Files |
|---|---|---|
| Person 1 | Dataset prep, peer answers, conditions, prompt templates | `generate_conditions.py`, `prompts.py`, `pilot_output/` |
| Person 2 | Target agent simulation on two model configurations | `run_target_agent.py`, `results/`, `results_haiku_low/`, [`PERSON2_SUMMARY.md`](PERSON2_SUMMARY.md) |
| Person 3 | Evaluation and analysis: accuracy, switching rate, conformity, model comparison | *(to come)* |

## Repository layout
```
generate_conditions.py     Builds the 90 scenarios (Person 1)
prompts.py                 Round 1 / Round 2 prompt templates + answer parser (Person 1)
pilot_output/              Questions with correct answers, and the 90 scenarios (Person 1)
run_target_agent.py        Runs the target agent on all scenarios (Person 2)
results/                   Run 1: claude-opus-5-5, medium effort  (CSV + JSONL + README)
results_haiku_low/         Run 2: claude-haiku-5-5, low effort    (CSV + JSONL + README)
diagrams/                  Pipeline flowchart (PNG + editable SVG)
PERSON2_SUMMARY.md         What Person 2 did, step by step
```

## Running the simulation
Requires Python 3.10+ and a Claude API key.
```bash
python3 -m venv .venv && .venv/bin/pip install anthropic python-dotenv
```
Create a `.env` file with the following (never commit it):
```
ANTHROPIC_API_KEY=your-key
CLAUDE_MODEL=claude-opus-5-5
CLAUDE_EFFORT=medium
```
Then run:
```bash
.venv/bin/python run_target_agent.py                                                    # uses .env settings
.venv/bin/python run_target_agent.py --model claude-haiku-5-5 --effort low --out-dir results_haiku_low
```
