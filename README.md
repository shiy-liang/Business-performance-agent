# Business Performance Agent

Owners of small and medium-sized enterprises receive business information from
multiple sources, including sales reports, accounting systems, inventory records,
customer enquiries, and operational updates. Because information is scattered
across different systems and reports, business owners spend considerable time
reviewing data before understanding overall business performance and identifying
issues that require immediate attention.

This prototype combines those sources in a FastAPI application with a Chinese
management dashboard. It currently includes:

- company-wide or store-level financial pulse
- urgent inventory alerts and the oldest unresolved priority tickets
- best-selling, highly rated, high-return and low-rated product rankings
- campaign ROI and conversion rankings
- a chatbot placeholder ready for the pgvector retrieval pipeline

## Run the dashboard on this computer

The root `.env` file must contain a valid Supabase Session Pooler
`DATABASE_URL`. Keep that file local; it is excluded from Git.

```bash
cd Business-Performance-Agent
source .venv/bin/activate
uvicorn app:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). FastAPI documentation is
available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## Set up a fresh clone

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Replace the placeholder `DATABASE_URL` in `.env` with the Supabase Session
Pooler URI. Never commit `.env`.

For a new, empty Supabase project:

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
| `POST` | `/api/chat` | Stable placeholder contract for the future assistant |

The month-based endpoints accept `month=YYYY-MM`. Finance, inventory and product
sales also accept `store_id`; campaign and support-ticket source data do not have
a store identifier.

`database/schema.sql` creates the PostgreSQL schema and pgvector extension.
`database/build_embeddings.py` will populate `business_documents` after the
multilingual embedding model is installed and downloaded. Until that step is
run, the dashboard keeps the chatbot clearly marked as a placeholder.

Product costs, inventory, expenses, returns/refunds and campaign attribution are
synthetic prototype data. Financial metrics that depend on them are labelled as
estimates in the interface.
