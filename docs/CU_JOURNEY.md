# One customer, three visits, and a computer-use rep in the order console

**Result: 4 counted runs, 4 passed.** Runs 1 and 2 are below. Runs 3 and 4 came after later changes. Each run took about 62 seconds. Computer use cost $0.09 to $0.13 per run.

This demo follows one customer with one late package across three chat visits. Each part of the system has a visible job:

- **Memory.** The store keeps the follow-ups and how each visit ended, so the next visit starts from them.
- **Jev.** Jev is TypeSafe's decision model. It reads two things in the customer's words: whether the package arrived, and the mood.
- **Code.** Code decides entitlement from the delay facts, and code writes the reship request.
- **Computer use.** A Claude computer-use agent carries out the reship in a staff order console. It sees only screenshots and acts only with the mouse and keyboard.

The [first computer-use demo](CU_TICKET_AGENT.md) only typed a staff reply. Here, the computer-use agent does the one action that the chat agent cannot do.

## The rules this demo keeps

- **Delay facts decide entitlement. Mood changes only the handling.** A calm customer with the same order gets the same reship. An angry ending adds a priority flag, so a person follows up by email. When the console completes a priority reship, code opens a staff ticket for that follow-up, with a handoff summary built from stored facts, and the chat shows a "Handed to staff" note. The agent never tells the customer how they sounded, and the ticket, the summary and the note do not name the mood.
- **Code gates the action, not the model.** The chat agent has no reship tool. Code writes a `reship_request` only after four checks pass. The order console accepts a reship only for an order that has a pending request from code.
- **Everything is behind `BOOKLY_RESHIP=1`.** It also needs `BOOKLY_STORE=1`. With the flag off, the prompts, the tools, the backend snapshot and every existing test are unchanged, and `/admin` returns 404.

## The journey

Order BK-1020 has an estimated delivery date of Thursday, October 8, and a last tracking scan on Friday, October 9. Its total is $14.99, which is under the $100 value cap. "Lost" uses the existing `_likely_lost` rule: no tracking scan for 5 business days after the estimate. For this order, that day is Friday, October 16.

Code types every customer line. Code also clicks every clock button and the **New conversation, same store** button.

| Visit | Store date | Customer lines (scripted, read by Jev) | What Jev read (both runs) | What code decided (both runs) |
|---|---|---|---|---|
| 1 | Sat 10/10 | "Where is my order BK-1020? It was due on the 8th. My email is riley.morgan@example.com." then "This is ridiculous. I'm done waiting on you people." | Mood on the last line: angry (P = 0.91 and 0.93) | Late, not lost. Code opens follow-up M-0001 (kind `delay_watch`), due Monday 10/12. Stored mood: angry. |
| clock | Tue 10/13 | Code clicks **+1 day** three times. | | The scheduled check sends the M-0001 email ("running late, has it reached you?"). Two business days since the last scan: inside the window. |
| 2 | Tue 10/13 | "It's still not here and nothing has changed on the tracking. Order BK-1020, riley.morgan@example.com." then "No. I don't want to talk to anyone, I just want my damn book." | `not_arrived` 0.99. Mood on the last line: angry (P = 0.95 to 0.96) | The last contact ended unresolved and angry, so code chooses early escalation and the agent offers a person. Not lost yet, so M-0001 closes as `closed_still_missing` and M-0002 opens. The customer declines and leaves. No ticket. Stored mood: angry. |
| clock | Sat 10/17 | Code clicks **+1 day** four times. | | The M-0002 email is sent. Five business days since the last scan: lost. |
| 3 | Sat 10/17 | "Still nothing has arrived, and the tracking hasn't moved in a week. Order BK-1020, riley.morgan@example.com." | `not_arrived` 0.99 | Verified, lost, under the cap, no earlier reship: code writes RR-0001. The last visit ended angry, so code sets the priority flag and drops the chat offer of a person. The chat gives the code-written message: a replacement is requested, and it will confirm when it is sent. |
| console | Sat 10/17 | (between chat turns) | | The computer-use agent works RR-0001 in `/admin`. The console creates RS-1020-01. |
| 3, last turn | Sat 10/17 | "Okay. Has it actually been sent?" | | The chat relays the confirmation that code wrote, word for word (below). |

The confirmation in both runs, written by code from the reship record and the follow-up dates:

> Your replacement copy of The Hobbit is on its way (reship RS-1020-01). You first told us about this on Saturday, October 10, and again on Tuesday, October 13. A member of our team will also check in with you by email.

### One change to the first script's wording

The first script's decline line was "No. I don't want to talk to anyone, I just want my book." Jev read it as concerned, not angry, on two calls: P(angry) was 0.16 and 0.17. The mood bar is 0.6, and it did not change. So in the one smoke run, the stored mood dropped to "concerned", and the priority beat failed. The scripted line now ends "my damn book". Jev reads that at P(angry) 0.96. The smoke run is not counted in the results.

