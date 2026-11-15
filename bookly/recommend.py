"""Recommend from history: books a customer may like, from a small mock catalog.

Who does what:
- Code filters: in stock, not already owned, not in a genre the customer said they dislike.
- Code checks genre matches (an exact lookup) and ranks.
- Jev answers one question per remaining candidate: would a reader of her books also choose this one?
- The conversational model words the reply, and may name only the titles this module returned. A check in
  the orchestrator enforces that (unlisted_titles).

Privacy: the history is the books on the orders verified in THIS conversation. Another order under the same
email is not used until the customer verifies it too.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache

from bookly import config, judgments
from bookly.jev import JevError


@lru_cache(maxsize=1)
def catalog() -> tuple[dict, ...]:
    return tuple(json.loads(config.CATALOG_PATH.read_text())["books"])


def catalog_entry(order_title: str) -> dict | None:
    """An order line such as 'Atomic Habits (ebook)' matches the catalog title 'Atomic Habits'."""
    for book in catalog():
        if order_title == book["title"] or order_title.startswith(book["title"] + " ("):
            return book
    return None


def owned_and_history(session, backend) -> tuple[list[dict], list[dict]]:
    """(books the customer owns, books that count as taste). A change-of-mind return is owned, not taste."""
    owned, history = [], []
    for order_id in session.verified_orders:
        order = backend.orders[order_id]
        regretted = {i for rec in backend.ledger if rec.order_id == order_id and rec.reason == "changed_mind"
                     for i in rec.item_ids}
        for item in order.items:
            book = catalog_entry(item.title)
            if book is None:
                continue
            owned.append(book)
            if item.item_id not in regretted:
                history.append(book)
    return owned, history


def recommend(store, session, backend, email: str | None, stated_genres: list[str]) -> tuple[dict, list[dict]]:
    """Returns (tool result for the model, the picks). Never raises."""
    memory = store.memory.get(email)
    stated = {g for g in stated_genres if g in judgments.GENRES} | set(memory.likes if memory else ())
    disliked = set(memory.dislikes if memory else ())
    stated -= disliked
    owned, history = owned_and_history(session, backend)
    owned_ids = {b["book_id"] for b in owned}
    candidates = [b for b in catalog()
                  if b["in_stock"] and b["book_id"] not in owned_ids and not (set(b["genres"]) & disliked)]

    if not history and not stated:
        return {"status": "needs_input",
                "next_step": "Ask what kinds of books the customer enjoys. You can also offer to look at a past "
                             "order if they give its order number and email."}, []

    probs, note, latency = None, None, 0
    if history:
        try:
            answer = store.jev.ask("recommend", judgments.recommend_state(history), judgments.fit_questions(candidates))
            probs, latency = answer.probs, answer.latency_ms
        except JevError as exc:
            note = str(exc)[:200]  # an error is not an answer: fall back to the genre match alone, if there is one
    picks = judgments.decide_recommend(candidates, probs, stated)
    session.log(
        "jev", purpose="recommend", jev_error=note, latency_ms=latency,
        history=[b["title"] for b in history], stated=sorted(stated),
        answers={p["book"]["title"]: round(p["p"], 2) for p in picks if p["p"] is not None} or None,
        decision=("picked " + ", ".join(f"{p['book']['title']} (tier {p['tier']})" for p in picks)) if picks else "no fit",
    )
    if not picks:
        return {"status": "failed" if note and not stated else "no_fit",
                "next_step": "Say you do not have a good match in the catalog right now, and offer a person."}, []
    return {
        "status": "ok",
        "picks": [{"title": p["book"]["title"], "author": p["book"]["author"], "format": p["book"]["format"],
                   "price": p["book"]["price"], "genres": [judgments.GENRES[g] for g in p["book"]["genres"]],
                   "about": p["book"]["about"], "why": p["why"]} for p in picks],
        "next_step": "Offer only these books, each with one short reason based on its 'why'. To describe a book, "
                     "use its 'about' line and its 'genres', and add nothing that is not in this result. Do not "
                     "name any other book as a recommendation, and do not promise stock, discounts or delivery dates.",
    }, picks


def titles_in(text: str) -> set[str]:
    """Catalog titles named in a piece of text (whole title, as written)."""
    found = set()
    for book in catalog():
        if re.search(r"(?<![\w'])" + re.escape(book["title"]) + r"(?![\w'])", text or ""):
            found.add(book["title"])
    return found


def _marked_as_title(title: str, author: str, reply: str) -> bool:
    """A one-word title ("Educated", "James", "Dune") is also an ordinary word or a name. Outside a
    recommendation it counts as a book only when the reply marks it as one: bold, italics or quotes, or the
    author's surname in the same reply."""
    t = re.escape(title)
    return bool(re.search(rf"(\*\*?|[\"“‘'_]){t}(\*\*?|[\"”’'_])", reply) or author.split()[-1] in reply)


def unlisted_titles(reply: str, allowed: set[str], recommending: bool = True) -> list[str]:
    """Catalog titles the reply names that the system did not hand to the model in this conversation.
    `recommending` is False until recommend_books has been called: then a one-word title must be marked."""
    found = titles_in(reply) - allowed
    if not recommending:
        authors = {b["title"]: b["author"] for b in catalog()}
        found = {t for t in found if " " in t or _marked_as_title(t, authors[t], reply)}
    return sorted(found)
