# Contributing to TerraSentinel-Nepal

Thank you for contributing. This document describes the workflow, coding standards, and review process for all contributions.

---

## Getting Started

1. Read the [README](README.md) and [architecture docs](docs/architecture/).
2. Pick an issue from the [project board](https://github.com/your-org/TerraSentinel-Nepal/projects/1) or open a new one using the appropriate issue template.
3. Comment on the issue to indicate you are working on it.
4. Fork the repository or, for team members, create a branch directly.

---

## Branch Naming

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `feature/<short-description>` | `feature/risk-map` |
| Bug fix | `fix/<short-description>` | `fix/alert-zone-filter` |
| Documentation | `docs/<short-description>` | `docs/risk-model-assumptions` |
| Infrastructure | `infra/<short-description>` | `infra/sagemaker-endpoint` |
| Experiment | `experiment/<short-description>` | `experiment/ndwi-threshold-tuning` |

Branches must be short-lived and created from the latest `main`.

---

## Coding Standards

### Python
- Follow **PEP 8**. Use `ruff` for linting and `black` for formatting.
- Type-annotate all public functions.
- Write docstrings (Google style) for all modules, classes, and public functions.
- Unit-test coverage target: **≥ 80 %** for new code in `services/` and `ml/`.

### JavaScript / TypeScript (Frontend)
- Use **ESLint** (Airbnb config) and **Prettier**.
- Prefer TypeScript for all new files.
- No hardcoded API URLs — use environment variables via `.env.example`.

### Geospatial
- Always record CRS, resolution, and data-source attribution in processing scripts.
- Tag outputs with `[HISTORICAL]`, `[SIMULATED]`, or `[LIVE]` metadata fields.
- Do not commit raster files > 5 MB. Use the sample data in `data/sample/`.

### General
- No secrets, credentials, phone numbers, or unrestricted datasets in any commit.
- Keep functions short and single-purpose.
- Prefer explicit error messages over silent failures.

---

## Commit Messages

Use the **Conventional Commits** format:

```
<type>(scope): <short imperative summary>

[optional body — explain WHY, not WHAT]

[optional footer: closes #issue-number]
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `infra`, `data`

Examples:
```
feat(geospatial): add NDWI water-change computation for Sentinel-2
fix(alert-dispatcher): correct Nepali voice synthesis encoding
docs(risk-methodology): document high-risk threshold assumptions
```

---

## Pull Request Process

1. **One PR per issue.** Reference the issue with `Closes #<N>`.
2. Fill in the pull-request template completely.
3. Keep PRs small — aim for < 400 lines changed per review.
4. Use a **draft PR** for early feedback before the implementation is complete.
5. Ensure all automated checks pass before requesting review.
6. At least **one reviewer must approve** before merging.
7. All review comments must be resolved or explicitly dismissed with a reason.
8. Use **squash merge** to keep `main` history readable (team policy).

### PR Checklist

- [ ] Linked issue in PR description
- [ ] Tests added or updated
- [ ] `ruff` / `eslint` pass locally
- [ ] No secrets or large files added
- [ ] Data-layer outputs labelled (HISTORICAL / SIMULATED / LIVE)
- [ ] Documentation updated if behaviour changed
- [ ] Screenshots or recording attached for UI changes
- [ ] Rollback note added for infrastructure changes

---

## Testing

```bash
# Python unit & integration tests
pytest tests/ -v --cov=services --cov=ml --cov=geospatial

# Frontend tests
cd frontend && npm test

# End-to-end demo pipeline
python tests/e2e/run_melamchi_scenario.py
```

All tests must pass in CI before a PR can be merged.

---

## Reporting Issues

Use the issue templates in `.github/ISSUE_TEMPLATE/`:

| Template | Use for |
|----------|---------|
| `feature_request.md` | New capabilities |
| `bug_report.md` | Defects and unexpected behaviour |
| `data_issue.md` | Missing, corrupt, or unlicensed data |
| `research_task.md` | Algorithm investigations and experiments |

---

## Questions

Open a GitHub Discussion or comment on the relevant issue. Do not share credentials or personal data in public issue threads.