## What was built

| File | What it does |
|---|---|
| `bookly/data/orders.json` | Adds order BK-1020. |
| `bookly/missions.py` | Adds the `delay_watch` follow-up kind and its email. In `read_reply`, a `delay_watch` follow-up goes to its own branch. The lost-package and refund paths are unchanged. |
| `bookly/reship.py` | New. Opens a `delay_watch` follow-up for a late, not-yet-lost package. Applies the reply: still missing, or lost. Holds the chat-side reship gate and the FACTS SO FAR lines. |
| `bookly/backend.py` | Adds reship requests, reships and a log of every console POST. `Backend.reship` rejects an order with no pending request, a second reship, an order over the cap, and a reason code that does not match the request. |
| `bookly/tools.py` | Calls the above when the flag is on. If the model tries a `lost_package` hand-off after code has requested a reship, code answers "not needed". The `last_contact` line is now attached after the follow-up reads, so a reship request can replace the person offer. |
| `app/server.py`, `app/static/admin.html` | The order console at `/admin`: a work queue, order search, an order page, an **Actions** menu with **Reship Order**, a required reason code and a confirmation pop-up. It is deliberately old-style, and it is labelled as simulated. |
| `app/static/index.html` | Shows reship requests, reships and the code's reship decisions in the existing panels. |
| `evals/cu_journey.py` | Drives the three visits with Playwright, runs computer use between chat turns, checks the store after each beat and records the videos. |
| `evals/cu_ticket_agent.py` | `cu_loop` and `run_action` now take a system prompt and a screenshot function. Their defaults are the old ones. Also fixes `post()`: a `noqa` comment had swallowed its `data` and `method` arguments. |
| `tests/test_reship.py` | 17 tests: `delay_watch`, the whole journey with a scripted model and Jev, the staff ticket, its handoff summary and the chat note for a priority reship (and none without the flag), the console gate (no request, repeat, over the cap, wrong reason), the chat gate over the cap, the hand-off guard, and flag-off behavior. |

### The checks after each run

Code reads the store through `POST /api/session`, which returns a snapshot and changes nothing. A run passes only when every check passes:

- **Visit 1.** The stored mood is angry. One `delay_watch` is scheduled. No ticket is open.
- **Clock 1.** Today is 2026-10-13, and the follow-up email was sent.
- **Visit 2.** Code chose `early_escalation`. Jev read "not arrived" at 0.7 or more, and code decided `still_missing`. The first follow-up closed and a second one is scheduled. The stored mood is still angry. There is no ticket and no reship request.
- **Clock 2.** Today is 2026-10-17, and the second follow-up email was sent.
- **Visit 3.** There is one pending `reship_request`, for BK-1020. The priority flag is set. There is no lost-package ticket.
- **Console.** There is exactly one reship, on BK-1020. The server saw exactly one console POST, and the console page sent exactly one. The agent ended with DONE.
- **Confirmation.** The chat reply has the reship id and both cited dates.
- **Handoff (run 4 on).** The `reship_followup` ticket carries the exact handoff summary below, and the chat shows one "Handed to staff" note.

## How to run it

```bash
uv sync
uv run playwright install chromium       # once
BOOKLY_STORE=1 BOOKLY_RESHIP=1 uv run uvicorn app.server:app --port 8021
# in a second terminal:
uv run python -m evals.cu_journey --base-url http://localhost:8021 --runs 2
```

It needs `ANTHROPIC_API_KEY` and `TYPESAFE_API_KEY` in `.env`. The computer-use settings and limits are the same as in the first demo ([CU_TICKET_AGENT.md](CU_TICKET_AGENT.md)): 25 actions per run, and a $3.00 spend cap summed across every run on this machine. The server's Jev budget guard stays on.

## Results (2026-11-17)

**2 runs: 2 passed.**

| Run | Computer-use actions | Model requests | Computer-use cost | Jev cost | Time |
|---|---|---|---|---|---|
| 1 | 15 | 7 | $0.132 | $0.0006 | 62 s |
| 2 | 15 | 7 | $0.088 | $0.0006 | 63 s |

Both runs took the same path in the console:

1. Click **Order Search**.
2. Click the search box, type BK-1020 and click **Search**.
3. Open **Actions**, then choose **Reship Order**.
4. Select `lost_in_transit`, then click **Submit Reship**.
5. Click **OK** in the pop-up, then take a screenshot of the result.

The agent took a screenshot after each step.

**Cost.** Computer use cost $0.22 for the two counted runs and $0.135 for the smoke run. Jev cost about $0.0006 per run, read from the Jev call log. Testing four wordings of the decline line cost less than $0.001 more. The chat agent behind the page (Claude Sonnet 5.5) also ran. This script does not measure that cost.

**Videos.** Playwright recorded the chat page and the console page at the same time, as two pages in one browser context. The script then combines them into one MP4. The repo does not keep the run 1 and run 2 videos. Each combined MP4 was about 0.9 MB, and the raw WebM recordings were 2.5 to 17.8 MB each.

