# A computer-use support rep works one ticket through the screen

**Result: 2 runs, 2 passed.** Each run cost about $0.06 in computer-use tokens and took about 37 seconds.

This is a small demo of one claim. A Claude computer-use agent can act as a support rep in an existing web app. It works only through the screen. It does not call the app's API.

## What it does

`evals/cu_ticket_agent.py` runs one scenario. It is test 3 from the store experiment ([JEV.md](JEV.md)): a lost package.

1. **Setup, done by code.** The script resets the store through `POST /api/store/reset`. It opens the page in Chromium with Playwright and types the customer's message into the chat: order BK-1013 has not arrived, email nina.patel@example.com. The support agent behind the chat opens ticket T-0001. If the agent only offers a person, the script types an acceptance. In every recorded run, the agent handed off in its first reply, so no acceptance was needed. The script checks that T-0001 exists before it goes on.
2. **The computer-use agent.** Claude Opus 5.5 gets the computer use toolset (`computer_toolset_20260801`). It sees only PNG screenshots of the page, at 1600 × 1000 pixels. It acts only with clicks, typing, keys, scrolling and waits, which Playwright runs at the same pixel coordinates. Its task is to find the open ticket in the "Bookly's systems (simulated)" panel, read the chat, type a reply in the ticket's reply box, and press **Staff replied**. The reply reaches the server only through that button's own request from the page.
3. **Checks, done by code.** The script reads the store through `POST /api/session`, which returns a snapshot and changes nothing. A run passes when all of these are true:
   - T-0001 has a reply date.
   - T-0001 has stored reply text of 20 characters or more that names the order or the package.
   - The page sent exactly one `POST /api/ticket/answer`.
   - The agent ended with a message that starts with DONE.
4. **Return visit, scripted.** The script clicks **New conversation, same store** and the customer asks about the package again. The ticket row in the systems panel shows the stored reply text.

Every run records one raw Playwright video, with no editing, of setup, the agent's actions and the return visit.

### The app change this needed

Before this change, the staff control was one button. It recorded that "a person replied" and stored no text. A support rep needs somewhere to write, so the change adds:

- An optional reply box above the **Staff replied** button (`app/static/index.html`).
- An optional `reply` field on `POST /api/ticket/answer` (`app/server.py`).
- A `staff_reply` field on the ticket (`bookly/backend.py`).

An empty box keeps the old one-click behavior. The ticket row shows the reply text after it is sent. A test in `tests/test_server_store.py` covers both paths.

## How to run it

```bash
uv sync                                  # Playwright is a dev dependency
uv run playwright install chromium       # once
BOOKLY_STORE=1 uv run uvicorn app.server:app --port 8021
# in a second terminal:
uv run python -m evals.cu_ticket_agent --base-url http://localhost:8021 --runs 2
```

It needs `ANTHROPIC_API_KEY` in `.env`. Jev rows also need `TYPESAFE_API_KEY`. Add `--headed` to watch the browser.

Settings:

| Variable | Default | What it does |
|---|---|---|
| `BOOKLY_CU_MODEL` | `claude-opus-5-5` | Computer-use model |
| `BOOKLY_CU_EFFORT` | `medium` | Effort for that model |
| `BOOKLY_CU_BUDGET_USD` | `3.00` | Computer-use spend cap, summed across every run on this machine |

Limits that the code enforces:

- **Actions.** A run stops at 25 computer actions. Screenshots count as actions.
- **Spend.** The script estimates the cost of each request from its token usage and writes it to `logs/cu_spend.jsonl`, which is gitignored. It stops before a request once the total reaches the cap.
- **Jev.** The server keeps its own Jev budget guard (`BOOKLY_JEV_BUDGET_USD`).

Each request resends the earlier screenshots, and prompt caching reads them back at the cache price.

Outputs:

- **Videos:** `docs/media/cu_ticket_<run>.webm`.
- **Results:** `evals/results/cu_ticket_agent/<run>.json`. Each file holds the action log, the stored reply, the checks and the cost.

The repo does not keep the recorded videos or the result files from these runs. Each raw video was about 9.8 MB.

## Results (2026-11-17)

**2 runs: 2 passed.**

| Run | Actions | Model requests | Computer-use cost | Time |
|---|---|---|---|---|
| 1 | 5 | 2 | $0.057 | 36 s |
| 2 | 5 | 2 | $0.057 | 37 s |

Both runs took the same path:

1. Click the reply box.
2. Type the reply.
3. Click **Staff replied**.
4. Wait one second.
5. Take a screenshot to check the result.

The reply stored on T-0001 in run 1:

> Hi Nina, I'm sorry your order BK-1013 hasn't arrived and that tracking stopped updating. Since it is well past the estimated delivery date of Sept 23, we're treating the package as lost. We will arrange a replacement or a refund for you, whichever you prefer, so please reply to let us know. Bookly support

The reply stored in run 2 says the same thing in different words.

Purple "Jev ·" trace rows appeared in both recorded videos, for example `Jev · remember · lasting 0.01 ...`.

Before the two runs, one smoke run with the same code also passed: 5 actions, $0.056. It is not counted above.

**Cost.** Computer-use spend for all three runs was $0.17 in total. The support agent behind the chat (Claude Sonnet 5.5) and Jev also ran during setup and the return visit. This script does not measure that spend.

## Limits, stated plainly

- **One scenario, two runs.** That is not enough to give a pass rate. It shows that the path works, not how often it works.
- **The staff panel is simulated.** It is a reply box in the same demo page, not a real contact-center desktop. A real desktop has queues, search, more than one window and login. None of that is tested here.
- **The task was easy to see.** Only one ticket was open, and the reply box was on the first screen, so the agent needed no scrolling or searching.
- **Code did the setup.** The model did not open the ticket. It only answered the ticket.
- **The return visit does not use the reply.** The support agent on the next visit reads that a person replied, but not what the person wrote. In both runs it opened a new ticket, T-0002, for the same package. The reply text shows only in the systems panel. The script records this, and it is not a pass condition.
- **The content check is light.** It checks that a reply exists, has 20 characters or more, and names the order or the package. No grader judged the tone or the accuracy. The two replies above are the evidence.
- **The agent works on the local page only.** It ran in a headless browser on a local server, with no other sites and no credentials.
