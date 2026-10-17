"""Kitchen assistant: answers questions using ONLY the app's own data.

How it works:
- A few "tools" (plain Python functions) compute facts from the data: prep plan,
  order suggestions, waste summary, worst-waste dishes, weekday patterns.
- Offline mode (default): simple keyword matching picks a tool and turns its result into text,
  always with a "Why" line saying where the numbers come from.
- LLM mode (if LLM_API_KEY is set): an OpenAI-compatible model may call the same tools.
  It is told to use only tool results; we also check its numbers against the tool results.
- The assistant only ADVISES. It cannot approve plans or place orders.
"""
import json
import os
import re
from dataclasses import dataclass, field

import pandas as pd

import core
import ordering

SUGGESTED_QUESTIONS = [
    "What should I prep tomorrow?",
    "What should I order for the next 3 days?",
    "Which dishes waste the most?",
    "How much did we waste last week?",
    "Which weekday is busiest?",
    "Any advice to cut waste?",
]


@dataclass
class AppData:
    sales: pd.DataFrame
    recipes: pd.DataFrame
    stock: pd.DataFrame
    suppliers: pd.DataFrame
    plan_date: object                       # the "tomorrow" we plan for
    waste_log: list = field(default_factory=list)


# ------------------------------------------------------------------ tools
def tool_prep_plan(data: AppData, buffer_pct: float = 10, weeks: int = 4) -> dict:
    rec = core.recommend(core.weekday_moving_average(data.sales, data.plan_date, weeks), buffer_pct)
    rec = rec.sort_values("suggested_prep", ascending=False)
    return {"date": str(data.plan_date), "buffer_pct": buffer_pct, "weeks_of_history": weeks,
            "items": [{"item": r.item, "forecast": float(r.forecast), "suggested_prep": int(r.suggested_prep)}
                      for r in rec.itertuples()],
            "total_portions": int(rec["suggested_prep"].sum())}


def tool_order_suggestions(data: AppData, days: int = 3, buffer_pct: float = 10) -> dict:
    days = max(1, min(int(days), 14))
    o = ordering.order_suggestions(data.sales, data.recipes, data.stock, data.suppliers,
                                   data.plan_date, days=days, buffer_pct=buffer_pct)
    to_order = o[o["packs"] > 0]
    return {"start": str(data.plan_date), "days": days, "buffer_pct": buffer_pct,
            "lines": [{"ingredient": r.ingredient, "supplier": r.supplier, "packs": int(r.packs),
                       "pack_size_g": int(r.pack_size_g), "needed_g": int(r.needed_g),
                       "on_hand_g": int(r.on_hand_g), "est_cost_nok": int(r.est_cost_nok)}
                      for r in to_order.itertuples()],
            "total_est_cost_nok": int(to_order["est_cost_nok"].sum()),
            "ingredients_with_enough_stock": int((o["packs"] == 0).sum())}


def tool_waste_summary(data: AppData, days: int = 7) -> dict:
    s = data.sales
    if "wasted_units" not in s:
        return {"error": "sales data has no wasted_units column"}
    end = s["date"].max()
    recent = s[s["date"] > end - pd.Timedelta(days=days)]
    prev = s[(s["date"] <= end - pd.Timedelta(days=days)) & (s["date"] > end - pd.Timedelta(days=2 * days))]
    by_dish = recent.groupby("item")["wasted_units"].sum().sort_values(ascending=False)
    out = {"days": days, "period_end": str(end.date()),
           "wasted_portions": int(recent["wasted_units"].sum()),
           "previous_period_wasted_portions": int(prev["wasted_units"].sum()),
           "by_dish": [{"dish": d, "wasted_portions": int(v)} for d, v in by_dish.items()]}
    if "unit_cost_nok" in s:
        out["est_waste_cost_nok"] = int((recent["wasted_units"] * recent["unit_cost_nok"]).sum())
    if data.waste_log:
        log = pd.DataFrame(data.waste_log)
        out["logged_this_session_g"] = round(float(log["grams_wasted"].sum()), 1)
    return out


def tool_worst_waste_dishes(data: AppData, n: int = 3, days: int = 28) -> dict:
    s = data.sales
    recent = s[s["date"] > s["date"].max() - pd.Timedelta(days=days)]
    g = recent.groupby("item")[["prepared_units", "wasted_units"]].sum()
    g["waste_rate_pct"] = (100 * g["wasted_units"] / g["prepared_units"]).round(1)
    g = g.sort_values("waste_rate_pct", ascending=False).head(n)
    return {"days": days, "dishes": [{"dish": d, "waste_rate_pct": float(r.waste_rate_pct),
                                      "wasted_portions": int(r.wasted_units), "prepared_portions": int(r.prepared_units)}
                                     for d, r in g.iterrows()]}


