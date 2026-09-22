# Business Performance Agent API 冒烟测试报告

## 1. 测试概览

- 测试目的：验证本地 FastAPI 服务、Supabase 数据库连接及现有 Dashboard API 的基础可用性。
- 测试环境：Windows 本地开发环境；FastAPI/Uvicorn；Supabase PostgreSQL。
- 测试方式：启动服务后，通过 Swagger UI（`/docs`）手工发起请求。
- 结论：本轮已测试接口均符合当前 API 契约预期，服务可作为下一阶段 MVP 开发的可用基线。

## 2. 启动与依赖检查

| 检查项 | 结果 | 备注 |
| --- | --- | --- |
| Python 语法检查 | 通过 | 已执行 `python -m compileall app.py backend`，未发现语法错误。 |
| FastAPI 启动 | 通过 | Uvicorn 正常启动，服务可访问。 |
| 数据库连接 | 通过 | 配置本地 `.env` 后，Dashboard 显示 Supabase 已连接。 |
| 前端页面加载 | 通过 | 财务脉搏、行动中心等 Dashboard 页面成功显示数据。 |

> 安全说明：`.env` 中含数据库连接凭证，仅用于本地运行；未提交到 Git 仓库。

## 3. 接口测试结果

| 接口 | 测试场景 | 预期 | 实际结果 | 结论 |
| --- | --- | --- | --- | --- |
| `GET /api/health` | 正常请求 | `200`；API 与数据库连通 | 正常返回，数据库为 connected | 通过 |
| `GET /api/dashboard/stores` | 正常请求 | `200`；返回 `default_scope`、`stores` | 返回公司范围及门店列表 | 通过 |
| `GET /api/dashboard/financial-pulse` | 不传参数 | `200`；默认完整交易月、公司范围指标和趋势 | 正常返回 `scope`、`period`、`metrics`、`trend` | 通过 |
| `GET /api/dashboard/action-center` | 正常请求 | `200`；返回库存预警和工单预警 | 正常返回库存及工单数据 | 通过 |
| `GET /api/dashboard/product-performance` | 正常请求 | `200`；返回商品表现排行榜 | 正常返回 | 通过 |
| `GET /api/dashboard/marketing-performance` | 正常请求 | `200`；返回公司级营销表现 | 正常返回 | 通过 |
| `POST /api/chat` | `message` 为非空字符串 | `200`；返回占位回答 | 返回 `status: placeholder` 与 `answer` | 通过 |

## 4. 最小异常场景

| 场景 | 示例请求 | 预期状态码 | 实际结果 | 结论 |
| --- | --- | --- | --- |
| 月份格式错误 | `month=2025-1` | `422` | `422` | 通过 |
| 门店不存在 | `store_id=store_does_not_exist` | `404` | `404` | 通过 |
| Chat 空消息 | `{ "message": "" }` | `422` | `422` | 通过 |

说明：若同一个请求同时包含格式非法的 `month` 和不存在的 `store_id`，当前实现优先返回 `422`。这是因为参数格式校验发生在查询门店是否存在之前；当前接口契约未定义多个错误的聚合返回规则。

## 5. 已知原型限制

- Chat 接口当前仅为占位实现，不包含真实 LLM、RAG、来源引用、会话管理或流式输出。
- 利润、库存预警、退货退款、费用和营销归因相关数据含合成或估算数据，不能视为正式财务核算或因果归因结果。
- 当前没有认证、用户、角色和权限体系。

## 6. 后续建议

1. 执行 Ruff 静态检查与格式检查。
2. 将本轮测试结果与必要代码改动提交至个人分支，确认 `.env` 未被提交。
3. 在现有可用 Dashboard 基线上，进入 MVP 的运行状态、事件日志与可观测性能力开发。
