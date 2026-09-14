# Runtime Observability 9.14开发说明

## 1. 本次开发内容

本次新增了 **Runtime Observability（运行状态与可观测性）MVP**，用于记录一次 Agent / 分析任务的运行状态，以及该次运行过程中产生的事件。

当前实现保持现有项目架构：

```text
FastAPI Router
    ↓
backend.database.connect()
    ↓
psycopg
    ↓
PostgreSQL / Supabase
```

本阶段未引入 Repository、Service、ORM、Celery、Redis、多 Worker、asyncio 并发、SSE、认证权限或真实 LLM/RAG。

---

## 2. 新增数据库表

### `agent_runs`

用于记录一次完整运行的生命周期。

主要字段：

- `run_id`: UUID，运行唯一标识
- `run_type`: TEXT，运行类型，当前不限制枚举
- `status`: `pending / running / completed / failed`
- `created_at`: 创建时间
- `started_at`: 开始时间，可为空
- `completed_at`: 完成/失败时间，可为空
- `error_message`: 错误信息，可为空

当前新建 run 时默认：

```text
status = pending
```

### `run_events`

用于记录某次 run 中发生的事件。

主要字段：

- `event_id`: BIGSERIAL，自增事件 ID
- `run_id`: 关联 `agent_runs.run_id`
- `event_type`: 事件类型
- `message`: 可读事件信息
- `created_at`: 事件创建时间
- `payload`: JSONB，额外结构化信息，默认 `{}`

`run_events.run_id` 使用外键关联 `agent_runs`，并启用了 `ON DELETE CASCADE`。

---

## 3. 新增 API

### `POST /api/runs`

创建一次新的运行记录。

请求示例：

```json
{
  "run_type": "dashboard_analysis"
}
```

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

---

### `GET /api/runs/{run_id}`

查询某次运行当前状态。

成功：

```text
200 OK
```

run 不存在：

```text
404 Not Found
```

非法 UUID：

```text
422 Validation Error
```

---

### `GET /api/runs/{run_id}/events`

查询某次运行的事件时间线。

事件按照：

```text
created_at ASC
event_id ASC
```

排序。

成功：

```text
200 OK
```

run 不存在：

```text
404 Not Found
```

---

## 4. 已完成测试

Swagger 本地冒烟测试已通过：

```text
POST /api/runs                 → 201 ✅
GET /api/runs/{run_id}        → 200 ✅
GET /api/runs/{run_id}/events → 200 ✅
```

已验证：

- `run_id` 能正确生成 UUID
- `run_type` 能正确保存
- 新 run 默认状态为 `pending`
- `created_at` 自动生成
- 新 run 会自动产生 `run_created` event
- 通过 `run_id` 可以重新查询对应 run
- 通过 `run_id` 可以查询对应事件
- 不存在的合法 UUID 返回 `404`
- 非 UUID 参数由 FastAPI / Swagger 校验

---

## 5. 当前涉及文件

```text
app.py
backend/routers/runs.py
database/schema.sql
```

其中：

- `app.py`：注册 `runs_router`
- `backend/routers/runs.py`：Runtime Observability API、Pydantic Model、SQL 和错误处理
- `database/schema.sql`：新增 `agent_runs`、`run_events` 及事件查询索引

---

## 6. 当前 MVP 边界

当前模块只完成：

```text
创建 run
查询 run
查询 run events
```

目前还没有实现：

- run 状态更新 API
- 自动从 `pending` 更新为 `running / completed / failed`
- 业务分析流程与 run tracking 的正式接入
- asyncio 并发
- SSE 实时事件推送
- Celery / Redis / 多 Worker
- 运行取消、重试、超时
- 用户 / 角色 / RLS 权限
- 真实 LLM / RAG 执行过程记录

这些内容可以在后续阶段逐步接入。

---

## 7. 后续模块接入建议

后续 Finance / Operations / Marketing / Agent 执行流程接入时，建议围绕同一个 `run_id` 更新状态并追加 event，例如：

```text
run_created
run_started
finance_analysis_started
finance_analysis_completed
operations_analysis_started
operations_analysis_completed
run_completed
```

如果执行失败，可将：

```text
agent_runs.status = failed
```

并记录：

```text
error_message
run_failed event
```

这样可以形成完整的运行时间线，方便 Swagger、日志、后续 SSE 或前端状态展示复用。
