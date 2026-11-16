# Working in this repo

For a person or a coding agent who pulls this branch. The reader's path starts at [README.md](README.md) (the base agent) and [docs/JEV.md](docs/JEV.md) (the Jev experiment).

## Commands
| To do this | Run | Keys |
|---|---|---|
| Install and run the offline tests (218, about 2 seconds) | `uv run pytest` | none |
| Run the agent as submitted | `uv run uvicorn app.server:app --port 8000` | `ANTHROPIC_API_KEY` |
| Run it with the store and Jev | `BOOKLY_STORE=1 uv run uvicorn app.server:app --port 8000` | both |
| Base eval suite (about $1) | `uv run python -m evals.run_evals --k 5` | Anthropic |
| Jev judgments (about $0.01) | `uv run python -m evals.judgment_eval` | `TYPESAFE_API_KEY` |
| Journeys across conversations (about $0.85) | `uv run python -m evals.run_journeys --k 3` | both |

Keys go in `.env` (`cp .env.example .env`). Live evals spend money; the offline tests do not.

## Flags (all off by default)
| Flag | Effect |
|---|---|
| `BOOKLY_STORE=1` | Customer memory, recommendations, follow-ups, the last-contact record |
| `BOOKLY_ROUTER=1` | The intent router (Haiku) |
| `BOOKLY_ROUTER_ENGINE=jev` | Moves the router to Jev. Needs `BOOKLY_ROUTER=1` |
| `BOOKLY_JEV_BUDGET_USD` | Hard limit on Jev spend across runs on this machine (default 2.00) |

## Where things are
| What | Where |
|---|---|
| The agent loop | `bookly/agent.py` |
| The refund gate and the quote | `bookly/gate.py`, `bookly/state.py` |
| Tools | `bookly/tools.py` |
| Policy rules and policy text | `bookly/policy.py`, `bookly/data/policy.yaml`, `bookly/data/policy_text.yaml` |
| Every Jev question, threshold and truth table | `bookly/judgments.py` |
| The Jev client, request log and budget | `bookly/jev.py` |
| The store and what it holds | `bookly/store.py`, `memory.py`, `missions.py`, `contact.py`, `recommend.py` |
| Prompts | `bookly/prompts/`, `bookly/procedures/` |
| State machines, drawn | `docs/STATE_MACHINES.md` |

## Rules that must hold
1. **Money moves only through code.** Do not let a model output, a Jev answer or customer text reach `create_return` without the gate. Do not put the gate in a truth table.
2. **With the flags off, nothing changes.** `test_flags_off_prompt_and_tools_are_the_submitted_ones` pins the prompt and the tool list by hash. If it fails, the change touched the submitted agent.
3. **Jev judges, code decides, Sonnet writes.** A question asks for one judgment about language. The decision is a table in `bookly/judgments.py` with a row for the unsettled case. Do not ask Jev "what should happen".
4. **A failed Jev call is an error, never an answer.** It must not read as "no".
5. **Customer memory and the last-contact record hold values, never the customer's words.** The raw message goes only to `Store.audit`, for a person, and no model reads it. Nothing is judged or saved before an order and email verify.
6. **One wording file.** New questions, thresholds and tables go in `bookly/judgments.py`, with a test for every row.
7. **Write the expectation before a live run,** and report the result as it comes. Saved runs in `evals/results/` are never edited.
8. **Quote state names are read by the model.** The strings in `bookly/state.py` go into the agent's FACTS SO FAR text. Renaming one changes what the agent sees, and the flags-off hash test does not cover that text.

## Before you change a state machine
Read its section in `docs/STATE_MACHINES.md`. The states are strings and the moves are in more than one file. "Gaps found" lists what is known to be open.
