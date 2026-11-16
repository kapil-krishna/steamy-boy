# Decisions

Each entry records its status, the context, the decision, the reasons, the alternatives rejected and the consequences. A reversal gets a new entry, and the old one's status becomes "Superseded by Dn".

## D1: Store a snapshot and refresh it incrementally (2026-11-09)

**Status:** Accepted

**Context:** questions could be answered by calling Steam on every request, or from stored data.

**Decision:** fetch all reviews once into Postgres. A refresh job then fetches only new or edited reviews. Questions run against the local data, in production as well.

**Rejected:**
- **Live calls on every question:** hundreds of sequential requests (100 reviews per page), so minutes per question, and rate limits. U1 and U2 need every review at once. RAG needs embeddings computed in advance. Theme tagging would be paid for on every question. Evals need a fixed snapshot to give stable results.
- **JSON files:** counting, filtering and vector search get awkward.

**Consequences:** the data is small, roughly 20–50 MB plus vectors for one game. The refresh has to handle edited reviews. Answers are only as fresh as the last refresh.

## D2: Python (2026-11-09)

**Status:** Accepted

**Context:** the workload is HTTP ingestion, SQL, statistical analysis and calls to model APIs.

**Decision:** Python.

**Reasons:** the analysis (pandas, scipy) and the AI ecosystem (SDKs, embedding libraries, eval tooling) are Python-first. The plumbing (HTTP, SQL, calling a model SDK) is equally easy in any mainstream language, so the analysis and AI parts decide it.

**Rejected:**
- **Java (Spring Boot):** no technical advantage for this workload, and a thinner AI ecosystem.
- **A Java service plus Python scripts:** two toolchains for a small project.

**Consequences:** the toolchain is chosen in D6.

## D3: Postgres with pgvector, in Docker (2026-11-09)

**Status:** Accepted

**Context:** the tools need relational queries (counts, group-bys, before/after comparisons) and vector search over review embeddings.

**Decision:** Postgres with the pgvector extension, run with Docker Compose.

**Reasons:** one database holds the rows and the vectors, so a single query can filter with SQL and rank by similarity. There's no second store to keep in sync. It's also a database the app could run on unchanged in production.

**Rejected:**
- **SQLite with sqlite-vec:** the vector extension is less mature.
- **DuckDB:** excellent for analysis, but weak at serving an API and at vector search.
- **A separate vector database:** a second store to run and keep in sync, for a data set this small.

**Consequences:** local development needs Docker.

## D4: One agent with deterministic tools (2026-11-09)

**Status:** Accepted

**Context:** U1–U4 need exact numbers and a written explanation of them.

**Decision:** a single `/ask` path. The agent decides which tools to call and writes the answer. The SQL tools compute every number. The rule is **"numbers come from SQL; the model only explains them."**

**Rejected:**
- **The agent computes numbers itself:** LLMs make arithmetic mistakes.
- **Fixed reports for U1/U2 plus a separate agent:** two paths to build and maintain.

**Consequences:** what can be answered is bounded by the tools. A question no tool covers gets a refusal (R14).

## D5: psycopg 3 with plain SQL and numbered SQL migration files (2026-11-09)

**Status:** Accepted

**Context:** the tools are mostly hand-written aggregate queries.

**Decision:** use psycopg 3 with plain SQL queries. Schema changes are numbered `.sql` migration files.

**Reason:** the queries are the core of the tools, and plain SQL keeps every one visible and easy to review.

**Rejected:**
- **SQLAlchemy + Alembic:** more setup, and the abstraction hides the queries.

**Consequences:** mapping rows to Pydantic models is written by hand. Migrations need a small runner (D12).

## D6: Python toolchain: uv, Pydantic, pytest, ruff (2026-11-09)

**Status:** Accepted

**Context:** the project needs environments and dependencies, validation of external data, tests, and linting and formatting.

**Decision:** uv for environments and dependencies, Pydantic models at every boundary, pytest for tests, ruff for linting and formatting.

**Reasons:**
- **uv:** one fast tool for the Python version, the virtualenv and a lockfile.
- **Pydantic:** Steam responses and model output are untrusted, so they're validated where they enter the system.
- **pytest:** the standard test runner, with fixtures for faking Steam and model calls.
- **ruff:** one fast tool that replaces flake8, isort and black.

**Rejected:**
- **pip + venv:** no lockfile.
- **Poetry:** slower, and uv covers the same ground.

**Consequences:** contributors need uv installed.

## D7: The right model for each task, swappable, with no self-hosted GPUs (2026-11-09)

**Status:** Accepted

**Context:** the tasks differ. Bulk tagging of thousands of reviews is high-volume and simple. The agent needs reliable tool calling.

**Decision:** all model calls go through one interface, and the model is configured per task.

| Task | Model |
|---|---|
| Theme tagging (bulk batch) | An open-weight model, local (Ollama/MLX) or hosted (OpenRouter). It doesn't need a frontier model |
| The agent (`/ask`) | The best tool-caller that passes the evals. Chosen at M1 |
| Sentiment | No model. Steam's `voted_up` flag gives it directly |

Every choice is justified by eval scores, cost and latency.

**Rejected:**
- **Renting a GPU to self-host a large open model:** it's billed by the hour whether used or not (about US$0.50–3/h, or US$350–2,000 a month if always on), compared with about US$10–30 for the whole project on per-token APIs. It also adds infrastructure that doesn't serve the goals.
- **A single model for everything:** overpays for bulk work.

**Consequences:** comparing models on the evals is a planned later step.

## D8: Don't store reviewers' Steam IDs (2026-11-09)

**Status:** Accepted

**Context:** `GetAppReviews` returns each author's Steam ID.

