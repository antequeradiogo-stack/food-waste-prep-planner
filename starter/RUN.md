# Run the starter
Windows PowerShell (from the `starter` folder; Python 3.10+):
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope Process RemoteSigned
pip install -r requirements.txt
pytest -q
streamlit run app.py               # opens http://localhost:8501
```
Optional LLM (never commit keys): `$env:LLM_API_KEY="..."; pip install openai` (and `$env:LLM_BASE_URL`, `$env:LLM_MODEL` for other OpenAI-compatible providers). Without it, the rule-based text is used.
Regenerate data: `cd ..\data; python generate_synthetic_restaurant_data.py --seed 42`
macOS/Linux: same, with `python3 -m venv .venv; source .venv/bin/activate`.
**Before the event:** install once at home (venv + pip) so you don't depend on venue Wi-Fi.
