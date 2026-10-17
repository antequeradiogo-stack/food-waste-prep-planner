# Run Leftover Lab
From the **repo root** (so `.streamlit/config.toml` theme loads), Python 3.10+:
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope Process RemoteSigned
pip install -r starter/requirements.txt
pytest -q starter
streamlit run starter/app.py       # opens http://localhost:8501
```
Optional LLM (never commit keys): `$env:LLM_API_KEY="..."; pip install openai` (and `$env:LLM_BASE_URL`, `$env:LLM_MODEL`, `$env:VISION_MODEL`). Without it, offline rule-based answers are used.
Optional IP-camera snapshot: `pip install opencv-python-headless`.
macOS/Linux: same, with `python3 -m venv .venv; source .venv/bin/activate`.
**Before the event:** install once at home (venv + pip) so you don't depend on venue Wi-Fi.
