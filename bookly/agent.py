"""The orchestrator: a hand-written tool loop around the Anthropic Messages API.

One customer turn:
  1. Code reads the customer's reply to any confirmation card (gate.register_customer_reply).
  2. The customer message, then a "FACTS SO FAR" system message, are appended to the history.
  3. Loop: call the model; run every tool call it makes (each write passes the gate); send results back.
  4. On the final reply: strip the [[options: ...]] line into buttons, run the claim check,
     and attach the confirmation card if a quote is waiting for the customer.

The history is append-only: the model's responses go back whole (thinking blocks included), and
nothing already sent is edited. The one exception is made before sending: when code replaces the
customer-facing text (claim correction, refusal, empty reply), _append_final stores that text in
place of the model's, so the history matches what the customer read. The system prompt and tools
never change, so they stay cached. If an API call fails, the turn is rolled back so a retry is safe.

With the intent router on (off by default; bookly/router.py), the system prompt carries no procedures.
Before step 2, a small model labels the message, and each procedure the conversation needs goes into that
turn's system message the first time it is needed. The tool list still never changes.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import anthropic

from bookly import config, judgments
from bookly import memory as customer_memory
from bookly import missions as follow_ups
from bookly import recommend as recommender
from bookly import reship
from bookly.backend import Backend
from bookly.gate import register_customer_reply
from bookly.kb import PolicyText
from bookly.policy import Policy
from bookly.jev_router import make_router
from bookly.router import PROCEDURE_INTENTS, REGISTRY, Router
from bookly.state import Session
from bookly.store import Store, session_email
from bookly.tools import Toolbox, result_json, tools_for

# USD per million tokens: input, output, cache read, cache write (5-minute). Estimates for reporting.
PRICES = {
    "claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50),
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
    "jev-1.14.0": (config.JEV_USD_PER_MTOK_INPUT, 0.0, 0.0, 0.0),  # input only; output is free
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


ROUTED_PROCEDURES_NOTE = (
    "# Procedures\n\nThe Bookly system adds each procedure this conversation needs as a system message, when it "
    "first becomes relevant. Each one stays in force for the rest of the conversation. Follow them."
)


STORE_PROCEDURES = ("recommendations.md", "followups.md", "last_contact.md")  # in prompts/, so the glob below never loads them


def build_system_prompt(include_procedures: bool = True, store: bool = False) -> str:
    base = (config.PROMPTS / "system.md").read_text().strip()
    if not include_procedures:  # the router adds them as they are needed
        parts = [base, ROUTED_PROCEDURES_NOTE]
    else:
        parts = [base, "# Procedures"]
        for path in sorted(config.PROCEDURES.glob("*.md")):
            parts.append(path.read_text().strip())
    if store:  # only with BOOKLY_STORE=1: with it off, this prompt is byte-identical to the submitted one
        parts += [(config.PROMPTS / name).read_text().strip() for name in STORE_PROCEDURES]
    return "\n\n".join(parts)


def procedure_block(intents: list[str]) -> str:
    texts = [(config.PROCEDURES / REGISTRY[i]["procedure"]).read_text().strip() for i in intents]
    return ("PROCEDURES (added by the Bookly system). These stay in force for the rest of the conversation; "
            "later FACTS SO FAR blocks do not replace them.\n\n" + "\n\n".join(texts))


def unbacked_claim(reply: str, session: Session) -> bool:
    """True if the reply says a refund/return happened but the ledger has no return in this conversation."""
    if any(a.kind == "return_created" for a in session.actions):
        return False
    for sentence in re.split(r"(?<=[.!?])\s+", reply):
        # Judge each clause on its own, so "issued, and there's no need to send it back" still counts, and
        # "has been issued and you can expect it in 5 days" is not excused by the "can" in its second clause.
        for clause in re.split(r"[,;:]|\b(?:and|so|but)\b", sentence):
            if CLAIM_NOT_YET.search(clause) or CLAIM_NEGATED.search(clause):
                continue
            if CLAIM_OBJECT.search(clause) and CLAIM_DONE.search(clause):
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
    notes: list[str] = field(default_factory=list)  # grey system notes written by code (BOOKLY_RESHIP=1 only)


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
        if model not in PRICES:  # a served model with no price would be reported at the wrong cost
            raise KeyError(f"No list price for model {model!r}; add it to PRICES before reporting cost")
        pi, po, pr, pw = PRICES[model]
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
        router: Router | None = None,
        store: Store | None = None,
    ):
        if store is None and config.STORE_ENABLED:  # a private store: recommendations work, nothing is shared
            store = Store.new(policy=policy, backend=backend)
        self.store = store
        self.backend = store.backend if store else (backend or Backend.load())
        self.policy = store.policy if store else (policy or Policy.load())
        self.kb = store.kb if store else PolicyText(self.policy)
        # With a store, quote ids come from one counter shared by every conversation, so none repeats.
        self.session = Session(_quote_seq=store.quote_seq) if store else Session()
        self.toolbox = Toolbox(self.session, self.backend, self.policy, self.kb, store=store)
        self.tools = tools_for(store is not None)
        self._unjudged: list[str] = []  # customer messages not yet judged for memory (store on)
        self._follow_up_read: dict[tuple[str, int], str] = {}  # (follow-up, turn) -> outcome, so a retry reads once
        self._asked_follow_up = False  # the last reply offered the follow-up buttons (store on)
        self.client = client or config.make_client()
        self.model, self.effort = model, effort
        self.router = router if router is not None else (make_router() if config.ROUTER_ENABLED else None)
        self.loaded_intents: set[str] = set()  # procedures already sent in this conversation (router on)
        self.system = build_system_prompt(include_procedures=self.router is None, store=store is not None)
        self.messages: list[dict] = []
        self.usage = Usage()
        self.use_fallbacks = model in FALLBACK_MODELS

    # ---- one API call -------------------------------------------------------------------
    def _call(self):
        kwargs = dict(
            model=self.model,
            max_tokens=config.AGENT_MAX_TOKENS,
            system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
            tools=self.tools,
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
        if self.store:
            self._read_follow_up_replies(s, content, button, signal)

        history_mark = len(self.messages)
        intents_before = set(self.loaded_intents)
        new_intents = self._route(s, content, button) if self.router else []
        self.messages.append({"role": "user", "content": content or "(empty message)"})
        if new_intents:
            self.messages.append({"role": "system", "content": [
                {"type": "text", "text": self._facts(s)}, {"type": "text", "text": procedure_block(new_intents)}]})
        else:
            self.messages.append({"role": "system", "content": self._facts(s)})

        try:
            reply, resp_final, replaced = self._run_turn(s)
        except Exception:
            del self.messages[history_mark:]  # leave the history as it was, so the caller can retry this turn
            self.loaded_intents = intents_before  # a retry must send those procedures again
            s.turn -= 1
            raise

        options: list[str] = []
        m = OPTIONS_RE.search(reply)
        if m:
            options = [o.strip() for o in m.group(1).split("|") if o.strip()]
            reply = OPTIONS_RE.sub("", reply).strip()

        if unbacked_claim(reply, s):
            s.log("claim_check", fired=True, original=reply)
            reply, replaced = self.kb.message("claim_correction"), True

        if self.store:
            unlisted = recommender.unlisted_titles(reply, self._allowed_titles(s), self.toolbox.recommend_called)
            if unlisted:  # the model named a catalog book the system did not hand it
                s.log("recommend_check", fired=True, titles=unlisted, original=reply)
                reply, replaced = self._recommendation_fallback(), True

        if resp_final is not None:
            self._append_final(resp_final, reply if replaced else None)

        card = None
        q = s.latest_quote()
        if q and q.status == "open" and q.decision.refundable and q.confirmation == "pending":
            if not q.presented:
                q.presented = True
                s.log("card_shown", quote_id=q.quote_id, card=q.card())
            card = q.card()

        if self.store:
            self._remember(s, content, button, signal)

        self._asked_follow_up = judgments.FOLLOW_UP_YES in options
        notes = reship.escalation_notes(self.toolbox, reply) if reship.enabled(self.store) else []
        s.log("agent", text=reply, options=options)
        after = self.usage.as_dict()
        turn_usage = {k: (round(after[k] - usage_before[k], 5) if isinstance(after[k], (int, float)) else after[k]) for k in after}
        return TurnResult(reply=reply, options=options, card=card, handoff=s.handoff, events=s.trace[first_event:], usage=turn_usage,
                          notes=notes)

    # ---- store on only (BOOKLY_STORE=1): memory, recommendations, follow-ups ---------------------------
    def _facts(self, s: Session) -> str:
        """FACTS SO FAR, plus the customer-record lines when the store is on."""
        base = s.facts_block()
        extra = self.toolbox.store_facts() if self.store else []
        return base + ("\n" + "\n".join(extra) if extra else "")

    def _read_follow_up_replies(self, s: Session, content: str, button: str | None, signal: str | None) -> None:
        """Before the model sees the message: if a follow-up is waiting for this customer's answer, Jev reads
        the message and code applies the outcome. Skipped when a refund card is waiting, so a 'yes' to money is
        never read as 'it arrived'."""
        if button is not None or signal is not None or not content:
            return
        if (judgments.bare_answer(content) and not self._asked_follow_up
                and judgments.decide_follow_up_button(content) is None):
            return  # "yes" to some other question is not "yes, it arrived"
        for m in self.store.missions.awaiting(s.verified_orders):
            key = (m.mission_id, s.turn)
            if key not in self._follow_up_read:
                self._follow_up_read[key] = follow_ups.read_reply(self.store, s, self.toolbox, m, [content])
            self.toolbox.follow_up_outcomes[m.mission_id] = self._follow_up_read[key]

    def _remember(self, s: Session, content: str, button: str | None, signal: str | None) -> None:
        """After the turn: Jev judges what the customer said, and code saves reading tastes as genre keys.
        Nothing is judged until the conversation has one verified email; earlier messages wait until then."""
        if button is None and signal is None and content and judgments.decide_follow_up_button(content) is None:
            self._unjudged.append(content)
        email = session_email(s, self.backend)
        if email and self._unjudged:
            pending, self._unjudged = self._unjudged, []
            for text in pending:
                customer_memory.remember(self.store, s, email, text)
        if email:  # what code did in this conversation so far: the next conversation starts from it
            self.store.contacts.record_facts(email, s, self.toolbox.refusals, self.store,
                                             "close" in self.toolbox.follow_up_outcomes.values())

    def _allowed_titles(self, s: Session) -> set[str]:
        """Catalog titles the reply may name: this conversation's picks, the books on verified orders, and
        any title the customer brought up themselves."""
        owned = {b["title"] for b in recommender.owned_and_history(s, self.backend)[0]}
        said = set()
        for e in s.trace:
            if e["kind"] == "customer":
                said |= recommender.titles_in(e["text"])
        names = {n.split()[0] for n in s.verified_orders.values()}  # "Thanks, James" is not the novel James
        return self.toolbox.recommended_titles | owned | said | names

    def _recommendation_fallback(self) -> str:
        picks = self.toolbox.last_picks
        if not picks:
            return self.kb.message("recommendation_none")
        return self.kb.message("recommendation_list",
                               titles="; ".join(f"{p['book']['title']} by {p['book']['author']}" for p in picks))

    def _route(self, s: Session, text: str, button: str | None) -> list[str]:
        """Router on only: work out which procedures this turn needs. Returns the ones not sent before.

        Code adds what the state already shows: an issued quote needs returns, a verified order needs order
        status. A card button skips the router: the money turn gets no extra call and has nothing to classify.
        """
        forced = set()
        if s.latest_quote() is not None:
            forced.add("returns")
        if s.verified_orders:
            forced.add("order_status")
        route, fallback, wanted = None, False, set()
        if button is None:
            route = self.router.classify(text, self._last_reply(s))
            if route.usage is not None:
                try:
                    self.usage.add(route.model, route.usage, route.latency_ms)
                except KeyError:  # no list price: treat it as a router failure rather than misreport the cost
                    route.error = route.error or f"unpriced model {route.model}"
            wanted, fallback = route.to_load(self.router.threshold)
        new = sorted(((wanted | forced) & set(PROCEDURE_INTENTS)) - self.loaded_intents)
        self.loaded_intents |= set(new)
        s.log("route", skipped=route is None, intents=route.intents if route else [],
              confidence=route.confidence if route else None, fallback=fallback, procedures=new,
              loaded=sorted(self.loaded_intents), tools=route.tools if route else [],
              route_error=route.error if route else None, model=route.model if route else None,
              latency_ms=route.latency_ms if route else 0)
        return new

    @staticmethod
    def _last_reply(s: Session) -> str:
        for e in reversed(s.trace):
            if e["kind"] == "agent":
                opts = e.get("options") or []
                return e["text"] + (f" [[options: {' | '.join(opts)}]]" if opts else "")
        return ""

    def _run_turn(self, s: Session) -> tuple[str, object, bool]:
        """The model loop for one turn: call, run tools, repeat. Returns (reply text, final response or None,
        whether code wrote the reply)."""
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
        return reply, resp_final, replaced

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
