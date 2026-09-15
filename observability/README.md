# 日志模块使用说明

项目统一使用 `observability.logging` 中的全局 `logger` 实例记录系统、Agent、模型和 Tool 的运行状态。业务模块不要自行调用 `logging.getLogger()` 或添加 Handler，避免重复输出、格式不一致和日志文件分散。

日志采用“代码配置 + 环境变量覆盖”的方式：

- `config/logging.py` 保存配置结构、默认值、类型转换、路径解析和合法性校验。
- `.env` 保存不同运行环境需要覆盖的值；密钥和连接信息也只能放在 `.env`，不能写进配置源码。
- `observability/logging.py` 只负责日志行为，通过统一配置对象读取设置，不直接读取环境变量。

配置在进程启动、模块首次导入时加载，修改 `.env` 后需要重启应用。

## 1. 快速开始

```python
from observability.logging import logger

logger.info(
    "inventory.reorder.triggered",
    message="库存达到补货条件",
    component="inventory",
    sku="SKU-001",
    stock_quantity=5,
    reorder_point=10,
)
```

第一个参数是稳定、可搜索的事件名，建议采用：

```text
模块.对象.状态
```

例如：

```text
inventory.reorder.triggered
agent.route.completed
database.query.failed
```

变量值应作为命名字段传入，不要拼接到事件名或 `message` 中。

## 2. 日志级别

| 方法 | 使用场景 |
| --- | --- |
| `logger.debug()` | 开发调试、中间状态和已脱敏参数摘要 |
| `logger.info()` | 正常流程、条件触发、执行开始或完成 |
| `logger.warning()` | 可恢复问题、数据缺失、数据过期或低置信度 |
| `logger.error()` | 已知错误，但当前没有捕获到异常对象 |
| `logger.exception()` | 捕获 Python 异常，并记录异常类型、错误信息和 traceback |
| `logger.model_event()` | 模型调用状态、模型名称、耗时和 Token 数量 |
| `logger.tool_event()` | Tool 调用状态、工具名称、耗时和结果摘要 |

默认情况下，控制台显示 `INFO` 及以上级别，日志文件保存 `DEBUG` 及以上级别。

## 3. 记录条件触发和执行结果

建议分别记录条件触发、执行完成和执行失败：

```python
from time import perf_counter

from observability.logging import logger


if stock_quantity <= reorder_point:
    started_at = perf_counter()

    logger.info(
        "inventory.reorder.triggered",
        message="库存达到补货条件，开始生成补货建议",
        component="inventory",
        condition="stock_quantity <= reorder_point",
        stock_quantity=stock_quantity,
        reorder_point=reorder_point,
        action="create_reorder_recommendation",
        sku=sku,
    )

    try:
        recommendation = create_reorder_recommendation()

        logger.info(
            "inventory.reorder.completed",
            message="补货建议生成完成",
            component="inventory",
            sku=sku,
            recommendation_id=recommendation.id,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
    except Exception as exc:
        logger.exception(
            "inventory.reorder.failed",
            exc,
            message="补货建议生成失败",
            component="inventory",
            sku=sku,
            action="create_reorder_recommendation",
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        raise
```

记录日志后是否继续抛出异常，应由业务逻辑决定。不要仅记录异常后静默忽略失败。

## 4. 模型日志

使用 `model_event()` 记录模型生命周期，不记录完整 Prompt、模型回复或私有思维链。

```python
logger.model_event(
    status="started",
    model="configured-model-id",
    agent_name="finance",
    prompt_version="finance-v1",
)

# 调用模型

logger.model_event(
    status="completed",
    model="configured-model-id",
    agent_name="finance",
    prompt_version="finance-v1",
    duration_ms=856,
    input_tokens=1200,
    output_tokens=340,
    estimated_cost=0.02,
)
```

模型调用失败时，可以将 `status` 设为 `failed`，并另外通过 `logger.exception()` 记录异常。

## 5. Tool 日志

使用 `tool_event()` 记录工具的开始、完成或失败状态。只记录参数摘要、参数哈希、查询 ID、行数、新鲜度和耗时，不记录完整查询结果或敏感原始数据。

```python
logger.tool_event(
    status="started",
    tool_name="get_revenue_summary",
    agent_name="finance",
    query_id=query_id,
)

# 调用 Tool

logger.tool_event(
    status="completed",
    tool_name="get_revenue_summary",
    agent_name="finance",
    query_id=query_id,
    row_count=len(result),
    duration_ms=128,
    data_freshness="2026-09-12T00:00:00Z",
)
```

