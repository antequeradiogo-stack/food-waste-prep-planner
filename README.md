# Leftover Lab — food waste prep planner

A small Streamlit app that helps a restaurant kitchen **prep the right amount, order only what's missing, and see what gets thrown away**, with a manager approving every step.

- **Synthetic data only.** All sales, recipes, stock, suppliers and plate images are generated/illustrations — not from a real restaurant.
- **Prepared before the AI for Good Hackathon (19 Oct 2026, Oslo) as a disclosed starter template; built with AI assistance.** The hackathon prototype itself is built during the event (see `DISCLOSURE.md`).

![Home](docs/screenshots/home.png)

## How it works
1. **Forecast** — same-weekday average of recent sales predicts tomorrow's portions.
2. **Approve prep** — suggestions with a reason; the manager edits and approves.
3. **Order what's missing** — forecast × recipe grams − stock, rounded up to supplier packs; export CSV only.
4. **Log waste** — plate-return and kitchen-bin entries (staff-confirmed) show what's thrown away, to tune the next forecast.

## Pages
| Page | What you do | Screenshot |
|---|---|---|
| Home | Today's cards (forecast portions, top 3 to prep, waste logged, waste trend) and start-here links | [home](docs/screenshots/home.png) |
| Prep plan | Edit suggested portions, approve with your role | [prep](docs/screenshots/prep.png) |
| Ordering | Supplier order per ingredient with a *why* column; approve → download CSV (nothing is sent) | [order](docs/screenshots/order.png) |
| Waste cameras | **Plate return camera**: sample / upload / device webcam / IP-camera snapshot → leftover estimate → staff confirm → grams per ingredient. **Kitchen bin camera**: scale grams + reason. Explainer on connecting real cameras | [cameras](docs/screenshots/cameras.png) |
| Assistant | Chat that answers from the app's data (prep, orders, waste, worst dishes, busy weekdays) with a *Why* line; advises only | [chat](docs/screenshots/chat.png) |
| About & responsible AI | Data sources, limits, human oversight, privacy | [about](docs/screenshots/about.png) |

## Run locally (Python 3.10+; run from the repo root so the theme in `.streamlit/config.toml` loads)
Windows PowerShell:
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1     # if blocked: Set-ExecutionPolicy -Scope Process RemoteSigned
pip install -r starter/requirements.txt
pytest -q starter
streamlit run starter/app.py
```
macOS / Linux:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r starter/requirements.txt
pytest -q starter
streamlit run starter/app.py
```
Optional:
- **LLM mode** (assistant tool-calling + vision plate estimate): `pip install openai`, set `LLM_API_KEY` (and `LLM_BASE_URL`, `LLM_MODEL` [default gpt-4o-mini], `VISION_MODEL` [default gpt-4o-mini] for OpenAI-compatible providers). Never commit keys. Without a key everything works offline.
- **IP-camera snapshots**: `pip install opencv-python-headless`.
- Regenerate data: `python data/generate_synthetic_restaurant_data.py --seed 42 --out data/synthetic_restaurant_daily.csv` and `python data/make_sample_plates.py`.

## The assistant
It calls five deterministic functions over the app's data — `get_prep_plan`, `get_order_suggestions`, `get_waste_summary`, `get_worst_waste_dishes`, `get_weekday_pattern` — and shows the data it used. Offline it picks the function by keywords; with an LLM, the model calls the same functions and any number in its reply that isn't in the function results is flagged. It never approves plans or places orders.

## Deploy on Streamlit Community Cloud
1. share.streamlit.io → **Create app** → GitHub repo `antequeradiogo-stack/food-waste-prep-planner`.
2. Branch `main` · Main file path `starter/app.py` · Python 3.12.
3. (Optional) Secrets: `LLM_API_KEY = "..."` (and add `openai>=1.0` to `starter/requirements.txt`).

## Contents
| Path | What |
|---|---|
| `starter/app.py` | Entry point: theme, navigation, onboarding tip |
| `starter/views/` | Pages: home, prep, order, cameras, chat, about |
| `starter/ui.py` | Shared data loading, header/banner, how-it-works |
| `starter/core.py` | Forecast + prep suggestions |
| `starter/ordering.py` | Order = forecast × recipe − stock, rounded to packs |
| `starter/plate_waste.py` | Leftover estimate (vision LLM or heuristic), JSON validation, recipe gram math |
| `starter/assistant.py` | Assistant tools, offline answers, LLM tool-calling, number check |
| `starter/cameras.py` | One-frame IP-camera grab (optional OpenCV) |
| `starter/tests/` | pytest + Streamlit AppTest (every page loads, approvals, confirm flows, chat) |
| `data/` | Synthetic sales, recipes, stock, suppliers, plate illustrations + generators + data card |
| `docs/screenshots/` | Screenshots (headless Chrome, synthetic data) |
| `PITCH.md`, `DISCLOSURE.md`, `RESPONSIBLE_AI.md`, `BACKUP_GRANT_AGENT.md` | Hackathon materials |

## Limits
Same-weekday averages ignore weather, holidays and menu changes; sales history undercounts demand on sold-out days; suggestions are never orders. Plate-waste estimates are **unvalidated**: they need calibration against weighed plates in a pilot; camera at the plate-return station only, no guests in frame (GDPR). The waste log and chat live in the browser session only. MIT licensed — see `LICENSE`.
