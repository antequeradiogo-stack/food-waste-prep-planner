# Responsible AI checklist (20% of score + tie-breaker)
## Data
- [ ] Every dataset listed with URL/licence, or marked SYNTHETIC with generator + assumptions.
- [ ] No personal data, passwords, keys or confidential records in prompts, slides, repo, screenshots.
- [ ] `.env` / API keys never committed or shown on screen.
## Source transparency
- [ ] Each recommendation shows its reason (inputs + rule), not just a number.
- [ ] LLM output only rephrases data; prompt forbids adding numbers; we check it in the demo.
- [ ] Any external fact on slides has a source URL; "demonstrated" vs "estimated" separated.
## Human oversight
- [ ] Tool suggests; a person approves/edits. No automatic ordering, discarding, or submission.
- [ ] Approval step visible in the demo.
## Limits & failure safeguards
- [ ] Limits box in the app (synthetic data, censored demand, no weather/events, cold start).
- [ ] Low-data items flagged; LLM failure falls back to rule-based text; bad CSV gives a clear error.
- [ ] Who could be harmed if wrong? (over-prep = waste; under-prep = lost sales/unhappy guests) and how we limit it (buffer, manual check).
## Privacy & fairness
- [ ] Approver recorded by role, not full name.
- [ ] Grant challenge: no applicant personal data; nonprofit eligibility judged by a human.
## Claims
- [ ] No invented user validation or impact figures. Say "we expect / would measure", not "reduces waste by X%".
