"""One source of truth: the policy text the agent quotes is rendered from the same values the engine uses."""

import re

import yaml

from bookly.config import POLICY_TEXT_PATH
from bookly.kb import PLACEHOLDER, PolicyText
from bookly.policy import Decision, Line, Policy


def _templates():
    raw = yaml.safe_load(POLICY_TEXT_PATH.read_text())
    return [p["text"] for p in raw["passages"]] + list(raw["terms"].values()) + list(raw["messages"].values())


def test_templates_contain_no_hard_coded_numbers():
    for template in _templates():
        stripped = PLACEHOLDER.sub("", template)
        assert not re.search(r"\d", stripped), f"Hard-coded number in policy text: {template!r}"


def test_every_placeholder_resolves(policy):
    pt = PolicyText(policy)
    for p in pt.passages:
        assert "{" not in p.text, p.text


def test_text_follows_the_policy_value():
    shorter = PolicyText(Policy.load(overrides={"returns.print_return_window_days": 14}))
    text = next(p.text for p in shorter.passages if p.id == "returns-print")
    assert "within 14 days of delivery" in text


def test_search_finds_grounded_passages(policy_text):
    assert policy_text.search("do you ship to Canada?")[0].id == "shipping-regions"
    assert policy_text.search("I forgot my password")[0].id == "account-password"
    assert policy_text.search("what is your return policy")[0].id == "returns-print"


def test_search_returns_nothing_for_unsupported_topics(policy_text):
    assert policy_text.search("do you price match Amazon") == []
    assert policy_text.search("gift wrapping options") == []


def test_terms_are_built_from_the_decision(policy_text):
    d = Decision(decision="refund_no_return", reason="damaged", reason_code="eligible",
                 lines=[Line("BK-1001-1", "The Midnight Library", "print", "refund_no_return", 18.99)], amount=18.99)
    terms = policy_text.terms(d)
    assert "$18.99" in terms
    assert "do not need to send the book back" in terms
