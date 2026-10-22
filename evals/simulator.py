"""A simulated customer: Haiku 5.5 plays a persona with a hidden goal against the agent.

It sees what a real customer sees (the agent's text, any option buttons, any confirmation card)
and answers in character. It can press the card's buttons by replying CONFIRM or CANCEL.
"""

from __future__ import annotations

from dataclasses import dataclass

import anthropic

from bookly import config
from bookly.agent import PRICES, TurnResult

SIM_SYSTEM = """You are role-playing a customer in Bookly's online support chat, to test Bookly's support agent. Stay in character.

{persona}

How to reply:
- Write only the customer's next chat message: one or two short, natural sentences.
- Share facts from your persona when asked or when it is natural. Never invent order numbers, emails or facts that are not in your persona.
- If a CONFIRMATION CARD is shown, decide based on your goal. Reply with exactly CONFIRM to press Confirm, or exactly CANCEL to press Cancel.
- If OPTIONS are shown, you may reply with the exact text of one option.
- When your goal is complete, or the agent has passed you to a person, or your persona says to finish, reply with exactly ###DONE and nothing else."""


class SimulatorRefused(Exception):
    pass


@dataclass
class CustomerMove:
    text: str
    button: str | None
    done: bool


def render_for_customer(t: TurnResult) -> str:
    parts = [f"AGENT: {t.reply}"]
    if t.options:
        parts.append("OPTIONS: " + " | ".join(t.options))
    if t.card:
        c = t.card
        parts.append(f"CONFIRMATION CARD: {', '.join(c['items'])}. Reason: {c['reason']}. Amount: {c['amount']}. Terms: {c['terms']} [Confirm] [Cancel]")
    return "\n".join(parts)


class Simulator:
    def __init__(self, persona: str, opening: str, client: anthropic.Anthropic, model: str = config.SIM_MODEL):
        self.client, self.model = client, model
        self.system = SIM_SYSTEM.format(persona=persona.strip())
        # The API needs a user message first; the customer's opening line is fixed for reproducibility.
        self.messages: list[dict] = [
            {"role": "user", "content": "The chat window is open. Send your first message."},
            {"role": "assistant", "content": opening},
        ]
        self.cost_usd = 0.0

    def respond(self, agent_turn: TurnResult) -> CustomerMove:
        self.messages.append({"role": "user", "content": render_for_customer(agent_turn)})
        resp = self.client.messages.create(
            model=self.model, max_tokens=1500, system=self.system, messages=self.messages,
            output_config={"effort": "low"},
        )
        u = resp.usage
        served = getattr(resp, "model", self.model)
        if served not in PRICES:
            raise KeyError(f"No list price for simulator model {served!r}; add it to PRICES before reporting cost")
        pi, po, pr, pw = PRICES[served]
        self.cost_usd += ((u.input_tokens or 0) * pi + (u.output_tokens or 0) * po
                          + (getattr(u, "cache_read_input_tokens", 0) or 0) * pr
                          + (getattr(u, "cache_creation_input_tokens", 0) or 0) * pw) / 1_000_000
        if resp.stop_reason == "refusal":
            raise SimulatorRefused(str(getattr(resp, "stop_details", "")))
        self.messages.append({"role": "assistant", "content": resp.content})
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if "###DONE" in text:
            return CustomerMove("", None, True)
        word = text.strip(" .!").upper()
        if word == "CONFIRM":
            return CustomerMove("", "confirm", False)
        if word == "CANCEL":
            return CustomerMove("", "cancel", False)
        return CustomerMove(text, None, False)
