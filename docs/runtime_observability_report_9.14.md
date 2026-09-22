# Runtime Observability 9.14开发说明

## 1. 本次开发内容

本项目已完成 **Runtime Observability（运行状态与可观测性）同步 MVP**。模块用于记录一次 Agent / 分析任务的总 run 生命周期，以及该 run 内各业务步骤产生的事件。

当前实现保持项目既有架构：

```text
FastAPI Router / Python Workflow
    ↓
backend.database.connect()
    ↓
psycopg
    ↓
PostgreSQL / Supabase
```

本阶段未引入 Repository、Service、ORM、Celery、Redis、多 Worker、asyncio 并发、SSE、认证权限或真实 LLM/RAG。

---

## 2. 已完成的数据结构

### `agent_runs`

用于记录一次完整 run 的生命周期。

主要字段：

- `run_id`: UUID，运行唯一标识
- `run_type`: TEXT，运行类型，当前不限制枚举
- `status`: `pending / running / completed / failed`
- `created_at`: 创建时间
- `started_at`: 开始时间，可为空
- `completed_at`: 完成或失败时间，可为空
- `error_message`: 错误信息，可为空

状态值由数据库 `CHECK` 约束限制。时间字段还具有以下约束：

```text
started_at >= created_at
completed_at >= COALESCE(started_at, created_at)
```

新建 run 时默认：

```text
status = pending
```

### `run_events`

用于记录某次 run 中发生的不可变事件。

主要字段：

- `event_id`: BIGSERIAL，自增事件 ID
- `run_id`: 关联 `agent_runs.run_id`
- `event_type`: 事件类型
- `message`: 可读事件信息
- `created_at`: 事件创建时间，数据库默认 `NOW()`
- `payload`: JSONB，额外结构化信息，默认 `{}`

`run_events.run_id` 使用外键关联 `agent_runs`，并启用了 `ON DELETE CASCADE`。事件时间线使用索引：

```text
(run_id, created_at, event_id)
```

---

## 3. 已完成 API

### `POST /api/runs`

创建一次新的运行记录。

请求示例：

```json
{
  "run_type": "dashboard_analysis"
}
```

`run_type` 长度为 1–100；额外请求字段会被拒绝。

行为：

1. Python 使用 `uuid4()` 生成 `run_id`
2. 创建一条 `agent_runs`
3. 默认状态为 `pending`
4. 同一数据库事务中自动创建一条 `run_created` event

自动事件：

```text
event_type = run_created
message = Run created
```

成功返回：

```text
201 Created
```

数据库错误映射为 `503 Database query failed`。

---

### `GET /api/runs/{run_id}`

查询某次运行当前状态。

| 情形 | 返回 |
| --- | --- |
| 成功 | `200 OK` |
| run 不存在 | `404 Not Found` |
| 非法 UUID | `422 Validation Error` |
| 数据库错误 | `503 Database query failed` |

---

### `GET /api/runs/{run_id}/events`

查询某次运行的事件时间线。事件按照：

```text
created_at ASC
event_id ASC
```

排序，并直接返回事件数组，不使用额外 wrapper。

| 情形 | 返回 |
| --- | --- |
| 成功 | `200 OK` |
| run 不存在 | `404 Not Found` |
| 非法 UUID | `422 Validation Error` |
| 数据库错误 | `503 Database query failed` |

---

## 4. 已完成 Runtime 生命周期能力

`backend/runtime.py` 已提供以下 Python 内部函数；当前没有对应的状态更新 REST API。

| 函数 | 已实现行为 |
| --- | --- |
| `mark_run_running(run_id)` | 仅允许 `pending → running`；设置 `started_at = NOW()`；同一事务写入 `run_started`。 |
| `mark_run_completed(run_id)` | 仅允许 `running → completed`；设置 `completed_at = NOW()`；同一事务写入 `run_completed`。 |
| `mark_run_failed(run_id, error_message)` | 允许 `pending / running → failed`；设置 `completed_at = NOW()` 与去除首尾空格后的错误信息；同一事务写入 `run_failed`。 |
| `record_run_event(run_id, event_type, message, payload)` | 不改变 run 状态；确认 run 存在后写入 JSONB payload 事件。 |

