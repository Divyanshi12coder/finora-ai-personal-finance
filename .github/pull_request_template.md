## What does this change?

<!-- A short description of the change and why it is needed. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor (no behaviour change)
- [ ] Documentation
- [ ] Build / CI

## Checklist

- [ ] `cd backend && pytest` passes
- [ ] `cd frontend && npm run typecheck && npm test && npm run build` passes
- [ ] `ruff check backend/app backend/tests ml` and `ruff format --check ...` pass
- [ ] `cd frontend && npm run lint` passes

## Project-specific checks

These are the rules that keep Finora honest. Tick the ones that apply:

- [ ] **No hardcoded financial values.** Every figure shown to the user is computed
      by the backend from the database, not supplied by the client or written into
      the frontend.
- [ ] **AI does not invent numbers.** If this touches the assistant or insights,
      the figures still come from backend retrieval tools, and the model is only
      phrasing them.
- [ ] **Honest empty states.** If a feature cannot produce a result (too little
      history, no OCR engine, no API key), it says so rather than showing a
      fabricated one.
- [ ] **Per-user isolation.** Any new query is scoped by `user_id`, and there is a
      test proving another user cannot reach the data.
- [ ] **Schema changes have a migration.** `alembic revision --autogenerate` was run
      and the migration applies and reverses cleanly.
- [ ] **ML changes are reproducible.** If the dataset or pipeline changed,
      `python -m ml.build_dataset` and `python -m ml.train` were re-run and the
      metrics in the PR description come from that run.

## Screenshots

<!-- For UI changes, include before/after in both light and dark mode. -->
