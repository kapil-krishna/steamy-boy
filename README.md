# steamy-boy

Ask plain-English questions about a game's Steam reviews and patch notes, and get answers backed by evidence: numbers computed from the data and quotes from real reviews.

- "Do people who've played longer review it more positively?"
- "What are the most common complaints, and the most common praise?"
- "I've never played it: should I buy it?"
- "What changed in the last patch, and how did reviews react?"

It starts with Monster Train 2. Under the hood it's an agent that uses deterministic SQL and vector-search tools over a Postgres snapshot of the reviews. Every number comes from SQL, and the model only explains the numbers. Evals run in CI.

## Status

- [ ] M0: reviews and patch notes ingested into Postgres, with incremental refresh
- [ ] M1: `/ask` answers playtime-vs-sentiment questions, with first evals
- [ ] M2: theme tagging, vector search, grounded quotes
- [ ] M3: patch-impact questions, guardrails, eval gate in CI

## Docs

- [Requirements](docs/REQUIREMENTS.md)
- [Decisions](docs/DECISIONS.md)
- [Architecture](docs/ARCHITECTURE.md)