## 6. 绑定运行上下文

`bind_context()` 可以让一段流程中的每条日志自动带上相同标识。必须在 `finally` 中调用 `reset_context()`，防止上下文泄漏到后续任务。

```python
context_token = logger.bind_context(
    run_id="run-123",
    conversation_id="conversation-456",
    agent_name="finance",
)

try:
    logger.info("agent.started")
    logger.info("agent.completed")
finally:
    logger.reset_context(context_token)
```

FastAPI 日志中间件已经自动为每个 HTTP 请求绑定 `request_id`、请求方法和路径。业务路由通常不需要再次绑定 `request_id`。

## 7. 保存格式与位置

默认日志文件为：

```text
logs/business-performance.log
```

日志使用 UTF-8 编码和 JSON Lines 格式。每一行是一个独立 JSON 对象，例如：

```json
{"timestamp":"2026-09-12T08:02:48+00:00","level":"info","service":"business-performance-agent","environment":"development","event":"inventory.reorder.triggered","message":"库存达到补货条件","component":"inventory","sku":"SKU-001","stock_quantity":5,"reorder_point":10}
```

公共字段包括：

- `timestamp`：带 `+08:00` 偏移的新加坡时间。
- `level`：日志级别。
- `service`：服务名称。
- `environment`：运行环境。
- `event`：稳定的事件名称。
- `message`：供开发者阅读的简短说明。
- 其他字段：调用者传入的结构化业务字段及已绑定上下文。

## 8. 日志轮转与清理

正在写入的文件始终是：

```text
business-performance.log
```

代码使用 Python 标准库的 `TimedRotatingFileHandler`。默认配置为每天新加坡时间零点轮转一次，历史文件也按照新加坡业务日期命名。轮转不是独立后台任务；程序在轮转时间之后写入下一条日志时，才会执行文件改名和新文件创建。

历史文件名称类似：

```text
business-performance.log.20260912
business-performance.log.20260913
```

默认最多保留 14 个历史备份。第 15 个备份产生时，`TimedRotatingFileHandler` 会自动删除最旧的备份文件。它按照备份文件数量清理，而不是通过后台任务持续检查文件是否恰好超过 14 天。

默认时区为 `Asia/Singapore`。日志时间戳和每日轮转边界都会使用这个配置，不依赖服务器本地时区。新加坡全年使用 UTC+8，不实行夏令时。

## 9. 环境变量

可以在 `.env` 中配置：

```dotenv
APP_ENV=development
LOG_CONSOLE_LEVEL=INFO
LOG_FILE_LEVEL=DEBUG
LOG_BACKUP_COUNT=14
LOG_TIMEZONE=Asia/Singapore
# LOG_DIRECTORY=logs
```

| 环境变量 | 默认值 | 作用 |
| --- | --- | --- |
| `APP_ENV` | `development` | 写入每条日志的运行环境 |
| `LOG_CONSOLE_LEVEL` | `INFO` | 控制台最低日志级别 |
| `LOG_FILE_LEVEL` | `DEBUG` | 文件最低日志级别 |
| `LOG_BACKUP_COUNT` | `14` | 最多保留的历史日志文件数量 |
| `LOG_TIMEZONE` | `Asia/Singapore` | 日志时间戳、每日轮转边界和历史文件日期使用的 IANA 时区 |
| `LOG_DIRECTORY` | 项目根目录下的 `logs` | 自定义日志目录 |

`LOG_DIRECTORY` 如果是相对路径，会统一相对于项目根目录解析。环境变量由 `config/logging.py` 转换并校验；例如时区名称无效，或备份数量小于 1 时，应用会在启动阶段明确报错。Windows 环境通过 `tzdata` 依赖提供 IANA 时区数据库。

## 10. 安全规则

日志类会自动脱敏以下字段或内容：

- password、secret、API key 和各类 access/refresh token。
- Authorization 和 Cookie。
- 数据库连接字符串中的密码。

自动脱敏不能替代调用方控制。禁止主动记录：

- `.env` 内容或完整数据库连接地址。
- 完整用户文件、客户隐私数据或 Tool 原始结果。
- 完整 Prompt、模型私有思维链或未经处理的模型上下文。

推荐记录版本、数量、哈希、ID、耗时、状态和脱敏摘要，以便监控与问题定位。
