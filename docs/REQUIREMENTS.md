# Requirements

## Problem and goals

An AI agent you ask plain-English questions about a game's Steam reviews and patch notes. It answers with evidence: numbers computed from the data and quotes from real reviews.

- **Primary goal:** demonstrate production practices for LLM applications end to end:
  - grounded answers with evidence
  - an agent using deterministic tools
  - retrieval
  - evals that run in CI
  - guardrails
  - cost and latency tracking
- **Secondary goal:** keep the option to make it a tool for indie game developers ("what are my players saying?"). Make choices that are cheap now and keep this open (see Scope). Don't build anything only that direction needs.
- **First game:** Monster Train 2 (MT2, Steam app ID `2742830`). It was chosen because the maintainer knows the game and its patch history well, so wrong answers are easy to spot.

## Users

- **Maintainer:** demos and evaluation.
- **An indie developer (secondary goal):** mainly U2 and U4.
- **A prospective player:** U3.

## Use cases

| # | Use case | Example question | Answered from |
|---|---|---|---|
| U1 | Playtime vs sentiment | "Do people who've played longer review it more positively?" | SQL numbers, plus a caveat about self-selection (players who dislike the game stop playing, so long playtimes skew towards fans) |
| U2 | Themes in positive and negative reviews | "What are the most common complaints? And the most common praise?" | Theme tags, with counts and real quotes |
| U3 | Buyer's guide for newcomers | "I've never played it: should I buy it?" | U2's themes turned into "you'll like it if… / skip it if…" |
| U4 | Patch impact | "What changed in the last patch, and how did reviews react?" | Patch notes (RAG) plus a before/after comparison of sentiment and themes (SQL) |

## Scope

**In scope:**
- MT2 reviews and patch notes, with the game as a parameter (its Steam app ID) and all data stored per game.
- U1–U4, answered through an API, with a simple demo.
- Evals and guardrails from the start.
- English reviews only at first (D10).

## Non-goals

| Non-goal | Why |
|---|---|
| Accounts, billing, multi-tenancy | Only the developer-tool direction would need them |
| A polished web interface | The API and a simple demo are enough |
| Live or streaming ingestion | A refresh run on demand is enough (D1) |
| Fine-tuning or training models | Not needed: off-the-shelf models plus retrieval and tools cover the use cases |
| Agent frameworks (LangChain, LangGraph, LlamaIndex…) | See D11 |
| Republishing review text publicly | Steam's terms. Quotes appear in answers, not in a public dataset |
| Storing reviewers' Steam IDs | See D8 |
| Self-hosting models on rented GPUs | See D7 |

## Requirements

| # | Requirement | Done when | Milestone |
|---|---|---|---|
| R1 | Ingest a game's English reviews from Steam (`GetAppReviews`, D9) into Postgres | The stored MT2 count is within 1% of the `total_reviews` Steam reports at the start of the run (5,705 on 2026-11-09) | M0 |
| R2 | Incremental refresh: fetch only reviews that are new or edited since the last run | A second run with no changes on Steam writes nothing. An edited review is updated in place | M0 |
| R3 | Ingest the developer's patch notes from Steam news, filtered from press and other posts, with BBCode cleaned | Each MT2 patch is stored with its date and clean text. A hand-checked patch list backs this up if filtering is unreliable (K2) | M0 (raw) / M3 (clean + patch list) |
| R4 | Never store reviewers' Steam IDs (D8) | The schema has no column for them, and a test checks this | M0 |
| R5 | `/ask` endpoint: a question in, an answer with evidence out, produced by one agent using deterministic tools (D4) | The answer includes the numbers and quotes it relied on | M1 |
| R6 | Numbers come only from SQL tools. The model never calculates them | Every number in an eval answer matches its SQL query | M1 |
| R7 | U1: playtime vs sentiment, using playtime at the time of the review | The answer matches an independent SQL query and mentions self-selection | M1 |
| R8 | The model sits behind one interface and can be swapped per task (D7) | Changing the model for a task is a config change | M1 |
| R9 | Record the model, tokens, cost and latency of every question | Each `/ask` call writes a record with these fields | M1 |
| R10 | Theme tagging of every review as a batch job, with structured output | Every review has schema-valid theme tags. Micro-averaged F1 against a hand-labelled set of about 100 reviews is at least 0.80 | M2 |
| R11 | Review embeddings in pgvector, with a vector-search tool | On about 20 labelled topic queries, including some that share no keywords with the matching reviews, recall@10 is at least 0.7 | M2 |
| R12 | U2: the most common themes in positive and negative reviews | Theme counts match SQL over the tags, and each theme is illustrated by at least one quote that passes R14 | M2 |
| R13 | U3: a buyer's guide built from U2's themes | The answer gives "you'll like it if… / skip it if…" points, each backed by a theme count and a quote | M2 |
| R14 | Every quoted review exists in the data. If a question can't be answered from the data, the agent refuses | Quote checks pass 100%. Out-of-scope eval questions get a refusal | M2 |
| R15 | U4: patch impact, using patch dates, patch notes and before/after tools. The weekly review-count source is added | The "last patch" eval questions are answered correctly | M3 |
| R16 | Guardrails: tools are read-only, review text is treated as data, the agent has an iteration cap, and planted prompt-injection reviews are in the evals | Injection evals pass | M3 |
| R17 | Evals: golden questions with a scorer that reports per category, run in CI with thresholds that fail the build | CI fails when a threshold is broken | M1 (first evals) / M3 (CI gate) |
| R18 | The whole system runs with one command in Docker | `docker compose up` starts the database and the API | M0 (database) / M3 (app) |
| R19 | Hybrid search: Postgres full-text search alongside pgvector, with the two result lists merged by reciprocal rank fusion, then the top ~30 reranked (a local cross-encoder or the model) | On R11's labelled queries, recall@10 is reported for vector only, keyword only, hybrid, and hybrid + rerank. The search tool uses the best of these, and the comparison is written up | M2 |
| R20 | Fallback chain for model calls: timeout, retry with backoff on transient errors only, then a configured second model | A test with a fake failing primary gets its answer from the fallback, and the R9 record shows which model answered. A non-transient error (e.g. 400) is not retried | M1 |
| R21 | Tracing: each `/ask` writes one trace with a request ID and every step (model call, tool call, arguments, result size, tokens, latency). The R9 record is the root of the trace | A failed eval question can be diagnosed from its trace alone, viewed with a CLI command | M3 |
| R22 | MCP server exposing the agent's read-only tools, reusing the same tool definitions as the agent | Claude Code, used as the MCP client, can call every tool and answer a U1 question. A test checks that the agent and the MCP server expose the same tool list | M4 |

