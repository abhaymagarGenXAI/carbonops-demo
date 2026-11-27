import json

import pytest

from app.services import assistant as asst
from app.services import assistant_tools as tools
from tests.conftest import ENGINEER, MANAGER, auth_headers

API = "/api/v1"


class FakeOllama:
    """Scripted stand-in for the model: replies is a list of messages, or callables(messages) -> message."""

    def __init__(self, *replies):
        self.replies, self.seen = list(replies), []

    def __call__(self, messages, specs):
        self.seen.append([dict(m) for m in messages])
        r = self.replies.pop(0)
        return r(messages) if callable(r) else r


def call(name, **args):
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}


def say(text):
    return {"role": "assistant", "content": text}


def ask(client, h, q="What were total emissions in 2026-05?"):
    r = client.post(f"{API}/assistant/ask", headers=h, json={"question": q})
    assert r.status_code == 200, r.text
    return r.json()


def total_may(client, h):
    return client.get(f"{API}/reports/inventory", headers=h, params={"from": "2026-05", "to": "2026-05"}).json()["summary"]["totals"]["total"]


def test_answer_is_built_from_tool_output(client, monkeypatch):
    h = auth_headers(client, MANAGER)
    t = total_may(client, h)
    # the model quotes whatever the tool returned, taken from the tool message it was shown
    fake = FakeOllama(call("get_emission_inventory", from_month="2026-05", to_month="2026-05"),
                      lambda m: say(f"Approved emissions for 2026-05 were {json.loads(m[-1]['content'])['totals']['total']:,} tCO2e."))
    monkeypatch.setattr(asst, "ollama_chat", fake)
    out = ask(client, h)
    assert out["mode"] == "answered" and f"{t:,}" in out["answer"]
    assert [c["name"] for c in out["toolCalls"]] == ["get_emission_inventory"]
    assert out["toolCalls"][0]["result"]["totals"]["total"] == t            # traceable: data used is returned with the answer
    assert out["ungrounded"] == []


def test_invented_number_is_retried_then_withheld(client, monkeypatch):
    h = auth_headers(client, MANAGER)
    fake = FakeOllama(call("get_emission_inventory", from_month="2026-05", to_month="2026-05"),
                      say("Emissions were 123,456.7 tCO2e."), say("It is still 987,654.3 tCO2e."))
    monkeypatch.setattr(asst, "ollama_chat", fake)
    out = ask(client, h)
    assert out["mode"] == "withheld" and out["answer"] is None and "987654.3" in out["ungrounded"]
    assert out["toolCalls"][0]["result"]["totals"]                           # the real data is still returned
    assert "not in the tool results" in fake.seen[-1][-1]["content"]         # one corrective retry happened


def test_retry_can_recover_with_grounded_answer(client, monkeypatch):
    h = auth_headers(client, MANAGER)
    t = total_may(client, h)
    fake = FakeOllama(call("get_emission_inventory", from_month="2026-05", to_month="2026-05"), say("About 99,999 tCO2e."),
                      say(f"Total emissions were {t:,} tCO2e."))
    monkeypatch.setattr(asst, "ollama_chat", fake)
    assert ask(client, h)["mode"] == "answered"


def test_model_arithmetic_is_not_allowed(client, monkeypatch):
    h = auth_headers(client, MANAGER)
    monkeypatch.setattr(asst, "ollama_chat", FakeOllama(call("get_emission_inventory", from_month="2026-05", to_month="2026-05"),
                                                         say("Scope 1 plus Scope 2 gives 1,234,567.8 tCO2e."), say("Sum: 1,234,567.8 tCO2e.")))
    assert ask(client, h)["mode"] == "withheld"


def test_numbers_without_any_tool_call_are_withheld(client, monkeypatch):
    h = auth_headers(client, ENGINEER)
    monkeypatch.setattr(asst, "ollama_chat", FakeOllama(say("Last year we emitted 55,000 tCO2e."), say("We emitted 55,000 tCO2e.")))
    out = ask(client, h, "How much did we emit last year?")
    assert out["mode"] == "withheld" and out["toolCalls"] == []


def test_refusal_without_numbers_passes(client, monkeypatch):
    h = auth_headers(client, ENGINEER)
    monkeypatch.setattr(asst, "ollama_chat", FakeOllama(say("I can only answer questions about the platform's emissions data.")))
    out = ask(client, h, "Who won the cricket match?")
    assert out["mode"] == "answered" and out["toolCalls"] == []


def test_bad_tool_arguments_are_returned_to_the_model_not_raised(client, monkeypatch):
    h = auth_headers(client, MANAGER)
    fake = FakeOllama(call("get_emission_inventory", from_month="May 2026"), call("nope"), call("get_emission_inventory", facility_id="Atlantis"),
                      say("I could not retrieve that."))
    monkeypatch.setattr(asst, "ollama_chat", fake)
    out = ask(client, h)
    assert [("error" in c["result"]) for c in out["toolCalls"]] == [True, True, True] and out["mode"] == "answered"