**Decision:** drop `author.steamid` at ingestion. `recommendationid` is the unique key.

**Reason:** not needed, so it isn't kept. This is data minimisation.

**Rejected:**
- **Storing a salted hash of the ID:** only needed if there were no review ID, which there is.

**Consequences:** questions about individual reviewers can't be answered. None of U1–U4 needs them.

## D9: Reviews from `IUserReviewsService/GetAppReviews` (2026-11-09)

**Status:** Accepted

**Context:** `store.steampowered.com/appreviews/<appid>?json=1` now redirects to the store homepage for every game. Steam's documentation marks it deprecated.

**Decision:** use `GET https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/` with no key.
- Parameters go in `input_json`.
- To page through every review, use `filter` 1 (Recent) or 2 (Updated) with the cursor. The default Helpful filter keeps returning reviews and never ends.
- Patch notes come from `ISteamNews/GetNewsForApp/v2` (no key).
- The weekly review counts come from `store.steampowered.com/appreviewhistogram/<appid>` (no key).

**Reasons:**
- It returns everything the plan needs, including `playtime_at_review`.
- It adds a `refunded` field (refund questions become answerable) and `developer_response`.
- A key is optional, and only a *publisher* key raises the rate limit.

**Rejected:**
- **Scraping the community review pages (HTML):** fragile, and it lacks playtime at review and a review ID.

**Consequences:** anonymous calls share a lower rate limit and get HTTP 429 when they exceed it, so ingestion backs off (K1). Responses may be cached for up to 10 minutes.

## D10: English reviews only at first (2026-11-09)

**Status:** Accepted

**Context:** on 2026-11-09 MT2 had about 8,900 reviews in all languages: 5,705 in English (5,433 positive, 272 negative).

**Decision:** ingest English reviews only.

**Reason:** every answer and every eval label can be checked by hand.

**Rejected:**
- **All languages:** answers and labels in languages the maintainer can't read can't be checked.

**Consequences:** only 272 negative reviews (K7). Other languages are a later option.

## D11: No agent framework (2026-11-09)

**Status:** Accepted

**Context:** the agent loop is: call the model, run the tools it asks for, return the results, and repeat until it answers or hits a cap.

**Decision:** use the model providers' SDKs directly and write the agent loop by hand.

**Reason:** the loop is small, and owning it keeps tool calls, retries, limits and tracing explicit and easy to test.

**Rejected:**
- **LangChain, LangGraph, LlamaIndex:** abstraction over a small loop, which makes it harder to debug and test.

**Consequences:** retries, the iteration cap (R16) and cost logging (R9) are written by hand.

## D12: A hand-written migration runner (2026-11-10)

**Status:** Accepted

**Context:** D5 left open whether to write a migration runner or use an existing tool.

**Decision:** a small runner in `db.py`. It applies the `.sql` files in filename order, each in one transaction with its row in a `schema_migrations` table.

**Reasons:** it's about 30 lines, has no extra dependency and keeps migrations as plain SQL.

**Rejected:**
- **yoyo-migrations, dbmate, Flyway:** another tool or runtime to install, and none of their extra features (rollbacks, branching) is needed yet.

**Consequences:** no down-migrations, so a mistake is fixed with a new migration. The runner doesn't lock against two concurrent runs, which is fine while there's one maintainer.

## D13: Ingest checkpoints in `ingest_runs`, and soft deletes via a full run (2026-11-16)

**Status:** Accepted

**Context:** incremental refresh (R2) needs to know where the last run got to. Reviews arrive newest edit first and are saved a page at a time, so after a crash the newest reviews are stored but older ones aren't. Steam can't tell us which reviews were deleted.

**Decision:**
- An `ingest_runs` table records each run. A normal run fetches back to one hour before the start of the last *finished* run, then stops. The hour covers Steam's response cache.
- Reviews are upserted, and an existing row changes only when Steam's `updated_at` is newer. News posts are inserted with `ON CONFLICT DO NOTHING`.
- `ingest --full` reads every page. If it completes, stored reviews it didn't see get `deleted_at` set (a soft delete). It refuses if that would be more than 5% of the game's reviews. A soft-deleted review that comes back is restored.

**Reasons:**
- Using the newest stored `updated_at` as the checkpoint would make the run after a crash stop straight away and never fetch the older reviews.
- One transaction per page means a crash loses at most one page, and the upserts make re-reading pages harmless.
- A soft delete keeps the review, so analysis can include or exclude deleted ones. The 5% limit stops a bad Steam response from marking everything deleted.

**Rejected:**
- **Checkpoint from the newest stored review:** fails after a crash, as above.
- **One transaction for the whole run:** a crash late in the run throws away everything, and the transaction stays open during slow network calls.

**Consequences:**
- Vote counts (`votes_up`, `votes_funny`, `weighted_vote_score`) can change without Steam changing `updated_at`, so a normal refresh doesn't pick those changes up. A full run doesn't either, because the upsert skips unedited reviews. Open question: refresh vote counts when a question needs them.
- Deletions are found only by `ingest --full`, so it should run now and then (for example weekly).
- Analysis queries exclude soft-deleted reviews with `WHERE deleted_at IS NULL`.
- For a game with very few reviews, the 5% limit blocks any deletion. That's acceptable while the project covers one game.

## Open decisions

| Topic | Decide at |
|---|---|
| API framework. Assumption: FastAPI | M1 |
| Agent model and hosted provider | M1, based on evals |
| Demo: command line or simple web page | M1 |
| Embedding model | M2, based on retrieval evals |
| Theme list: fixed categories, or discovered by the model and then fixed | M2 |
| Cloud deployment | After M3 |
