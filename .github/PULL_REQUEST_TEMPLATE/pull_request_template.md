## Summary

<!-- One-sentence description of what this PR does. -->

Closes #<!-- issue number -->

---

## Approach & Assumptions

<!-- Describe the implementation approach. Explain any important assumptions, trade-offs, or design decisions. -->

---

## Testing Evidence

<!-- How was this tested? Include commands to reproduce. -->

```bash
# example
pytest tests/integration/test_risk_scorer.py -v
```

- [ ] Unit tests pass locally
- [ ] Integration tests pass locally
- [ ] End-to-end demo pipeline runs without manual intervention
- [ ] `ruff check` and `black --check` pass (Python)
- [ ] `eslint` and `prettier --check` pass (Frontend)

---

## Screenshots / Recordings

<!-- For UI changes, attach screenshots or a screen recording. Delete this section if not applicable. -->

---

## Data & Security Implications

<!-- Does this PR add, remove, or change data handling? Does it touch any credentials, PII, or external APIs? -->

- [ ] No secrets or credentials added
- [ ] No PII or unrestricted datasets committed
- [ ] Geospatial outputs labelled [HISTORICAL] / [SIMULATED] / [LIVE] where applicable
- [ ] Alert dispatcher remains in `mock` mode

---

## Infrastructure Rollback Note

<!-- For infrastructure changes only: describe how to roll back if something goes wrong. Delete this section if not applicable. -->

---

## Reviewer Notes

<!-- Anything specific you want reviewers to focus on or verify. -->
