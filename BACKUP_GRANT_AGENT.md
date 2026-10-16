# Backup idea — Challenge 1: AI Grant Application Agent (~2.5 h scope)
**User:** volunteer coordinator at a small nonprofit with no fundraising staff. **Need:** find which grants fit, why, and get a first draft — without missing deadlines or submitting nonsense.

**Scope (buildable on the day, Streamlit + pandas):**
1. Load a small table of grant calls (8–15 rows) the team compiles **on the day** from public funder web pages: name, funder, URL, deadline, max amount, eligibility text, focus. (Or a clearly-labelled synthetic table if Wi-Fi fails.)
2. Nonprofit profile form (mission, location, size, focus) — fictional org, no personal data.
3. Match & rank: rule-based score (focus keyword overlap, location, deadline not passed, size) with the matched criteria shown; optional LLM summary of eligibility, each with the source URL.
4. Draft helper: LLM (or template fallback) drafts a 150-word project summary from the profile, marked DRAFT.
5. Human checklist: "eligibility confirmed by a person", "deadline checked on funder site", "submitted manually by: ___". **No submit button** — the app never submits.

**Data:** public funder pages (cite each URL, check terms) or synthetic. Keep the CSV in the repo with a source column.
**Demo (90 s):** fill profile → ranked grants with reasons + links → open one source → generate draft → tick human checklist → export (CSV/markdown).
**Responsible AI:** sources shown per grant; LLM text labelled draft; deadline/eligibility must be confirmed on the source; no auto-submission (explicit rule); failure fallback = template text; limits = small hand-picked list, eligibility text can be outdated.
**Reuse from starter:** CSV loading, human-approval pattern, assumptions box, LLM-with-fallback pattern (disclose).