The combined video shows the chat page, then the console page while computer use runs, then the chat page again. It is one timeline, and no time is cut. The only edit is which recording is shown. The two raw recordings are unedited.

## Run 3 (2026-11-18): the staff escalation is visible

Before this change, the only sign of the priority flag was one sentence in the chat. Now code also does two things:

- **A staff ticket.** When `Backend.reship` completes a reship that has the priority flag, it opens one ticket with the existing ticket mechanism. The ticket has kind `reship_followup`, the priority flag, the reship id, the request id and the earlier contact dates. It shows in the "Bookly's systems (simulated)" panel. The store panel shows its id on the closed follow-up. A reship without the flag opens no ticket.
- **A grey system note.** On the chat turn whose reply relays the confirmation, code adds one note in the same style as the clock notes. In run 3 it read "Escalated to staff · priority follow-up · ticket T-0001 · reship RS-1020-01". Code shows it once per reship. The model does not write it.

With `BOOKLY_RESHIP` off, nothing changes: the chat response has no `notes` key. The journey now also checks that exactly one priority `reship_followup` ticket exists after the console step, and that the note follows the confirmation.

**Result: 1 counted run, passed.** Every check passed, including the two new ones. Computer use took 15 actions and 7 model requests, for $0.098. Jev cost $0.0006. The run took 63 seconds. One earlier attempt on the same code failed in visit 1 and is not counted: the chat model offered a person at once and opened a ticket. That beat does not use the new code. The new ticket and note were correct in that attempt too. It cost $0.131 in computer use.

The repo does not keep the run 3 video. It was built the same way as the run 1 and run 2 videos.

## Run 4 (2026-11-18): a self-contained handoff for staff

Run 3 made the escalation visible, but the ticket row and the note looked like every other row and note. Now:

- **A handoff summary on the ticket.** `Backend.reship` stores `payload.handoff` on the priority `reship_followup` ticket. Code builds it from stored records only, with no model text. The per-visit facts come from the `delay_watch` follow-ups, the prior contact record and the order. Code writes them on the reship request in `reship.contact_facts`. "Declined a person" needs two stored facts: code offered a person on that day (a new `person_offered` note in the follow-up history), and that visit opened no hand-off ticket. The summary never names the mood or a Jev score. In run 4 it read:

  > **BK-1020 · Riley Morgan · Priority follow-up**
  > Contacts: 10/10 — 2 days late · 10/13 — still missing; declined a person · 10/17 — lost (no scan since 10/9)
  > Done: Reship RS-1020-01 issued in the order console on 10/17.
  > Next: Confirm the replacement shipped, then check in with the customer.

- **A distinct card and note.** The systems panel draws this ticket as a "HANDOFF TO STAFF" card: an amber left border, a light amber background, a bold header, then Contacts, Done and Next, with the staff reply box under it. The chat note uses the same accent and reads "↪ Handed to staff · Priority follow-up · ticket T-0001 · reship RS-1020-01". The colors are tokens (`--handoff`, `--handoff-bg`, `--handoff-ink`) with light and dark values. Other tickets and notes keep their old look. The `notes` items in the chat response are now objects (`kind`, `label`, `text`).

With `BOOKLY_RESHIP` off, nothing changes. A reship without the priority flag still opens no ticket, so there is no card and no note.

**Result: 1 run, 1 attempt, passed.** Every check passed, including the new handoff check. Computer use took 15 actions and 7 model requests, for $0.130. Jev cost $0.0006. The run took 62 seconds.

Video: [`docs/media/journey.mp4`](media/journey.mp4) (0.9 MB, 64 s). It is the combined video of run 4. The repo does not keep the raw WebM recordings or the result JSON. The combined video now holds its last frame for 3 more seconds (`tpad` in `combine`), and the harness scrolls the handoff card into view before the end, so the card and the note can be read.

## Limits, stated plainly

- **The customer's wording is scripted.** Code types fixed lines. One line was changed from the first script so that Jev reads it as angry, as described above. A model-played customer was not tried.
- **The clock is a button.** Code clicks **+1 day**. Nothing in the demo runs on its own schedule.
- **Code writes the citation of the earlier visits.** The dates come from the follow-up records. The chat model only relays the sentence.
- **The console is a simulated page made for the demo.** It is not a real legacy system. It has no login, it runs on the same local server, and a banner on the page says that it is simulated.
- **The chat agent has no reship tool.** The console accepts a reship only when code approved it first. Computer use does the clicks. It does not decide entitlement.
- **Code times the computer use.** The harness starts computer use between chat turns, because a chat turn holds the store lock. The system does not start it on its own.
- **Four counted runs on one scripted journey.** That shows that the path works. It is not a reliability rate.
- **The task was easy to see.** One request was in the queue, and every control was on the first screen.