状态转换如下：

```text
pending ──→ running ──→ completed
   │             │
   └──→ failed ←─┘
```

状态函数使用 `SELECT ... FOR UPDATE` 进行状态检查。`record_run_event()` 只做 run 存在性检查，使用不加行锁的普通 `SELECT`。

公共异常：

- run 不存在：`RunNotFoundError("Run not found")`
- 状态不允许转换：`RunStateError(...)`
- 空或全空白 `error_message`、`event_type`、`message`：`ValueError`

`record_run_event()` 会对 `event_type` 与 `message` 去除首尾空格；`payload=None` 时写入 `{}`，并通过 psycopg `Jsonb` 适配器存入 JSONB。

---

## 5. 已完成 Finance 接入

Finance 已接入 Runtime Observability，但 Finance 只记录自己的步骤事件，不控制总 run 的 `status`。

### Prepare 阶段

`prepare_financial_pulse(month, store_id)` 负责：

- 查询 transaction coverage；
- `No transaction data` 的 404；
- company 或 store scope 构造；
- 未知 `store_id` 的 404；
- 默认月份计算、month 解析与范围 422 校验；
- 计算 `selected_month`、`period_end`、`is_complete` 和趋势起点；
- 返回供正式分析使用的 prepared context dict。

Prepare 阶段不会：

- 写入 `finance_analysis_started / completed / failed`；
- 执行 `SUMMARY_SQL`；
- 执行 `TREND_SQL`；
- 改变 `agent_runs.status`。

### Analysis 阶段

`analyze_prepared_financial_pulse(prepared, run_id)` 负责：

- 当 `run_id` 存在时写入 `finance_analysis_started`；
- 执行既有 `SUMMARY_SQL` 和 `TREND_SQL`；
- 计算 trend 与原有 Financial Pulse JSON 响应；
- 成功时写入 `finance_analysis_completed`；
- started 之后发生异常时写入 `finance_analysis_failed`，payload 包含错误、month、store_id。

`build_financial_pulse(month, store_id, run_id)` 仍是 HTTP Router 使用的兼容入口：

```text
prepare_financial_pulse
    ↓
analyze_prepared_financial_pulse
```

因此 `GET /api/dashboard/financial-pulse` 的 Swagger 与前端调用方式保持不变。未传 `run_id` 时，不会写入 Finance event。

由于 `prepare_financial_pulse()` 在 Analysis 前执行，Finance 前置 404 / 422 不会产生 `finance_analysis_failed` event。

### 本地故障注入测试记录

Finance 开发阶段曾临时加入故障注入，用于验证以下 failure path：

```text
finance_analysis_started
    ↓
finance_analysis_failed
    ↓
run_failed
```

该测试结束后，临时故障注入开关、条件判断和测试异常均已完整删除。当前正式源码中不存在
`FORCE_FINANCE_ANALYSIS_FAILURE`，也不存在可通过开关触发 Finance analysis failure 的测试代码。

---

## 6. 已完成最小 Finance Workflow

`backend/workflow.py` 提供 Python 内部函数：

```python
run_finance_workflow(
    run_id: UUID,
    month: str | None = None,
    store_id: str | None = None,
) -> dict[str, object]
```

当前同步流程：

```text
prepare_financial_pulse
    ↓ 校验通过
mark_run_running
    ↓
analyze_prepared_financial_pulse
    ↓ 成功
mark_run_completed
```

异常处理边界：

- Prepare 阶段的 `HTTPException` 直接上抛；run 尚未进入 `running`，因此保持 `pending`。
- `mark_run_running()` 抛出 `RunNotFoundError` 或 `RunStateError` 时直接上抛，不尝试 failed 转换。
- Analysis 已开始后出现异常时，workflow 以 `str(exc).strip() or exc.__class__.__name__` 生成错误信息，尝试调用 `mark_run_failed()`，随后重新抛出原异常。
- `mark_run_completed()` 的 `RunNotFoundError` 或 `RunStateError` 直接上抛，不重复调用 `mark_run_failed()`。
- 失败状态持久化本身发生数据库错误或状态变化时，不覆盖原始业务异常。

