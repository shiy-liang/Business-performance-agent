# REST API 接口契约对齐检查报告

## 1. 检查范围与结论

检查对象：`Business Performance Agent` 当前 FastAPI 路由实现，以及《REST API 接口契约（原型版）》。

检查方式：静态审阅路由、请求校验、响应构造和 SQL 查询；本次未修改任何业务代码。

**结论：接口设计的静态逻辑与契约基本一致，但应用当前无法启动，所有接口均处于不可联调状态。**

根因是多个路由文件存在未闭合的 Python 字符串字面量，导入路由时会产生 `SyntaxError`。`app.py` 首先导入 `action_center.py`，因此其语法错误会阻止整个 FastAPI 应用加载。

## 2. 对齐结果总览

| 接口 | 对齐状态 | 代码中的实际实现 | 契约要求 | 差异说明 | 严重程度 |
|---|---|---|---|---|---|
| `GET /api/health` | 不对齐（运行阻塞） | `app.py` 的 `health()` 返回 `status`、`api`、`database`、`transaction_count`；数据库异常返回 `503`。 | 无请求参数；返回健康状态与交易计数；数据库不可用为 `503`。 | 静态字段和状态码逻辑对齐，但应用无法启动，接口不可访问。 | 阻塞联调 |
| `GET /api/dashboard/stores` | 不对齐（运行阻塞） | `backend/routers/finance.py` 的 `list_dashboard_stores()` 返回 `default_scope` 和 `stores[]`；门店含 `store_id`、`store_location`、`store_type`。 | 无 Query/Body；返回默认范围与门店筛选列表；数据库不可用为 `503`。 | 静态实现对齐，但受全局启动错误影响不可访问。 | 阻塞联调 |
| `GET /api/dashboard/financial-pulse` | 不对齐（运行阻塞） | `financial_pulse()` 校验 `month` 格式；月份越界返回 `422`；未知 `store_id` 返回 `404`；DB 异常返回 `503`；返回 `scope`、`period`、`metrics`、`trend`。 | 支持 `month`、`store_id`；格式/越界为 `422`；未知门店为 `404`；DB 不可用为 `503`；返回三项财务指标和 12 月趋势。 | 静态实现对齐；公司范围包含 Online 和未关联门店交易。无交易数据时额外返回 `404`，该业务场景未在契约中冻结。 | 阻塞联调 |
| `GET /api/dashboard/action-center` | 不对齐（运行阻塞） | `action_center()` 中只有库存 SQL 使用 `store_id`；工单查询不使用 `store_id`；库存最多返回 5 条，工单最多返回 3 条。 | 只有 inventory 支持门店筛选；`support_tickets` 恒为公司级；返回库存预警和长期高优工单。 | 静态口径对齐，但本文件有未闭合字符串，应用首次导入该模块即失败。 | 阻塞联调 |
| `GET /api/dashboard/product-performance` | 不对齐（运行阻塞） | `product_performance()` 返回四类 Top 5；销售和退货榜使用门店筛选；评分 SQL 不使用 `store_id`；退货率最低销量门槛为 5。 | 销售/退货榜可按门店过滤；评分榜必须是公司级、全生命周期数据；高退货率门槛为 5；利润为估算。 | 静态实现对齐：评分响应也明确标识 `all_time`、公司级和估算成本限制。 | 阻塞联调 |
| `GET /api/dashboard/marketing-performance` | 不对齐（运行阻塞） | `marketing_performance()` 仅声明 `month`，没有 `store_id`；按 ROI 降序，最多返回 5 条；返回公司范围与全生命周期指标说明。 | 不支持 `store_id`，始终公司级；月份仅用于活动周期重叠筛选；营销指标为活动全生命周期数据；归因为合成数据。 | 静态逻辑对齐，但本文件有未闭合字符串，模块无法解析。 | 阻塞联调 |
| `POST /api/chat` | 不对齐（运行阻塞） | `ChatRequest.message` 为 `str`，长度限制 `1–500`；设计上返回 `status: "placeholder"` 和 `answer`。 | 当前仅为 placeholder；不得视为真实 LLM、RAG、引用、会话或流式接口。 | 请求模型与设计意图对齐，但占位回答字符串未闭合，模块无法解析。 | 阻塞联调 |

## 3. 已确认的启动阻塞项

