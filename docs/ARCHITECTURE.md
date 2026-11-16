# Architecture

Planned design. Nothing is built yet.

## Shape

```
  Steam APIs: reviews, news, review counts
          │
          ▼
  ingest (CLI) ─────► Postgres + pgvector ◄───── enrich (batch job)
                      reviews, patches,          theme tags, embeddings
                      tags, embeddings                  │
                            ▲                           │
                            │ read-only SQL             │
                            │ and hybrid search         │
                            │                           ▼
  POST /ask ─► agent loop ─► tools          model interface ─► model provider
                   │                               ▲
                   ├───────────────────────────────┘
                   ▼
           answer + evidence, plus a usage record (model, tokens, cost, latency)

  evals (CI): golden questions ─► /ask ─► scorer ─► pass/fail per category
```

- **Ingest** gets each source through a source interface, so a Steam API change touches one module (K1). It stores data per game (by app ID) and drops the reviewers' Steam IDs (D8).
- **Enrich** tags and embeds reviews in batches, through the same model interface as the agent.
- **Tools** are the only way the agent reaches data. They're read-only and compute every number (D4). Search combines full-text and vector results, then reranks them (R19). An MCP server exposes the same tool definitions to outside clients (R22).
- **The model** is reached through one interface and configured per task (D7). The interface owns the fallback chain (R20).
- **Tracing:** each `/ask` writes one trace of its steps, rooted at the usage record (R21).

## Stack

| Concern | Choice | Decision |
|---|---|---|
| Language | Python | D2 |
| Tooling | uv, Pydantic, pytest, ruff | D6 |
| Database | Postgres + pgvector in Docker Compose | D3 |
| Data access | psycopg 3, plain SQL, numbered `.sql` migrations | D5 |
| Data sources | `GetAppReviews`, `GetNewsForApp`, `appreviewhistogram` | D9 |
| Models | Per task, behind one interface | D7 |
| Agent | Provider SDKs, hand-written loop, no framework | D4, D11 |
| API framework | Not decided | [Open decisions](DECISIONS.md#open-decisions) |

## Data model

Open question: the schema is designed at M0. Agreed so far:
- Reviews are keyed by `recommendationid` and store `playtime_at_review`. There's no Steam ID column (R4).
- Patches are stored with their date and text.