def tool_weekday_pattern(data: AppData, item: str | None = None) -> dict:
    s = data.sales if not item else data.sales[data.sales["item"] == item]
    daily = s.groupby("date")["sold_units"].sum().reset_index()
    daily["weekday"] = daily["date"].dt.day_name()
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    avg = daily.groupby("weekday")["sold_units"].mean().reindex(order).round(1)
    return {"item": item or "all dishes", "avg_portions_sold": {d: float(v) for d, v in avg.items()},
            "busiest": avg.idxmax(), "quietest": avg.idxmin()}


TOOLS = {
    "get_prep_plan": (tool_prep_plan, "Suggested prep portions per dish for the plan date.",
                      {"buffer_pct": {"type": "number"}, "weeks": {"type": "integer"}}),
    "get_order_suggestions": (tool_order_suggestions, "Suggested supplier order (packs) for the next N days.",
                              {"days": {"type": "integer"}, "buffer_pct": {"type": "number"}}),
    "get_waste_summary": (tool_waste_summary, "Wasted portions in the last N days, by dish.",
                          {"days": {"type": "integer"}}),
    "get_worst_waste_dishes": (tool_worst_waste_dishes, "Dishes with the highest waste rate.",
                               {"n": {"type": "integer"}, "days": {"type": "integer"}}),
    "get_weekday_pattern": (tool_weekday_pattern, "Average portions sold per weekday (optionally for one dish).",
                            {"item": {"type": "string"}}),
}


def run_tool(name: str, data: AppData, args: dict | None = None) -> dict:
    fn, _, params = TOOLS[name]
    clean = {k: v for k, v in (args or {}).items() if k in params}   # ignore unknown arguments
    return fn(data, **clean)


# ------------------------------------------------------------------ offline answers
def _days_in(q: str, default: int) -> int:
    m = re.search(r"(\d+)\s*day", q)
    return int(m.group(1)) if m else (7 if "week" in q else default)


def _item_in(q: str, data: AppData):
    for item in data.sales["item"].unique():
        if item in q or item.replace("_", " ") in q:
            return item
    return None


def _fmt_prep(r):
    top = "\n".join(f"- **{i['item']}**: prep {i['suggested_prep']} (forecast {i['forecast']})" for i in r["items"])
    return (f"For **{r['date']}** I suggest prepping {r['total_portions']} portions in total:\n{top}\n\n"
            f"**Why:** average of the same weekday over the last {r['weeks_of_history']} weeks of sales "
            f"+ {r['buffer_pct']}% safety buffer. Approve it on the *Prep plan* page.")


def _fmt_order(r):
    if not r["lines"]:
        return f"Stock covers the next {r['days']} days — nothing to order.\n\n**Why:** forecast needs are below stock on hand."
    lines = "\n".join(f"- **{l['ingredient']}**: {l['packs']} × {l['pack_size_g']} g ({l['supplier']}) — "
                      f"need {l['needed_g']} g, have {l['on_hand_g']} g" for l in r["lines"])
    return (f"Suggested order for the next {r['days']} days (est. {r['total_est_cost_nok']} NOK):\n{lines}\n\n"
            f"{r['ingredients_with_enough_stock']} other ingredients have enough stock.\n\n"
            f"**Why:** forecast portions × recipe grams (+{r['buffer_pct']}% buffer) minus stock, rounded up to packs. "
            f"Nothing is sent — review and approve on the *Ordering* page.")


def _fmt_waste(r):
    if "error" in r:
        return r["error"]
    top = ", ".join(f"{d['dish']} {d['wasted_portions']}" for d in r["by_dish"][:3])
    extra = f"\n\nPlates/bins logged this session: {r['logged_this_session_g']} g." if "logged_this_session_g" in r else ""
    cost = f" (≈ {r['est_waste_cost_nok']} NOK at recipe cost)" if "est_waste_cost_nok" in r else ""
    return (f"In the last {r['days']} days up to {r['period_end']}: **{r['wasted_portions']} portions** wasted{cost}, "
            f"vs {r['previous_period_wasted_portions']} in the {r['days']} days before. Top: {top}.{extra}\n\n"
            f"**Why:** sum of `wasted_units` (prepared − sold) in the sales history (synthetic data).")


def _fmt_worst(r, advice=False):
    lines = "\n".join(f"- **{d['dish']}**: {d['waste_rate_pct']}% of prepared portions wasted "
                      f"({d['wasted_portions']} of {d['prepared_portions']})" for d in r["dishes"])
    tip = ""
    if advice and r["dishes"]:
        w = r["dishes"][0]["dish"]
        tip = (f"\n\n**Advice:** start with **{w}** — lower its prep buffer on the *Prep plan* page, "
               f"prep in smaller batches later in service, and log returned plates to see if portions are too big.")
    return (f"Highest waste rate over the last {r['days']} days:\n{lines}{tip}\n\n"
            f"**Why:** wasted ÷ prepared portions per dish in the sales history.")


def _fmt_weekday(r):
    days = ", ".join(f"{d[:3]} {v}" for d, v in r["avg_portions_sold"].items())
    return (f"Average portions sold per day ({r['item']}): {days}. Busiest: **{r['busiest']}**, quietest: **{r['quietest']}**.\n\n"
            f"**Why:** mean of daily `sold_units` by weekday over all history.")