def test_loop_is_bounded(client, monkeypatch):
    h = auth_headers(client, MANAGER)
    monkeypatch.setattr(asst, "ollama_chat", lambda m, s: call("list_facilities"))
    out = ask(client, h)
    assert out["mode"] == "withheld" and len(out["toolCalls"]) == asst.MAX_ROUNDS


def test_ollama_down_is_reported_not_faked(client, monkeypatch):
    h = auth_headers(client, ENGINEER)

    def boom(m, s):
        raise asst.OllamaUnavailable("Ollama is not reachable at http://localhost:11434. Start it with `ollama serve`.")
    monkeypatch.setattr(asst, "ollama_chat", boom)
    out = ask(client, h)
    assert out["mode"] == "unavailable" and out["answer"] is None and "ollama serve" in out["message"]


def test_status_endpoint_and_default_model_is_free(client):
    h = auth_headers(client, ENGINEER)
    s = client.get(f"{API}/assistant/status", headers=h).json()
    assert s["model"] == "qwen2.5:7b" and s["reachable"] in (True, False)    # Apache-2.0 model; no server needed for the test
    assert {t["name"] for t in client.get(f"{API}/assistant/tools", headers=h).json()} == set(tools.TOOLS)


def test_validation_audit_and_auth(client, monkeypatch):
    monkeypatch.setattr(asst, "ollama_chat", FakeOllama(say("I can only answer questions about the platform's emissions data.")))
    h = auth_headers(client, ENGINEER)
    assert client.post(f"{API}/assistant/ask", headers=h, json={"question": "x"}).status_code == 422
    assert client.post(f"{API}/assistant/ask", headers=h, json={"question": "q" * 501}).status_code == 422
    assert client.post(f"{API}/assistant/ask", json={"question": "hello there"}).status_code == 401
    ask(client, h, "What is the weather?")
    log = client.get(f"{API}/audit", headers=auth_headers(client, MANAGER)).json()
    assert any(a["action"] == "Asked" and "What is the weather?" in a["detail"] for a in log)


@pytest.mark.parametrize("answer,results,bad", [
    ("Total was 1,234.5 tCO2e in 2026-05 (2026).", [{"t": 1234.5}], []),
    ("Total was 1,234 tCO2e.", [{"t": 1234.4}], []),                 # rounding to the quoted precision is fine
    ("Total was 1,240 tCO2e.", [{"t": 1234.4}], ["1240"]),
    ("There are 3 alerts, 42.1% off.", [{"n": 3}], ["42.1"]),
    ("Facilities: FAC-001 and FAC-002.", [], ["1", "2"][:0]),         # ids / dates / small ints are not "figures"
    ("Value 5.5", [{"x": "5.5 TJ"}], []),                            # numbers inside result strings count
])
def test_grounding_check(answer, results, bad):
    assert asst.ungrounded(answer, results) == bad


def test_tool_call_printed_as_text_is_still_executed(client, monkeypatch):
    h = auth_headers(client, MANAGER)
    t = total_may(client, h)
    printed = say('<tool_call>\n{"name": "get_emission_inventory", "arguments": {"from_month": "2026-05", "to_month": "2026-05"}}\n</tool_call>')
    monkeypatch.setattr(asst, "ollama_chat", FakeOllama(printed, say(f"Total was {t:,} tCO2e.")))
    out = ask(client, h)
    assert [c["name"] for c in out["toolCalls"]] == ["get_emission_inventory"] and out["mode"] == "answered"


def test_prompt_carries_todays_date_and_context_window(client, monkeypatch):
    h = auth_headers(client, ENGINEER)
    fake = FakeOllama(say("I can only answer questions about the platform's emissions data."))
    monkeypatch.setattr(asst, "ollama_chat", fake)
    ask(client, h, "hello there")
    assert "Today is 20" in fake.seen[0][0]["content"] and asst.NUM_CTX >= 8192


def test_withheld_answer_exposes_the_raw_reply_for_diagnosis(client, monkeypatch):
    h = auth_headers(client, MANAGER)
    monkeypatch.setattr(asst, "ollama_chat", FakeOllama(say("We emitted 55,000 tCO2e."), say("We emitted 55,000 tCO2e.")))
    out = ask(client, h)
    assert out["mode"] == "withheld" and out["rawAnswer"] == "We emitted 55,000 tCO2e."


# ------------------------------------------------------------- broader tool coverage (the questions that failed with a real model)
def run_tool(db, name, **args):
    return tools.run(db, name, args)


