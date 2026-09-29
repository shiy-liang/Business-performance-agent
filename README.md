# Business Performance Agent

Owners of small and medium-sized enterprises receive business information from
multiple sources, including sales reports, accounting systems, inventory records,
customer enquiries, and operational updates. Because information is scattered
across different systems and reports, business owners spend considerable time
reviewing data before understanding overall business performance and identifying
issues that require immediate attention.

This prototype combines those sources in a FastAPI application with a browser-based
business performance dashboard. It currently includes:

- company-wide or store-level financial pulse
- urgent inventory alerts and the oldest unresolved priority tickets
- best-selling, highly rated, high-return and low-rated product rankings
- campaign ROI and conversion rankings
- a LangGraph-based Supervisor with Finance and Operations specialists, governed SQL,
  pgvector retrieval, and evidence citations
- deterministic business risk detection with standardized Candidate Issues and Ask Agent
  investigation

## Run the dashboard on this computer

The root `.env` file must contain a valid Supabase pooler
`DATABASE_URL`. Keep that file local; it is excluded from Git.

```bash
cd Business-Performance-Agent
source .venv/bin/activate
uvicorn app:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). FastAPI documentation is
available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

For the Windows Conda development environment, install and test with:

```powershell
conda activate agent_project
python -m pip install -r requirements-dev.txt
python -m pytest -v
```

## Initialize a separate, empty database

Only use these steps when intentionally setting up a separate, empty Supabase
project. Configure `.env` to point to that new project first. Obtain the source
CSV files separately and place them in `data/raw/`; datasets are not included in
this repository.

1. Run `database/schema.sql` in the Supabase SQL Editor.
2. Generate the cleaned and synthetic CSV files.
3. Load them into PostgreSQL.

```bash
python clean_data.py
python generate_synthetic_data.py
python database/load_data.py
```

`load_data.py` resets and reloads the project tables, so use it for initial
setup or an intentional full refresh. To update only previously loaded synthetic
expense rows after regenerating them, run:

```bash
python database/update_expenses.py
```

## Dashboard API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Verify FastAPI and Supabase connectivity |
| `GET` | `/api/dashboard/stores` | Populate the company/store filter |
| `GET` | `/api/dashboard/financial-pulse` | Three finance cards and a 12-month trend |
| `GET` | `/api/dashboard/action-center` | Severe stock alerts and long-open priority tickets |
| `GET` | `/api/dashboard/product-performance` | Four Top-5 product rankings |
| `GET` | `/api/dashboard/marketing-performance` | Top campaigns overlapping the selected month |
| `POST` | `/api/runs` | Create an observable finance or business-performance run |
| `POST` | `/api/runs/{run_id}/execute` | Execute the workflow for a run |
| `GET` | `/api/runs/{run_id}` | Retrieve the current run status |
| `GET` | `/api/runs/{run_id}/events` | Retrieve events recorded during a run |
| `POST` | `/api/chat` | Run the Supervisor and return the collected answer |
| `POST` | `/api/chat/stream` | Stream public progress, tool events, answer tokens, and citations over SSE |
| `POST` | `/api/sessions` | Create a persistent chat session |
| `DELETE` | `/api/sessions/{session_id}` | Delete a persisted chat session and its history |
| `POST` | `/api/knowledge/files` | Validate, store, split, embed, and index one TXT/PDF/CSV file |
| `GET` | `/api/knowledge/files` | List registered knowledge-base source files |
| `GET` | `/api/knowledge/files/{file_id}/download` | Download a managed source file |
| `DELETE` | `/api/knowledge/files/{file_id}` | Delete a source file, its record, and its vector chunks |
| `POST` | `/api/knowledge/reviews/sync` | Embed customer reviews and support tickets whose embedding value is null |

The month-based endpoints accept `month=YYYY-MM`. Finance, inventory and product
sales also accept `store_id`; campaign and support-ticket source data do not have
a store identifier.

Chat conversations use UUID-keyed sessions persisted in PostgreSQL. The frontend creates a
session when the page opens and sends its `session_id` with every chat request.
User and assistant messages are stored in `chat_messages`, while session metadata is
stored in `chat_sessions`. Runtime, tool, skill, retrieval, and token events are excluded.
The Agent receives at most the most recent `MAX_CONTEXT_MESSAGES` messages (20 by default).
New Chat deletes the current session and starts an empty one.

`database/schema.sql` creates the PostgreSQL schema and pgvector extension.
Uploaded file chunks are indexed in `unstructured_knowledge_chunks`, while the
review sync endpoint populates row-level embeddings in `customer_reviews` and
`support_tickets`.

Product costs, inventory, expenses, returns/refunds and campaign attribution are
synthetic prototype data. Financial metrics that depend on them are labelled as
estimates in the interface.

## Knowledge source file management

The dashboard accepts one `.txt`, `.pdf`, or `.csv` file at a time by file picker,
drag-and-drop, or clipboard paste. The backend streams the upload through SHA-256,
rejects empty, unsupported, mismatched, oversized (over 25 MB), and duplicate
files, then saves it under `data/knowledge_files/` using its hash as the storage
path. The original filename and file metadata are written to `knowledge_files`.

The allowed file types and MIME types, local storage directory, maximum file
size, filename limit, unknown-MIME fallback, upload stream chunk size, semantic
chunk size, chunk overlap, and separator priority are configured in
`config/rag.yml`. The upload stream size controls physical file reads and is
separate from semantic chunking.

After storage, LangChain lazily loads the TXT, PDF, or CSV source and splits its
text into overlapping chunks. The shared embedding model converts those chunks
to vectors, which are upserted into `unstructured_knowledge_chunks` with
`source_type=other` and the matching `knowledge_files.file_id` as `source_id`.
The database registration and vector rows are committed together; a processing
failure rolls them back and removes the newly stored file.

## Supervisor and specialist agents

The chat panel is connected to a three-agent LangGraph runtime under `rag/agent/`.
The user-facing Supervisor routes structured questions to Finance or Operations.
High-frequency review, support-ticket, and financial calculations use dedicated
deterministic workflows, while other specialist questions use governed PostgreSQL
generation as a long-tail fallback. Models are accessed through `langchain-openai` using Aliyun Bailian's OpenAI-compatible API.
The primary chat model is `qwen3.7-plus`, with `qwen3-max` configured as fallback. Tool permissions are
enforced centrally in `rag/agent/tools/registry.py`, and safe public progress is
streamed through `/api/chat/stream`.

FastAPI initializes the shared tool registry, Finance and Operations graphs,
Supervisor graph, and their model clients during application startup. The same
compiled graphs and clients are reused for every default chat request.

The current tools are:

- `search_knowledge`: semantic pgvector retrieval with file and chunk citations.
- `delegate_finance`: runs the Finance specialist graph.
- `delegate_operations`: runs the Operations specialist graph.
- `find_real_name`: shared by Finance and Operations; maps a fuzzy or
  cross-language product phrase to ranked exact `public.products.product_name`
  values using a fixed Top-5 pgvector query, a 0.70 minimum similarity, and a
  0.20 absolute adjacent-score gap cutoff.
- `find_real_campaign_name`: shared by Finance and Operations; maps a fuzzy,
  abbreviated, or cross-language campaign phrase to exact
  `public.campaigns.campaign_name` values. It uses the same Top-5, three-attempt,
  similarity-threshold, and adjacent-score-gap rules as `find_real_name`.
- `search_finance_schema`, `resolve_finance_entity`, `execute_finance_sql`:
  Finance-only schema, entity, and read-only SQL capabilities.
- `load_finance_skills`: loads only the Finance workflow bodies selected from the
  compact routing catalog; full Finance skills are not placed in the initial
  specialist prompt.
- `calculate_net_sales`: Finance-only fixed query over `transactions` and
  completed `returns_refunds`, returning sales after discounts and completed
  refunds for one optional date/entity scope.
- `calculate_gross_profit`, `calculate_gross_margin`: Finance-only fixed queries
  over `transactions`, completed `returns_refunds`, and `products`, returning
  cost-covered recognized revenue, COGS, gross profit, gross-margin percentage,
  and cost coverage. They calculate recorded-data metrics and do not forecast.
- `search_operations_schema`, `resolve_operations_entity`,
  `execute_operations_sql`: Operations-only equivalents.
- `search_customer_reviews`: Operations-only semantic review retrieval with date,
  product, category, and rating filters; one product-filtered call by default and
  at most three for distinct themes or an explicit comparison. Non-comparison
  runs are locked to the first product.
- `find_other_comment_product`, `find_other_comment_category`: Operations-only
  fixed-query expansion tools. They exclude reviews already returned in the run,
  return at most ten rows each, and share a two-call limit.
- `check_concrete_problem`: Operations-only semantic retrieval over concrete
  descriptions in `support_tickets.notes`, with optional submission-date,
  category, priority, and resolution-status filters. It is limited to one call
  per Operations run and returns at most ten ticket examples.
- `check_purchase_rate`: Operations-only fixed-query tool for the ratio of
  `purchase` events to combined `checkout`, `wishlist_add`, and `add_to_cart`
  events for one canonical product name.
- `check_like_rate`: Operations-only fixed-query tool for the ratio of combined
  `wishlist_add` and `add_to_cart` events to `product_view` events for one
  canonical product name.
- `check_less_like`: Operations-only fixed-view Tool returning up to ten products
  with their precomputed `like_rate`, ordered ascending.
- `check_less_purchase`: shared by Operations and Finance; returns up to ten
  products with their precomputed `purchase_rate`, ordered ascending.
- `check_most_interact`: Operations-only fixed-query Tool returning up to ten
  products with total duration, average duration, interaction count, and ranking
  fields, with a minimum sample of 20 interaction rows per product.

Finance and Operations share a reusable specialist graph but have independent
prompts, progressively loaded skills, table permissions, and tool instances. Their handlers register
with `specialist_dispatcher` when the Supervisor graph is built. Prompts and skills
are Markdown files under `rag/agent/prompts/` and `rag/agent/skills/` and are
injected at runtime.

Generated SQL is parsed with `sqlglot` before execution. The runtime accepts only
one explicit-column `SELECT`, applies per-agent table and column allowlists, blocks
sensitive and vector columns, dangerous functions, locking reads, DDL/DML, and
system schemas, then executes inside a read-only transaction with a timeout and
result cap. Configure a database role with SELECT-only grants through
`AGENT_READONLY_DATABASE_URL`; `DATABASE_URL` is a development fallback.

After local validation and before any database access, every model-generated SQL
query pauses for explicit user approval. The chat UI shows the complete
parameterized SQL and its bound parameter values with **Execute** and **Cancel**
actions. Execute resumes the same Agent run; Cancel returns a `user_rejected`
result to the specialist and Supervisor without opening a database connection.
Pending approvals expire after `AGENT_SQL_APPROVAL_TIMEOUT_SECONDS` (15 minutes by
default) and fail closed. Dedicated fixed-query and semantic-retrieval skills do
not use this generic-SQL approval step.

The chat composer includes an **Automatically execute SQL** checkbox, which is off
by default. When enabled for a request, validated model-generated read-only SQL
runs without creating an approval prompt; all table allow-lists, timeouts, row
limits, and other SQL safety controls remain in force.

Every SQL attempt writes a structured `sql.generated` log event containing the
Agent-generated query text but not its parameter values. Local validation failures
retain `error_type=validation_error` and add a stable `validation_error_type` plus
a concrete validation message, allowing parser, policy, allowlist, alias, column,
and parameter failures to be distinguished without logging query results.

Every specialist result passes a deterministic evidence check before the
Supervisor may use it. Generic workflows require a successful domain-matching SQL
result. The dedicated product-review workflow instead requires a successful
`search_customer_reviews` call, forbids mixing in generic SQL tools, and validates
the returned review citations. The dedicated support-ticket problem workflow
accepts `check_concrete_problem` evidence and validates `[ticket:...]` citations.
Finance net-sales, gross-profit, and gross-margin workflows use fixed
parameterized queries and validate their `[db:finance:...]` evidence without
entering generated SQL approval.
Validation outcomes are emitted as public `validation` events.
`AGENT_KNOWLEDGE_MIN_SIMILARITY`, `AGENT_REVIEW_MIN_SIMILARITY`, and
`AGENT_TICKET_MIN_SIMILARITY` suppress weak vector matches.

Specialists return compact internal evidence summaries. Only the Supervisor emits
the user-facing answer; Supervisor routing output is not streamed as answer text.
Model lifecycle logs include `response_phase`, total duration, time to first token,
post-first-token generation duration, and input/output token counts when supplied
by the provider.

When `AGENT_RUN_PERSISTENCE=true`, each Supervisor run and its non-token public
events are written best-effort to `agent_runs` and `run_events`. Audit persistence
never stores prompts, private reasoning, raw answer tokens, or answer text, and a
database write failure does not prevent the Agent from answering.

The frontend displays public stages, applied skills, tool lifecycle and validation
events, streamed answer text, and resolvable database, review, and knowledge
citations. It deliberately does not display or log private model chain-of-thought.

Chat answers are rendered locally with Marked, sanitized with DOMPurify, and use
KaTeX for inline and display formulas. Rebuild and verify the browser bundle after
changing the renderer:

```powershell
npm --prefix frontend run build
npm --prefix frontend test
```

`chat_model.reasoning_effort` in `config/model.yml` is the default for non-Agent
chat usage. `chat_model.agent_reasoning_effort` assigns reasoning by Agent phase
while keeping the configured model unchanged. Routing can run without reasoning,
while synthesis, Finance, and Operations use a small reasoning budget. The UI
reports safe phase summaries in the Activity panel; raw private reasoning text is
never forwarded to the browser.

The supervisor performs one complete tool-planning wave followed by a tool-free
synthesis wave, and each specialist may be delegated at most once per request.
SQL execution is serialized and stops after the first successful query; failed
queries retain the configured correction-attempt budget.
