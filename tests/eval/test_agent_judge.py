"""E11: the blind A/B judge (engine top 3 vs agent top 3), with a fake SDK (no network)."""

import json

import anthropic
import httpx2
import pytest

from rmprep.eval.config import load_config
from rmprep.eval.judge import (
    AB_QUESTION, AbChoice, CachedAbJudge, HaikuAbJudge, ab_compare, ab_grades, ab_schema,
    ab_system_text, ab_user_text, agent_first,
)
from rmprep.eval.scenario import Scenario
from tests.eval.conftest import PROJECT, PackClient
from tests.eval.test_agent_eval import run_with_agent
from tests.eval.test_judge import FakeSdk, _message

CFG = load_config(PROJECT / "config" / "eval.yaml").judge


class Fixed:
    """An A/B judge that always gives `choice`."""

    model = "fake-ab"

    def __init__(self, choice="A", cost=0.001):
        self.choice, self.cost, self.users = choice, cost, []

    def choose(self, user):
        self.users.append(user)
        return AbChoice(self.choice, "reason", self.model, cost_usd=self.cost)


@pytest.fixture
def swapped(root):
    s = Scenario(id="base-p01", group="base", persona="P01", narrate=False)
    runs, _ = run_with_agent(root, [s], PackClient("swap"), repeat=False)
    return runs


def test_the_order_is_random_but_fixed_by_the_run_id():
    firsts = [agent_first(f"R{i:010x}") for i in range(200)]
    assert 60 < sum(firsts) < 140
    assert [agent_first(f"R{i:010x}") for i in range(200)] == firsts


@pytest.mark.parametrize("choice", ["A", "B", "esit"])
def test_the_answer_is_mapped_back(swapped, choice):
    run = swapped[0].runs[0]
    g = ab_compare("base-p01", run.result, run.agent.pack, run.agent.decision, Fixed(choice))
    first = agent_first(run.result.run_id)
    assert g.agent_label == ("A" if first else "B")
    want = {"esit": "equal", "A": "agent" if first else "engine",
            "B": "engine" if first else "agent"}[choice]
    assert g.winner == want and g.choice.choice == choice


def test_the_prompt_is_blind_and_holds_both_sets(swapped):
    run = swapped[0].runs[0]
    judge = Fixed()
    ab_compare("base-p01", run.result, run.agent.pack, run.agent.decision, judge)
    [user] = judge.users
    low = user.lower()
    for word in ("ajan", "agent", "engine", "motor_ilk3", "puan", "gerekçe"):
        assert word not in low
    agent = [p.option_id for p in run.agent.decision.picks]
    engine = list(run.result.recommended)
    names = {c["option_id"]: c["ad"] for c in run.agent.pack["adaylar"]}
    a, b = user.split("<set_b>")
    first, second = (agent, engine) if agent_first(run.result.run_id) else (engine, agent)
    assert all(names[o] in a for o in first) and all(names[o] in b for o in second)
    assert AB_QUESTION in ab_system_text()


def test_the_same_top3_is_not_sent(root):
    s = Scenario(id="base-p01", group="base", persona="P01", narrate=False)
    runs, _ = run_with_agent(root, [s], PackClient("keep"), repeat=False)
    run = runs[0].runs[0]
    judge = Fixed()
    g = ab_compare("base-p01", run.result, run.agent.pack, run.agent.decision, judge)
    assert judge.users == [] and g.winner == "same" and g.choice.cost_usd == 0


def test_ab_grades_respects_the_budget(swapped):
    judge = Fixed()
    spent = []
    [g] = ab_grades(swapped, judge, budget_left=lambda: 0.0, spend=spent.append)
    assert judge.users == [] and g.choice.error.startswith("budget") and g.winner == ""
    [g] = ab_grades(swapped, judge, budget_left=lambda: 1.0, spend=spent.append)
    assert g.winner in ("agent", "engine") and spent == [0.001]


def test_haiku_ab_request_and_reply(swapped):
    run = swapped[0].runs[0]
    reply = json.dumps({"choice": "B", "reason": "B fits the horizon."})
    sdk = FakeSdk(_message(reply))
    judge = HaikuAbJudge(CFG, sdk=sdk)
    g = ab_compare("base-p01", run.result, run.agent.pack, run.agent.decision, judge)
    [k] = sdk.messages.calls
    assert k["model"] == "claude-haiku-5-5"
    assert k["output_config"] == {"effort": "low",
                                  "format": {"type": "json_schema", "schema": ab_schema()}}
    assert k["system"] == [{"type": "text", "text": ab_system_text(),
                            "cache_control": {"type": "ephemeral"}}]
    assert g.choice.choice == "B" and g.choice.reason == "B fits the horizon."
    assert g.choice.cost_usd == pytest.approx((20000 * 0.10 + 400 * 0.50) / 1e6)


def test_haiku_ab_errors(swapped):
    run = swapped[0].runs[0]
    user = ab_user_text(run.result, run.agent.pack, ["fund:EIL"], ["fund:BBF"])
    bad = HaikuAbJudge(CFG, sdk=FakeSdk(_message("{\"choice\": \"C\", \"reason\": \"x\"}")))
    assert bad.choose(user).error.startswith("bad reply")
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    down = anthropic.APIConnectionError(request=req)
    assert HaikuAbJudge(CFG, sdk=FakeSdk(down)).choose(user).error.startswith("connection")


def test_cached_ab_judge(swapped, tmp_path):
    run = swapped[0].runs[0]
    inner = Fixed("A")
    judge = CachedAbJudge(inner, tmp_path / "ab")
    g1 = ab_compare("base-p01", run.result, run.agent.pack, run.agent.decision, judge)
    g2 = ab_compare("base-p01", run.result, run.agent.pack, run.agent.decision, judge)
    assert len(inner.users) == 1 and g1.winner == g2.winner
    assert g1.choice.cost_usd == 0.001 and g2.choice.cost_usd == 0
    assert judge.cached(inner.users[0]) is not None