def test_reporting_periods_tool_matches_api(client, db):
    h = auth_headers(client, MANAGER)
    api = {p["period"]: p["status"] for p in client.get(f"{API}/reporting-periods", headers=h).json()}
    t = run_tool(db, "get_reporting_periods")
    assert {p["period"]: p["status"] for p in t["periods"]} == api
    assert {s for s in t["periodsByStatus"]} <= {"Open", "In Review", "Locked"} and sum(len(v) for v in t["periodsByStatus"].values()) == len(api)


def test_submission_status_tool_matches_api(client, db):
    h = auth_headers(client, MANAGER)
    subs = [s for s in client.get(f"{API}/submissions", headers=h).json() if s["month"] == "2026-07"]
    facs = client.get(f"{API}/facilities", headers=h).json()
    t = run_tool(db, "get_submission_status", period="2026-07")
    have = {s["facilityId"] for s in subs}
    assert set(t["notYetSubmitted"]) >= {f["name"] for f in facs if f["id"] not in have}
    assert sum(t["countsByStatus"].values()) >= len(subs) and t["facilityCount"] == len(facs)
    assert "error" in run_tool(db, "get_submission_status") and "error" in run_tool(db, "get_submission_status", period="July")


def test_energy_tool_finds_peak_month_and_facility_split(client, db):
    h = auth_headers(client, MANAGER)
    recs = [r for r in client.get(f"{API}/energy-records", headers=h).json() if r["stream"] == "Electricity" and not r.get("excluded")
            and r.get("submissionStatus") in (None, "Approved")]
    per_month: dict[str, float] = {}
    for r in recs:
        per_month[r["month"]] = per_month.get(r["month"], 0) + r["quantity"]
    top = max(per_month, key=per_month.get)
    t = run_tool(db, "get_energy_consumption", stream="Electricity")
    assert t["peakMonthPerStream"]["Electricity"]["month"] == top
    assert t["peakMonthPerStream"]["Electricity"]["quantity"] == pytest.approx(per_month[top], abs=0.01)
    fac_total = sum(r["quantity"] for r in t["byFacilityInPeakMonths"] if r["month"] == top and r["stream"] == "Electricity")
    assert fac_total == pytest.approx(per_month[top], abs=0.05)                  # facility split adds up to the month total
    assert "error" in run_tool(db, "get_energy_consumption", basis="weird")


def test_factor_tool_lists_every_factor(client, db):
    h = auth_headers(client, MANAGER)
    api = client.get(f"{API}/emission-factors", headers=h).json()
    assert run_tool(db, "get_emission_factors")["count"] == len(api)
    s2 = run_tool(db, "get_emission_factors", scope="Scope 2")
    assert s2["count"] == len([f for f in api if f["scope"] == "Scope 2"]) and all(f["scope"] == "Scope 2" for f in s2["factors"])


def test_query_data_counts_sums_groups_and_is_whitelisted(client, db):
    h = auth_headers(client, MANAGER)
    assets = client.get(f"{API}/assets", headers=h).json()
    assert run_tool(db, "query_data", collection="assets")["value"] == len(assets)
    g = run_tool(db, "query_data", collection="assets", group_by="status")
    assert {x["key"]: x["count"] for x in g["groups"]} == {s: len([a for a in assets if a["status"] == s]) for s in {a["status"] for a in assets}}
    em = client.get(f"{API}/emission-records", headers=h).json()
    s = run_tool(db, "query_data", collection="emission_records", filters={"scope": "Scope 1", "reviewStatus": "Approved"}, aggregate="sum", field="co2e")
    assert s["value"] == pytest.approx(sum(r["co2e"] for r in em if r["scope"] == "Scope 1" and r["reviewStatus"] == "Approved"), abs=0.05)
    for bad in (dict(collection="users"), dict(collection="assets", filters={"password": "x"}), dict(collection="assets", group_by="secret"),
                dict(collection="assets", aggregate="sum", field="name"), dict(collection="assets", aggregate="drop")):
        assert "error" in run_tool(db, "query_data", **bad)


def test_user_questions_end_to_end_with_scripted_model(client, monkeypatch):
    """The five questions that previously got refusals/guesses: each now has a tool, and the answer is grounded in its output."""
    h = auth_headers(client, MANAGER)
    ex = lambda m: json.loads(m[-1]["content"])
    fake = FakeOllama(call("get_submission_status", period="2026-07"),
                      lambda m: say(f"For 2026-07 the period is {ex(m)['periodStatus']}; not yet submitted: {', '.join(ex(m)['notYetSubmitted']) or 'none'}."))
    monkeypatch.setattr(asst, "ollama_chat", fake)
    out = ask(client, h, "Which facilities are yet to submit for 2026-07?")
    assert out["mode"] == "answered" and out["toolCalls"][0]["name"] == "get_submission_status"
