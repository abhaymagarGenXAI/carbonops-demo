"""Local AI assistant: Ollama + an open-weight model, grounded by tool calls.

Guarantees (each covered by tests):
  * data only comes from assistant_tools (read-only calculations of the app) — the model cannot query anything else;
  * every number in the answer must occur in a tool result (rounding aside) — otherwise the answer is retried once, then withheld
    and only the tool output is shown, so the model cannot do its own arithmetic or recall figures from training;
  * runs entirely against the local Ollama server; if it is not running the endpoint says so instead of faking an answer.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Mapping

import httpx
from zoneinfo import ZoneInfo
from pymongo.database import Database

from app.core.config import get_settings
from app.services import assistant_tools as tools
from app.services.common import audit
from app.utils.time import utcnow

log = logging.getLogger("carbonops.assistant")
MAX_ROUNDS = 5
NUM_CTX = 8192  # Ollama's default context (2-4k tokens) silently truncates system prompt + tool results
SYSTEM = (
    "You are the CarbonOps assistant for an oil-and-gas sustainability team. You know NOTHING about the company's data except what tools return, "
    "and you must use tools for every data question. Tools cover: emissions inventory, targets, forecast, initiatives, alerts, reporting periods "
    "(Open/In Review/Locked), submission status per period, energy consumption, emission factors, and a generic query_data tool for counts and sums "
    "over assets, submissions, energy, emission records, initiatives, Scope 3 entries and facilities. "
    "Rules: (1) Pick the tool that fits; if the period is not named, or you are unsure which exist, call get_reporting_periods first — never invent a period. "
    "Several tool calls are fine. (2) Quote numbers exactly as they appear in tool results, with units; never calculate, estimate, round differently or combine "
    "numbers yourself. (3) State the basis (approved/pending), the period and any warnings the tool reports. (4) If a tool returns no records, say so plainly; "
    "do not substitute a different period. If no tool can provide the data, say which data is unavailable. Only decline questions unrelated to this platform. "
    "(5) Months are written YYYY-MM; when the user names a month without a year use the current year given below. Do not convert units. Be concise."
)
_NUM = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")
_DATE = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?\b")


class OllamaUnavailable(RuntimeError):
    pass


# ----------------------------------------------------------------------------- Ollama transport (patched in tests)
def ollama_chat(messages: list[dict[str, Any]], specs: list[dict[str, Any]]) -> dict[str, Any]:
    s = get_settings()
    try:
        r = httpx.post(f"{s.ollama_url}/api/chat", timeout=s.ollama_timeout_s,
                       json={"model": s.ollama_model, "messages": messages, "tools": specs, "stream": False, "options": {"temperature": 0, "num_ctx": NUM_CTX}})
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise OllamaUnavailable(f"Ollama is not reachable at {s.ollama_url}. Start it with `ollama serve`.") from exc
    if r.status_code == 404:
        raise OllamaUnavailable(f"Model '{s.ollama_model}' is not installed. Run `ollama pull {s.ollama_model}`.")
    if r.status_code >= 400:
        raise OllamaUnavailable(f"Ollama returned HTTP {r.status_code}: {r.text[:200]}")
    return r.json()["message"]


def status() -> dict[str, Any]:
    s = get_settings()
    out: dict[str, Any] = {"url": s.ollama_url, "model": s.ollama_model, "reachable": False, "modelInstalled": False, "message": ""}
    try:
        r = httpx.get(f"{s.ollama_url}/api/tags", timeout=3)
        names = {m.get("name", "") for m in r.json().get("models", [])}
        out["reachable"] = True
        out["modelInstalled"] = s.ollama_model in names or f"{s.ollama_model}:latest" in names
        out["message"] = "Ready" if out["modelInstalled"] else f"Model not installed. Run: ollama pull {s.ollama_model}"
    except Exception:  # noqa: BLE001 - any transport problem simply means "not available"
        out["message"] = "Ollama is not running. Install it from ollama.com (MIT licence), start it, then run: ollama pull " + s.ollama_model
    return out


def embedded_tool_calls(content: str) -> list[dict[str, Any]]:
    """Some open-weight models print the tool call as JSON text (optionally inside <tool_call> tags) instead of using the tool-call field."""
    text = re.sub(r"</?tool_call>", "", content or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    if not text.startswith(("{", "[")):
        return []
    try:
        data = json.loads(text)
    except ValueError:
        return []
    items = data if isinstance(data, list) else [data]
    out = []
    for it in items:
        if isinstance(it, dict) and it.get("name") in tools.TOOLS and isinstance(it.get("arguments", {}), (dict, str)):
            out.append({"function": {"name": it["name"], "arguments": it.get("arguments", {})}})
    return out


# ----------------------------------------------------------------------------- grounding
def _numbers_in_text(text: str) -> list[tuple[float, int]]:
    clean = _DATE.sub(" ", text)
    out = []
    for m in _NUM.finditer(clean):
        raw = m.group(0).replace(",", "")
        try:
            out.append((float(raw), len(raw.split(".")[1]) if "." in raw else 0))
        except ValueError:
            continue
    return out


def _flatten(o: Any, acc: list[float]) -> None:
    if isinstance(o, bool):
        return
    if isinstance(o, (int, float)):
        acc.append(float(o))
    elif isinstance(o, str):
        acc.extend(v for v, _ in _numbers_in_text(o))
    elif isinstance(o, Mapping):
        for v in o.values():
            _flatten(v, acc)
    elif isinstance(o, (list, tuple)):
        for v in o:
            _flatten(v, acc)


def ungrounded(answer: str, results: list[Any]) -> list[str]:
    """Numbers in the answer that no tool result contains (to the precision the answer quotes). Years/dates and 0-10 are ignored."""
    pool: list[float] = []
    _flatten(results, pool)
    bad = []
    for v, dec in _numbers_in_text(answer):
        if (dec == 0 and abs(v) <= 10) or (dec == 0 and 1900 <= v <= 2100):
            continue
        tol = 0.5 * 10 ** (-dec) + 1e-9
        if not any(abs(v - p) <= tol for p in pool):
            bad.append(f"{v:.{dec}f}")
    return sorted(set(bad))


# ----------------------------------------------------------------------------- the loop
def ask(db: Database, user: Mapping[str, Any], question: str) -> dict[str, Any]:
    s = get_settings()
    today = utcnow().astimezone(ZoneInfo(s.app_timezone)).date()
    messages: list[dict[str, Any]] = [{"role": "system", "content": f"{SYSTEM}\nToday is {today.isoformat()} (current year {today.year})."},
                                      {"role": "user", "content": question}]
    calls: list[dict[str, Any]] = []
    specs = tools.specs()
    out: dict[str, Any] = {"model": s.ollama_model, "question": question, "toolCalls": calls, "answer": None, "mode": "answered",
                           "ungrounded": [], "rawAnswer": None, "message": ""}
    retried = False
    try:
        for _ in range(MAX_ROUNDS):
            msg = ollama_chat(messages, specs)
            tcs = msg.get("tool_calls") or embedded_tool_calls(msg.get("content") or "")
            log.info("ollama round: tool_calls=%s content=%.200r", [t.get("function", {}).get("name") for t in tcs], msg.get("content"))
            if tcs:
                messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tcs})
                for tc in tcs:
                    fn = tc.get("function", {})
                    args = fn.get("arguments") or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except ValueError:
                            args = {}
                    name = fn.get("name", "")
                    result = tools.run(db, name, args)
                    calls.append({"name": name, "arguments": args, "result": result})
                    messages.append({"role": "tool", "tool_name": name, "name": name, "content": json.dumps(result, default=str)})
                continue
            answer = (msg.get("content") or "").strip()
            bad = ungrounded(answer, [c["result"] for c in calls])
            if bad and not retried:
                retried = True
                messages.append({"role": "assistant", "content": answer})
                messages.append({"role": "user", "content": "Your answer contains numbers that are not in the tool results (" + ", ".join(bad) +
                                 "). Call the needed tool, or answer again using only numbers exactly as returned by tools."})
                continue
            if bad:
                out.update(mode="withheld", ungrounded=bad, rawAnswer=answer, message="The model's answer contained figures that are not in the application's data, so it was withheld. "
                           "The data the tools returned is shown below.")
            else:
                out["answer"] = answer
            break
        else:
            out.update(mode="withheld", message="The assistant did not reach an answer within the allowed number of tool calls.")
    except OllamaUnavailable as exc:
        out.update(mode="unavailable", message=str(exc))
    audit(db, user, "Asked", "assistant", f"Assistant question ({out['mode']}): {question[:120]} — tools: {', '.join(c['name'] for c in calls) or 'none'}")
    return out
