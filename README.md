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

The root `.env` file must contain a valid Supabase pooler
`DATABASE_URL`. Keep that file local; it is excluded from Git.

```bash
cd Business-Performance-Agent
source .venv/bin/activate
uvicorn app:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). FastAPI documentation is
available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## 组员首次运行：连接现有数据库

拉取 `shiying-branch` 后，在项目根目录执行以下命令（macOS / Linux）：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

如果已有 `.env`，跳过复制命令，保留已有配置。

向项目负责人通过私密渠道获取数据库连接信息，将 `.env` 中的
`DATABASE_URL` 替换为完整连接地址。本项目当前使用 **Transaction pooler，
端口 6543**；以下仅为占位示例：

```dotenv
DATABASE_URL=postgresql://postgres.PROJECT_REF:PASSWORD@HOST:6543/postgres
```

主机、用户名和密码必须使用负责人提供的值。密码包含特殊字符时，需要进行
URL 百分号编码。不要将真实连接地址或 `.env` 提交到 GitHub。

启动服务：

```bash
uvicorn app:app --reload --port 8001
```

保持终端运行，在运行服务的这台电脑上打开：

- Dashboard：http://127.0.0.1:8001/
- 数据库连接检查：http://127.0.0.1:8001/api/health
- API 文档及测试：http://127.0.0.1:8001/docs

健康接口返回 `"database": "connected"` 表示连接成功。若端口被占用，可以改用
`--port 8002`，浏览器地址也同步改成 8002。修改 `.env` 后需停止并重新启动服务。

**组员共用现有 Supabase 数据库，不需要本地 CSV，也不要执行建表、数据导入或
数据更新脚本。** 本地原始、清洗后和模拟数据均未上传 GitHub；运行 Dashboard
直接读取云端数据库。`database/load_data.py` 会清空并重新加载共享表。

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