| 文件 | 位置 | 问题 | 影响 |
|---|---:|---|---|
| `backend/routers/action_center.py` | 219 行 | `support_tickets.scope.label` 的字符串未闭合。 | `app.py` 最先导入该模块，整个服务无法加载。 |
| `backend/routers/finance.py` | 363 行 | `estimated_gross_profit.label` 的字符串未闭合。 | 财务路由无法加载。 |
| `backend/routers/marketing.py` | 150 行 | `scope.label` 的字符串未闭合。 | 营销路由无法加载。 |
| `backend/routers/chat.py` | 23–24 行 | placeholder `answer` 的两段字符串均未闭合。 | Chat 路由无法加载。 |

## 4. 已核对且静态对齐的关键规则

### 参数校验与状态码

- `financial-pulse`、`product-performance`、`marketing-performance` 的 `month` 均使用 `YYYY-MM` 正则格式校验。
- 上述月度接口对超出交易数据可用范围的月份返回 `422`。
- `financial-pulse`、`action-center`、`product-performance` 对未知 `store_id` 返回 `404`。
- 所有数据库依赖接口捕获连接或查询异常后返回 `503`。
- `POST /api/chat` 使用 Pydantic 校验 `message` 为长度 `1–500` 的字符串；非法请求将触发 FastAPI/Pydantic 的 `422` 校验响应。

### 数据范围与业务口径

- 财务和商品销售范围未传 `store_id` 时为公司级，包含 Online 与未关联门店交易。
- Action Center 中库存受 `store_id` 影响；客服工单不接受门店过滤，固定为公司级。
- 商品评分查询不使用 `store_id` 和 `month`，为公司级全生命周期评分；响应中的 `basis.ratings` 也声明 `period: all_time` 与 `store_filter_applied: false`。
- 营销接口未声明 `store_id`，响应声明 `type: company` 与 `store_filter_available: false`。
- 营销活动入选条件为活动日期与选定自然月重叠；预算、转化、转化率、ROI 均为活动全生命周期指标。
- Chat 仅返回 placeholder，不存在 LLM 调用、pgvector 检索、来源引用、会话持久化或流式输出。

### 合成与估算数据限制

- 商品成本为合成成本，商品利润为估算值。
- 库存通过 `is_synthetic` 标识为合成快照。
- 经营费用、退款退货和营销归因均来自原型合成数据。
- 商品接口在 `basis.profit` 中标识了 `is_estimate`、`unit_cost_is_synthetic` 和 `returned_goods_cost_is_reversed: false`。
- 营销接口在 `basis.attribution` 中标识归因为合成数据且不证明因果关系。

## 5. 非阻塞待确认项

下列事项在契约中标为“待确认”“待决策”或“建议的 v1.1 扩展”，不应判定为当前代码不对齐。

| 项目 | 当前代码事实 | 契约状态 |
|---|---|---|
| `scope`、`period` 的精确 Schema | 当前代码返回对象，含范围类型、门店、日期范围、是否完整月份、数据截止日期等。 | 待冻结 |
| 统一错误 JSON | 手动异常采用 FastAPI 默认 `detail`；请求校验采用框架 `422` 结构。 | 待确认 |
| 币种、金额与比率精度 | 金额通常保留两位，库存比例保留四位；未返回 currency。 | 待确认 |
| 空数据规则 | 财务/商品/营销无交易数据时返回 `404`；行动中心可返回空列表和空日期。 | 待确认 |
| 未声明 Query 参数 | 例如营销接口收到 `store_id` 时，FastAPI 默认忽略该参数，仍返回公司级数据。 | 待确认 |
| 门店级利润的营销费用分摊 | 当前实现中门店范围不纳入营销预算；公司范围按活动日期分摊。 | 待确认 |
| 跨月退款、库存快照、榜单并列排序 | 代码有具体实现，但尚未冻结为公开契约。 | 待确认 |
| 鉴权、权限、多租户、限流、追踪 ID | 当前均未实现。 | 上线前待决策 |
| Chat RAG、引用、会话、流式输出 | 当前均未实现。 | v1.1 建议扩展 |

## 6. 建议的后续动作

1. 先修复四处未闭合字符串，恢复 FastAPI 应用可导入、可启动的状态。
2. 服务恢复后，按契约对全部 7 个接口执行真实 HTTP 冒烟测试，覆盖正常、`422`、`404`、`503` 和 Chat 校验场景。
3. 冻结公共对象、统一错误响应、金额/比例精度和空数据返回规则。
4. 将稳定后的契约转换为 OpenAPI 3.1，并将请求/响应样例纳入契约测试。