## Success criteria

The project is done when R1–R22 pass. The headline bar:

| Area | Criterion |
|---|---|
| Correct numbers | Exact-answer questions match SQL 100% of the time (R6) |
| Grounded answers | 100% of quotes exist in the data, and unanswerable questions are refused (R14) |
| Honest caveats | Correlation answers always mention self-selection (R7) |
| Retrieval and tagging | R10 and R11 thresholds met |
| Engineering | Evals gate CI (R17). One command runs it all (R18) |
| Cost and speed | Recorded per question (R9). Starting targets: under US$0.05 and 15 s per question, to revisit once there are real numbers |

## Constraints

- **Python** (D2).
- **No secrets and no bulk review data in the repo.**
- **API spending:** a monthly limit of about US$20.
- **Steam rate limits:** anonymous calls share a lower limit and get HTTP 429 when they exceed it (D9, K1).

## Risks

| # | Risk | Mitigation | Status |
|---|---|---|---|
| K1 | Steam rate limits or API changes | Pauses between requests, retry with backoff on 429, a fixed User-Agent. Ingestion sits behind a source interface | Open |
| K2 | Patch posts are mixed with DLC announcements and press | Filter by feed and tags. Fall back to a hand-checked patch list | Open |
| K3 | Prompt injection in review text | Read-only tools, review text treated as data, injection evals (R16) | Open |
| K4 | Correlation overclaimed as cause | Guardrail plus an eval check for the caveat (R7) | Open |
| K5 | API spending | Spending limit, cost recorded per question (R9) | Open |
| K6 | A local model may be too slow or weak for bulk tagging | Measure at M2. Fall back to a hosted open-weight model | Open |
| K7 | Only 272 English negative reviews for U2's negative themes | Report counts honestly. Consider adding translated non-English negatives later | Open |

## Milestones

| Milestone | Builds | Done when |
|---|---|---|
| **M0: data in** | Repo, Postgres (pgvector) in Docker Compose, migrations, an `ingest` command for reviews and patch notes, incremental refresh, tests | R1, R2, R4 done. Raw patch notes stored. Database part of R18 |
| **M1: first answers** | `/ask`, agent loop, SQL tools for U1, a swappable model, fallback chain, cost logging, 5–10 eval questions | R5–R9 and R20 done. First evals pass |
| **M2: themes** | Theme-tagging batch, about 100 hand labels, embeddings, hybrid search and reranking, quote checks | R10–R14 and R19 done |
| **M3: patches + production polish** | Patch cleaning and patch list, before/after tools, weekly review counts, guardrails, tracing, CI eval gate, app in Docker | R3 (clean), R15–R18 and R21 done |
| **M4: MCP** | MCP server over the existing tools, demo from Claude Code | R22 done |
| **Later** | Open-weight vs frontier model comparison on the evals, other languages, the developer-tool direction | |

## Open questions

Undecided design choices live in [DECISIONS.md: Open decisions](DECISIONS.md#open-decisions). Assumptions to confirm:

- Open question: on 2026-11-16, `GetAppReviews` (English, `purchase_type` = all, `filter` = updated) reported `total_reviews` = 5,138, not the 5,705 seen on 2026-11-09. All 5,138 were stored, so R1 passes against what Steam reports. The gap may come from a different parameter (such as Steam's off-topic review filter) or from how the 9 Nov count was taken. Check before quoting review totals.
- Assumption: the thresholds in R1 (1%), R10 (F1 0.80) and R11 (recall@10 0.7 on about 20 queries) are starting values. Confirm when each is first measured.
- Assumption: the reranker is a local cross-encoder unless the model reranks better on the R19 comparison. Confirm at M2.
