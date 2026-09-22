# Business Performance Workflow 最终验收报告（9.21）

## 1. Scope

本阶段已完成并验收以下同步 MVP 能力：

- Finance、Action Center、Products、Marketing 的 Runtime Observability 接入；
- 统一的 Business Performance Workflow；
- Run 创建、查询、事件查询与执行 API；
- Dashboard 前端从四个独立业务请求切换为 Workflow 执行结果渲染；
- 旧 Dashboard API 的兼容性回归。

未引入 Service / Repository / ORM、asyncio workflow、Celery、Redis、多 Worker、SSE、认证授权或真实 LLM/RAG orchestration。

## 2. Runtime lifecycle

`agent_runs.status` 当前状态为：

```text
pending
running
completed
failed
```

正常执行链：

```text
run_created
→ run_started
→ module analysis events
→ run_completed
```

Analysis 失败链：

```text
run_created
→ run_started
→ module_analysis_failed
→ run_failed
```

Prepare / validation 阶段失败时，发生在 `mark_run_running()` 之前：

```text
run_created
→ prepare / validation raises error
→ run remains pending

Persisted events: run_created only
```

`pending → running → completed / failed` 的运行状态转换由 `backend/workflow.py`
统一控制；`backend/routers/runs.py` 负责创建初始 `pending` run 并写入
`run_created`。业务 Router 不直接调用 `mark_run_running()`、
`mark_run_completed()` 或 `mark_run_failed()`。

## 3. Module events

| 模块 | Started | Completed | Failed |
| --- | --- | --- | --- |
| Finance | `finance_analysis_started` | `finance_analysis_completed` | `finance_analysis_failed` |
| Action Center | `action_center_analysis_started` | `action_center_analysis_completed` | `action_center_analysis_failed` |
| Products | `products_analysis_started` | `products_analysis_completed` | `products_analysis_failed` |
| Marketing | `marketing_analysis_started` | `marketing_analysis_completed` | `marketing_analysis_failed` |

各模块只通过 `record_run_event()` 写入自己的 module event；不直接修改 `agent_runs.status`。

## 4. Unified Workflow

`backend/workflow.py` 当前提供：

```python
run_finance_workflow(run_id, month=None, store_id=None)
run_business_performance_workflow(run_id, month=None, store_id=None)
```

`run_finance_workflow()` 是前期 Finance Runtime Observability 接入阶段形成并保留的单模块 Workflow，用于早期生命周期 / 状态机验证和独立 Finance 执行。当前 Dashboard 正式主流程使用 `run_business_performance_workflow()`。Finance standalone workflow 目前作为后端独立能力保留，后续可根据产品需求决定继续保留或清理。

`run_business_performance_workflow()` 的执行顺序如下：

```text
Prepare: Finance → Action Center → Products → Marketing
    ↓ all prepare succeeds
mark_run_running
    ↓
Analysis: Finance → Action Center → Products → Marketing
    ↓
mark_run_completed
```

Workflow 使用 fail-fast 语义：任一 analysis 抛出异常时，当前模块先记录自己的 `*_analysis_failed` event，异常向上抛出；Workflow 将总 run 标记为 `failed`，后续模块不会执行。

## 5. Run APIs

当前正式 API：

```text
POST /api/runs
POST /api/runs/{run_id}/execute
GET /api/runs/{run_id}
GET /api/runs/{run_id}/events
```

`POST /api/runs` 仅创建 `pending` run，并在同一事务写入 `run_created`；它不会自动执行 Workflow。

`POST /api/runs/{run_id}/execute` 根据已持久化的 `run_type` 分发：

```text
finance
→ run_finance_workflow

business_performance
→ run_business_performance_workflow
```

Execute 请求体支持：

```json
{
  "month": "2025-02",
  "store_id": "S001"
}
```

`month` 和 `store_id` 均可为 `null`；额外字段会被拒绝。当前已核验的重要 HTTP 行为：

| 情形 | HTTP 行为 |
| --- | --- |
| 不存在的 run UUID | `404 Run not found` |
| 不支持的 `run_type` | `422` |
| 已非 `pending` 的 run 再次 execute | `409` |
| 不合法的 `month` 格式 | `422`，Workflow 不启动 |
| Prepare 阶段不存在门店 | `404`，run 保持 `pending` |
| Workflow 异常 / 数据库失败 | 保持各模块既有 HTTP 映射语义；已验证的 `RuntimeError` analysis failure 与数据库错误返回 `503`，其他未映射异常继续向上抛出 |

