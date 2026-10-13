"""The orchestrator: a hand-written tool loop around the Anthropic Messages API.

One customer turn:
  1. Code reads the customer's reply to any confirmation card (gate.register_customer_reply).
  2. The customer message, then a "FACTS SO FAR" system message, are appended to the history.
  3. Loop: call the model; run every tool call it makes (each write passes the gate); send results back.
  4. On the final reply: strip the [[options: ...]] line into buttons, run the claim check,
     and attach the confirmation card if a quote is waiting for the customer.

The history is append-only: the model's responses go back whole (thinking blocks included),
and nothing already sent is edited. The system prompt and tools never change, so they stay cached.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import anthropic

from bookly import config
from bookly.backend import Backend
from bookly.gate import register_customer_reply
from bookly.kb import PolicyText
from bookly.policy import Policy
from bookly.state import Session
from bookly.tools import TOOLS, Toolbox, result_json

# USD per million tokens: input, output, cache read, cache write (5-minute). Estimates for reporting.
PRICES = {
    "claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50),
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5"}

OPTIONS_RE = re.compile(r"\[\[\s*options\s*:\s*(.+?)\]\]", re.I | re.S)
CLAIM_OBJECT = re.compile(r"\b(refund|refunded|return|label)\b", re.I)
CLAIM_DONE = re.compile(
    r"\b(has been|have been|was|is now|i've|i have|we've|we have|i just|i've just)\s+(\w+\s+)?"
    r"(issued|processed|created|submitted|initiated|approved|sent|emailed|completed|refunded|started)\b",
    re.I,
)
CLAIM_NOT_YET = re.compile(r"\b(once|after you|if you|when you|will|would|can|could|as soon as|until)\b", re.I)
# "No return or refund was created" is the opposite of a claim. Found as a false block in the first k=5 run.
CLAIM_NEGATED = re.compile(r"\b(no|not|nothing|never|neither|nor|haven't|hasn't|hadn't|didn't|wasn't|weren't|isn't|aren't|cancel\w*)\b", re.I)


def build_system_prompt() -> str:
    parts = [(config.PROMPTS / "system.md").read_text().strip(), "# Procedures"]
    for path in sorted(config.PROCEDURES.glob("*.md")):
        parts.append(path.read_text().strip())
    return "\n\n".join(parts)


def unbacked_claim(reply: str, session: Session) -> bool:
    """True if the reply says a refund/return happened but the ledger has no return in this conversation."""
    if any(a.kind == "return_created" for a in session.actions):
        return False
    for sentence in re.split(r"(?<=[.!?])\s+", reply):
        if CLAIM_NOT_YET.search(sentence):
            continue
        # Judge each clause on its own, so "issued, and there's no need to send it back" still counts.
        for clause in re.split(r"[,;:]|\b(?:and|so|but)\b", sentence):
            if CLAIM_OBJECT.search(clause) and CLAIM_DONE.search(clause) and not CLAIM_NEGATED.search(clause):
                return True
    return False


@dataclass
class TurnResult:
    reply: str
    options: list[str]
    card: dict | None
    handoff: dict | None
    events: list[dict]
    usage: dict


@dataclass
class Usage:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    cost_usd: float = 0.0
    api_calls: int = 0
    latency_ms: int = 0
    models_served: set = field(default_factory=set)

    def add(self, model: str, u, latency_ms: int) -> None:
        inp, out = u.input_tokens or 0, u.output_tokens or 0
        cr, cw = getattr(u, "cache_read_input_tokens", 0) or 0, getattr(u, "cache_creation_input_tokens", 0) or 0
        pi, po, pr, pw = PRICES.get(model, PRICES["claude-sonnet-5-5"])
        self.input += inp
        self.output += out
        self.cache_read += cr
        self.cache_write += cw
        self.cost_usd += (inp * pi + out * po + cr * pr + cw * pw) / 1_000_000
        self.api_calls += 1
        self.latency_ms += latency_ms
        self.models_served.add(model)

    def as_dict(self) -> dict:
        return {
            "input_tokens": self.input, "output_tokens": self.output, "cache_read_tokens": self.cache_read,
            "cache_write_tokens": self.cache_write, "cost_usd": round(self.cost_usd, 5), "api_calls": self.api_calls,
            "latency_ms": self.latency_ms, "models_served": sorted(self.models_served),
        }


class Agent:
    def __init__(
        self,
        backend: Backend | None = None,
        policy: Policy | None = None,
        client: anthropic.Anthropic | None = None,
        model: str = config.AGENT_MODEL,
        effort: str = config.AGENT_EFFORT,
    ):
        self.backend = backend or Backend.load()
        self.policy = policy or Policy.load()
        self.kb = PolicyText(self.policy)
        self.session = Session()
        self.toolbox = Toolbox(self.session, self.backend, self.policy, self.kb)
        self.client = client or config.make_client()
        self.model, self.effort = model, effort
        self.system = build_system_prompt()
        self.messages: list[dict] = []
        self.usage = Usage()
        self.use_fallbacks = model in FALLBACK_MODELS

    # ---- one API call -------------------------------------------------------------------
    def _call(self):
        kwargs = dict(
            model=self.model,
            max_tokens=config.AGENT_MAX_TOKENS,
            system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            messages=self.messages,
            output_config={"effort": self.effort},
            cache_control={"type": "ephemeral"},
        )
        t0 = time.monotonic()
        try:
            if self.use_fallbacks:
                resp = self.client.beta.messages.create(**kwargs, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
            else:
                resp = self.client.messages.create(**kwargs)
        except anthropic.BadRequestError as exc:
            if self.use_fallbacks and "fallback" in str(exc).lower():
                self.use_fallbacks = False  # account or model without server-side fallback: run without it
                self.session.log("note", text="server-side fallback unavailable; continuing without it")
                return self._call()
            raise
        latency = int((time.monotonic() - t0) * 1000)
        served = getattr(resp, "model", self.model)
        self.usage.add(served, resp.usage, latency)
        self.session.log("api_call", model=served, stop_reason=resp.stop_reason, latency_ms=latency,
                         input_tokens=resp.usage.input_tokens, output_tokens=resp.usage.output_tokens,
                         cache_read=getattr(resp.usage, "cache_read_input_tokens", 0) or 0)
        return resp

    # ---- one customer turn --------------------------------------------------------------
    def handle(self, text: str, button: str | None = None, quote_id: str | None = None) -> TurnResult:
        s = self.session
        s.turn += 1
        first_event = len(s.trace)
        usage_before = self.usage.as_dict()

        signal = register_customer_reply(s, text, button, quote_id)
        content = (text or "").strip()
        if button == "confirm" and not content:
            content = "[Customer pressed Confirm on the confirmation card]"
        elif button == "cancel" and not content:
            content = "[Customer pressed Cancel on the confirmation card]"
        s.log("customer", text=content, button=button, confirmation_signal=signal)

        self.messages.append({"role": "user", "content": content or "(empty message)"})
        self.messages.append({"role": "system", "content": s.facts_block()})

        reply, resp_final, replaced = "", None, False
        for step in range(config.MAX_TOOL_STEPS_PER_TURN + 1):
            try:
                resp = self._call()
            except (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError) as exc:
                # Retries are exhausted (the SDK retries twice). A 400 is a bug and is raised, not hidden.
                s.log("api_error", error=repr(exc)[:300])
                reply = self._code_handoff("tool_failure", f"The assistant service failed: {type(exc).__name__}.")
                break

            if resp.stop_reason == "tool_use" and step < config.MAX_TOOL_STEPS_PER_TURN:
                self.messages.append({"role": "assistant", "content": resp.content})
                results = []
                for block in resp.content:
                    if block.type != "tool_use":
                        continue
                    s.log("tool_call", tool=block.name, input=block.input)
                    result, is_error = self.toolbox.run(block.name, dict(block.input))
                    s.log("tool_result", tool=block.name, result=result, is_error=is_error)
                    item = {"type": "tool_result", "tool_use_id": block.id, "content": result_json(result)}
                    if is_error:
                        item["is_error"] = True
                    results.append(item)
                self.messages.append({"role": "user", "content": results})
                continue

            if resp.stop_reason == "tool_use":  # turn cap reached with tools still pending
                self.messages.append({"role": "assistant", "content": resp.content})
                self.messages.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": b.id, "is_error": True,
                     "content": result_json({"status": "error", "reason": "step_limit"})}
                    for b in resp.content if b.type == "tool_use"]})
                reply = self._code_handoff("tool_failure", "The agent hit its step limit for one turn.")
                break

            reply = "".join(b.text for b in resp.content if b.type == "text").strip()
            if resp.stop_reason == "refusal":
                s.log("refusal", stop_details=str(getattr(resp, "stop_details", None)))
                reply, replaced = self.toolbox.handoff("cannot_help", "The model declined to answer.")["message_for_customer"], True
            elif not reply:
                reply, replaced = "Sorry, I didn't catch that. Could you tell me a bit more?", True
            resp_final = resp
            break

        options: list[str] = []
        m = OPTIONS_RE.search(reply)
        if m:
            options = [o.strip() for o in m.group(1).split("|") if o.strip()]
            reply = OPTIONS_RE.sub("", reply).strip()

        if unbacked_claim(reply, s):
            s.log("claim_check", fired=True, original=reply)
            reply, replaced = self.kb.message("claim_correction"), True

        if resp_final is not None:
            self._append_final(resp_final, reply if replaced else None)

        card = None
        q = s.latest_quote()
        if q and q.status == "open" and q.decision.refundable and q.confirmation == "pending":
            if not q.presented:
                q.presented = True
                s.log("card_shown", quote_id=q.quote_id, card=q.card())
            card = q.card()

        s.log("agent", text=reply, options=options)
        after = self.usage.as_dict()
        turn_usage = {k: (round(after[k] - usage_before[k], 5) if isinstance(after[k], (int, float)) else after[k]) for k in after}
        return TurnResult(reply=reply, options=options, card=card, handoff=s.handoff, events=s.trace[first_event:], usage=turn_usage)

    def _append_final(self, resp, replace_with: str | None) -> None:
        """Append the final response whole. If code replaced the text the customer saw (claim correction,
        refusal, empty reply), swap it in for the model's text so the history matches what the customer
        read. This happens before the response is ever sent back, so nothing already sent is edited."""
        if replace_with is None:
            self.messages.append({"role": "assistant", "content": resp.content})
            return
        content, replaced = [], False
        for b in resp.content:
            if b.type == "text":
                if not replaced:
                    content.append({"type": "text", "text": replace_with})
                    replaced = True
                continue
            content.append(b)
        if not replaced:
            content.append({"type": "text", "text": replace_with})
        self.messages.append({"role": "assistant", "content": content})

    def _code_handoff(self, reason_code: str, summary: str) -> str:
        """A handoff the code makes on its own (service failure, step limit). Keeps the history valid."""
        result = self.toolbox.handoff(reason_code, summary)
        text = result["message_for_customer"]
        self.messages.append({"role": "assistant", "content": [{"type": "text", "text": text}]})
        return text