该 workflow 目前只作为 Python 内部能力，尚无 execute workflow 的 REST endpoint。

---

## 7. 事件链示例

### 正常 Finance workflow

```text
run_created
run_started
finance_analysis_started
finance_analysis_completed
run_completed
```

Finance 步骤事件 payload 示例：

```json
{
  "month": "2026-01",
  "store_id": null
}
```

### Analysis 失败

```text
run_created
run_started
finance_analysis_started
finance_analysis_failed
run_failed
```

`finance_analysis_failed` payload 示例：

```json
{
  "error": "Forced finance analysis failure for test",
  "month": "2026-01",
  "store_id": null
}
```

### Prepare 校验失败

```text
run_created
prepare_financial_pulse → 404 / 422
```

此时 workflow 尚未调用 `mark_run_running()`，run 保持 `pending`，也不会产生 Finance analysis failure event。

---

## 8. 已完成测试与检查

当前已完成的本地代码级验证包括：

- Runs API 的 Swagger 冒烟验证：创建 run、查询 run、查询事件；
- `run_finance_workflow()` 的成功路径控制流；
- Prepare 阶段 HTTP 失败路径：不会调用 `mark_run_running()` 或 `mark_run_failed()`；
- `mark_run_running()` 的 `RunNotFoundError` 路径：不会调用 `mark_run_failed()`；
- Analysis 异常路径：错误信息会去除首尾空格、尝试 `mark_run_failed()`，并重新抛出原异常；
- `mark_run_completed()` 的 `RunStateError` 路径：不会重复调用 `mark_run_failed()`；
- Finance Router 的 helper 委托、可选 `run_id` OpenAPI 参数与无 `run_id` 兼容路径；
- Prepare / Analysis 分离检查：prepare 不含 Finance SQL 或 Finance event；
- Finance 前置 404 / 422 位于 `finance_analysis_started` 之前，因此不产生 Finance failure event；
- Finance 临时故障注入测试曾验证：在 `finance_analysis_started` 后触发异常时，`SUMMARY_SQL` 不执行；该测试代码现已删除。

上述验证包括 Ruff、Python 编译、OpenAPI 结构检查及替身函数控制流检查；未在本轮文档更新中执行数据库 schema、导入或清库操作。

---

## 9. 当前涉及文件

```text
app.py
backend/routers/runs.py
backend/runtime.py
backend/routers/finance.py
backend/workflow.py
database/schema.sql
```

其中：

- `app.py`：注册 `runs_router`；
- `backend/routers/runs.py`：Run API、Pydantic response models、SQL 与错误处理；
- `backend/runtime.py`：生命周期状态转换与通用事件记录；
- `backend/routers/finance.py`：Financial Pulse prepare / analysis 拆分与 Finance 步骤事件；
- `backend/workflow.py`：最小同步 Finance workflow；
- `database/schema.sql`：`agent_runs`、`run_events`、外键、检查约束和事件查询索引。

---

## 10. 当前 MVP 边界与后续计划

### 当前已完成

```text
创建、查询 run 与事件
同步状态转换
通用 run event 写入
Finance prepare / analysis 步骤事件
最小同步 Finance workflow
```

### 后续计划（尚未实现）

- workflow execute 的 REST API；
- Operations、Product、Marketing 等业务模块接入同一 `run_id`；
- 用户主动取消、重试、超时和补偿状态；
- asyncio 并发 workflow；
- SSE 实时事件推送；
- Celery / Redis / 多 Worker；
- 用户、角色与 RLS 权限；
- 真实 LLM / RAG orchestration 与事件记录；
- 用自动化集成测试连接独立测试数据库，覆盖真实 PostgreSQL 状态与事件链。

当前文档描述的是同步 MVP，不应将其视为已具备异步调度、后台任务、流式推送或真实 Agent orchestration 能力。