## 6. Business Performance success sequence

一次成功的 Business Performance run 的事件顺序为：

```text
run_created
run_started
finance_analysis_started
finance_analysis_completed
action_center_analysis_started
action_center_analysis_completed
products_analysis_started
products_analysis_completed
marketing_analysis_started
marketing_analysis_completed
run_completed
```

每个成功 run 只有一个 `run_started` 和一个 `run_completed`，四个模块事件共享同一个 `run_id`。

## 7. Fail-fast verified sequence

已通过 Products analysis 临时故障注入验证 fail-fast 路径：

```text
run_created
run_started
finance_analysis_started
finance_analysis_completed
action_center_analysis_started
action_center_analysis_completed
products_analysis_started
products_analysis_failed
run_failed
```

验证结果：

- Marketing 没有执行，也没有 Marketing module event；
- 没有 `products_analysis_completed`；
- 没有 `run_completed`；
- 总 run 最终为 `failed`，错误信息非空；
- 原始异常继续向调用方 / HTTP execute endpoint 传播。

Finance、Marketing、Products 与 Action Center 的故障注入均仅用于测试，测试后相关临时代码已完整删除。

## 8. Scope semantics

| 运行范围 | Finance | Products | Action Center inventory | Action Center support tickets | Marketing |
| --- | --- | --- | --- | --- | --- |
| Company | company | company | company | company | company |
| Store | 目标门店 | 目标门店 | 目标门店 | company | company |

Support Tickets 和 Marketing 当前为 company-level 是既有业务口径，不是门店筛选失效。

## 9. Frontend integration

Dashboard 主加载流程已从四个独立业务 API 请求切换为：

```text
GET /api/dashboard/stores
→ POST /api/runs
→ POST /api/runs/{run_id}/execute
→ render Finance / Action Center / Products / Marketing workflow result
```

现有四个 render 函数继续复用 Workflow 返回的：

```text
result.finance
result.action_center
result.products
result.marketing
```

`month` 为空时，前端传递 `null`，并在 Workflow 成功后将 Finance 返回的 `period.month` 回填到月份控件；前端不自行推导默认月份。

## 10. Stale-data handling

Workflow 整体失败按整轮 Dashboard refresh failure 处理。当前前端会清理可能被误认为本轮结果的旧状态：

- Finance：`financePeriod`、`salesDataThrough`、`scopeCaption`；
- Action Center：`ticketCount`；
- Products：缓存的 `state.productData`；
- Marketing：`campaignCount`。

因此 Products failure 后切换商品 Tab 不会重新显示上一轮的榜单数据。已有 `AbortController` 和 stale-response 判断继续保护较旧响应不覆盖当前页面。

## 11. Backward compatibility

以下旧业务 API 保留并已通过无 `run_id` 回归：

```text
GET /api/dashboard/financial-pulse
GET /api/dashboard/action-center
GET /api/dashboard/product-performance
GET /api/dashboard/marketing-performance
```

无 `run_id` 调用不会创建 module event，原有响应结构和业务口径保持可用。

## 12. Final regression

最终回归已验证：

- Python compile 与模块 import 通过；
- FastAPI 正常启动，`GET /api/health` 返回 `200`，数据库为 `connected`；
- 四个旧 Dashboard API 返回成功，且不写入 run event；
- Run API 创建、查询 run、查询 events 通过；
- Finance execute 和 Business Performance execute 成功完成并产生预期完整事件链；
- Company 与 S001 store scope 均已核验；
- 前端 Workflow 已通过最小 DOM + 真实 FastAPI + PostgreSQL 的逻辑联调；
- 未发现当前正式源码中的临时故障注入代码。

未进行截图级的真实浏览器视觉验收；上述前端验收是逻辑/DOM 与真实后端、数据库联调，不应描述为视觉验收。

## 13. Known limitations

1. Workflow 当前为同步执行。
2. 当前没有 Celery、Redis、async worker 或 multi-worker 调度。
3. 浏览器 `AbortController` 不能取消已在服务器开始执行的同步 Workflow。
4. 如果客户端在 create run 成功后、execute 发出前放弃该请求，可能留下只有 `run_created` event 的 `pending` run。
5. 当前未实现 cancellation、expiration 或自动 pending-run cleanup。
6. 当前 run 状态仅为 `pending / running / completed / failed`。
7. 当前没有 SSE 实时事件推送，也没有真实 LLM/RAG orchestration。
