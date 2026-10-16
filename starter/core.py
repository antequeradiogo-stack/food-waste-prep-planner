"""Pure logic (testable without Streamlit). Generic starter — the real prototype is built on the day."""
import os
import pandas as pd

REQUIRED = {"date", "item", "sold_units"}


def load_data(path_or_buffer) -> pd.DataFrame:
    df = pd.read_csv(path_or_buffer, parse_dates=["date"])
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {sorted(missing)}")
    df["weekday"] = df["date"].dt.day_name()
    return df


def weekday_moving_average(df, target_date, weeks=4) -> pd.DataFrame:
    """Baseline: mean of sold_units on the same weekday over the last `weeks` weeks before target_date."""
    target = pd.Timestamp(target_date)
    hist = df[(df["date"] < target) & (df["date"].dt.weekday == target.weekday())]
    hist = hist[hist["date"] >= target - pd.Timedelta(weeks=weeks)]
    out = hist.groupby("item")["sold_units"].agg(forecast="mean", n_obs="count").reset_index()
    out["forecast"] = out["forecast"].round(1)
    return out


def recommend(forecast_df, buffer_pct=10) -> pd.DataFrame:
    """Rule-based placeholder: prep = ceil(forecast * (1 + buffer)). Always needs human approval."""
    r = forecast_df.copy()
    r["suggested_prep"] = (r["forecast"] * (1 + buffer_pct / 100)).apply(lambda x: int(-(-x // 1)))
    r["reason"] = r.apply(lambda x: f"avg of {int(x.n_obs)} same-weekday days = {x.forecast}, +{buffer_pct}% buffer", axis=1)
    r.loc[r["n_obs"] < 2, "reason"] += " (LOW DATA - check manually)"
    return r


def explain(rec_df) -> str:
    """Optional LLM explanation behind env var LLM_API_KEY; offline rule-based fallback otherwise."""
    if os.environ.get("LLM_API_KEY"):
        try:
            return _llm_explain(rec_df)
        except Exception as e:  # never break the demo
            return rule_explain(rec_df) + f"\n\n(LLM unavailable: {type(e).__name__}; showing rule-based text)"
    return rule_explain(rec_df)


def rule_explain(rec_df) -> str:
    low = rec_df[rec_df["n_obs"] < 2]["item"].tolist()
    lines = [f"- {r.item}: prep {r.suggested_prep} ({r.reason})" for r in rec_df.itertuples()]
    note = f"\nItems with too little history: {', '.join(low)}." if low else ""
    return "Suggested prep (rule-based, not an order):\n" + "\n".join(lines) + note


def _llm_explain(rec_df) -> str:
    """Fill in on the day (and disclose). Send only aggregated, non-personal numbers."""
    from openai import OpenAI  # optional dependency, OpenAI-compatible endpoint
    client = OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=os.environ.get("LLM_BASE_URL"))
    msg = ("Explain these kitchen prep suggestions in 3 short bullet points for a chef. "
           "Do not add numbers that are not in the table.\n" + rec_df.to_csv(index=False))
    resp = client.chat.completions.create(model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
                                          messages=[{"role": "user", "content": msg}], max_tokens=200)
    return resp.choices[0].message.content