HELP = ("I can answer from this app's data:\n" + "\n".join(f"- {q}" for q in SUGGESTED_QUESTIONS) +
        "\n\nI only advise — approvals happen on the Prep plan and Ordering pages.")


def answer_offline(question: str, data: AppData) -> dict:
    q = question.lower()
    if any(w in q for w in ("order", "buy", "supplier", "stock", "purchase")):
        tool, args, fmt = "get_order_suggestions", {"days": _days_in(q, 3)}, _fmt_order
    elif any(w in q for w in ("advice", "tip", "improve", "reduce", "cut")):
        tool, args, fmt = "get_worst_waste_dishes", {}, lambda r: _fmt_worst(r, advice=True)
    elif any(w in q for w in ("worst", "most waste", "waste the most", "wastes the most", "highest")):
        tool, args, fmt = "get_worst_waste_dishes", {}, _fmt_worst
    elif any(w in q for w in ("waste", "leftover", "bin", "thrown")):
        tool, args, fmt = "get_waste_summary", {"days": _days_in(q, 7)}, _fmt_waste
    elif any(w in q for w in ("weekday", "busiest", "busy", "quiet", "pattern", "day of the week")):
        tool, args, fmt = "get_weekday_pattern", {"item": _item_in(q, data)}, _fmt_weekday
    elif any(w in q for w in ("prep", "make", "cook", "plan", "tomorrow", "today", "forecast")):
        tool, args, fmt = "get_prep_plan", {}, _fmt_prep
    else:
        return {"text": HELP, "tools": [], "mode": "offline"}
    result = run_tool(tool, data, args)
    return {"text": fmt(result), "tools": [{"name": tool, "args": args, "result": result}], "mode": "offline"}


# ------------------------------------------------------------------ number grounding check
def ungrounded_numbers(text: str, tool_results: list, question: str = "") -> list:
    """Numbers in `text` that don't appear in any tool result or the question (small counts allowed)."""
    known = set(re.findall(r"\d+(?:\.\d+)?", json.dumps(tool_results) + " " + question))
    known |= {k.split(".")[0] for k in known} | {f"{float(k):g}" for k in known}
    found = re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))
    return [n for n in found if n not in known and not (n.isdigit() and int(n) <= 10)]


# ------------------------------------------------------------------ LLM mode
SYSTEM_PROMPT = (
    "You are the kitchen assistant for a restaurant demo app with SYNTHETIC data. "
    "Answer ONLY using numbers returned by the tools; never invent or estimate numbers yourself. "
    "If the tools can't answer, say so. Always end with a short 'Why:' line naming the tool/data used. "
    "You can only advise: you cannot approve prep plans or place orders; the manager does that in the app.")


def _tool_specs():
    return [{"type": "function", "function": {"name": n, "description": d,
             "parameters": {"type": "object", "properties": p}}} for n, (_, d, p) in TOOLS.items()]


def answer_llm(question: str, data: AppData, client, model: str, history: list | None = None) -> dict:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + (history or [])[-6:] + \
               [{"role": "user", "content": question}]
    used = []
    for _ in range(4):                                    # at most 4 rounds of tool calls
        resp = client.chat.completions.create(model=model, messages=messages, tools=_tool_specs(), temperature=0)
        msg = resp.choices[0].message
        calls = getattr(msg, "tool_calls", None) or []
        if not calls:
            text = msg.content or ""
            bad = ungrounded_numbers(text, [u["result"] for u in used], question)
            if bad:
                text += f"\n\n⚠️ Could not verify these numbers against the app data: {', '.join(bad)}. Treat them with caution."
            return {"text": text, "tools": used, "mode": "llm"}
        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [{"id": c.id, "type": "function",
                                         "function": {"name": c.function.name, "arguments": c.function.arguments}}
                                        for c in calls]})
        for c in calls:
            if c.function.name in TOOLS:
                args = json.loads(c.function.arguments or "{}")
                result = run_tool(c.function.name, data, args)
            else:
                args, result = {}, {"error": f"unknown tool {c.function.name}"}
            used.append({"name": c.function.name, "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": c.id, "content": json.dumps(result)})
    raise RuntimeError("too many tool-call rounds")


def answer(question: str, data: AppData, client=None, history: list | None = None) -> dict:
    """Main entry point. Uses the LLM if configured, else (or on any error) the offline answers."""
    if client is None and os.environ.get("LLM_API_KEY"):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=os.environ.get("LLM_BASE_URL"))
        except Exception:
            client = None
    if client is not None:
        try:
            return answer_llm(question, data, client, os.environ.get("LLM_MODEL", "gpt-4o-mini"), history)
        except Exception as e:
            out = answer_offline(question, data)
            out["text"] += f"\n\n_(LLM unavailable: {type(e).__name__}; answered offline.)_"
            return out
    return answer_offline(question, data)
