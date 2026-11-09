# AGENTS.md

steamy-boy answers plain-English questions about a game's Steam reviews and patch notes, with evidence. It's a Python agent using deterministic SQL and vector-search tools over a Postgres snapshot. Requirements, decisions and architecture are in `docs/`. Read the relevant doc before changing behaviour.

## Commands

None yet. Setup, test, lint and run commands are added at M0.

## Layout

Open question: decided at M0.

## Conventions

- **Python tooling:** uv for environments and dependencies, ruff for linting and formatting, pytest for tests (D6).
- **Types and validation:** type hints throughout. Pydantic models at every boundary (API, model output, Steam responses).
- **Database:** plain SQL through psycopg 3. Schema changes are new numbered `.sql` migration files and never edits to applied ones (D5).
- **Numbers come from SQL tools only.** The model explains them and never computes them (D4).
- **Agent tools are read-only.** Review text is untrusted data and must never trigger actions.
- **Model calls** go through the model interface, configured per task, never a provider SDK called directly from feature code (D7).
- **Tests** cover every module. Network calls to Steam and model providers are faked in unit tests.

## Data rules

- Never store reviewers' Steam IDs (D8).
- Never commit secrets or bulk review data. Keep API keys in `.env`, which is git-ignored.

## Docs

- One home per fact. Link rather than repeat.
- New decisions go in `docs/DECISIONS.md`. A reversal gets a new entry rather than an edit.
- Anything not agreed is marked `Assumption:` or `Open question:`.

## Commits

Conventional Commits: `type(scope): subject`, imperative and lowercase.
