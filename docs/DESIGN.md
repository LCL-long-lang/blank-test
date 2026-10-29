# 智能数据分析系统 · 系统模块规划

## 1. 项目概述

用户在网页上用自然语言提问（如“近 6 个月各品类销售额趋势”），系统完成以下流程：

1. 后端调用 Qwen3，把问题转成 SQL；
2. 在 SQLite3 业务库上只读执行；
3. 把结果以表格、ECharts 图表和文字解读三种形式实时推送到前端。

系统支持多会话和上下文追问（如“那只看华东区呢？”）。

### 1.1 技术栈总表

| 层 | 选型 | 用途 |
|---|---|---|
| 大模型 | 阿里云百炼 Qwen3（`qwen3.8-max` / `qwen3.8-flash`） | SQL 生成、问题改写、意图识别、图表推荐、结果解读 |
| LLM 框架 | LangChain 1.x（`langchain-core`、`langchain-openai`） | Prompt 模板、LCEL 链、结构化输出、流式输出、消息历史 |
| Web 框架 | FastAPI + Uvicorn + `sse-starlette` | REST 接口 + SSE 流式推送 |
| 数据库 | SQLite3（Python 标准库 `sqlite3`） | `business.db` 业务数据（只读），`app.db` 会话与记忆 |
| SQL 安全 | sqlglot | AST 级 SQL 校验、强制 LIMIT |
| 配置 | pydantic-settings + `.env` | API Key、模型名、路径 |
| 前端框架 | React 19 + TypeScript + Vite 8 | SPA |
| UI | Ant Design 6 | 三栏布局、列表、表格、气泡 |
| 图表 | ECharts 6 + `echarts-for-react` | 右侧可视化面板 |
| 状态 | Zustand | 会话、消息、图表三个 store |
| 流式 | `@microsoft/fetch-event-source` | POST 方式接收 SSE |

> 依赖版本在实施时用 `requirements.txt` / `package-lock.json` 锁定精确版本。

### 1.2 设计原则

- **LLM 只负责“想”，代码负责“做”。** 模型只输出 SQL 和图表意图（ChartSpec）；校验、执行、组装 ECharts option 都由确定性代码完成。
- **明细数据不回传给模型。** 解读环节只给模型结果摘要（行数、列统计、前 20 行），这样能避免编造数据，也能控制 Token。
- **显式管道，不用自由 ReAct Agent。** NL2SQL 的步骤是固定的，用 LCEL 串成显式流程更可控、更好调试，每一步都能单独推送给前端。

## 2. 总体分层架构

```
┌──────────────────────────── 前端 React（三栏） ─────────────────────────────┐
│  左：聊天管理            │  中：问答区域               │  右：可视化图表          │
│  SessionSidebar         │  ChatPanel                 │  ChartPanel            │
│  新建/列表/重命名/删除    │  消息流·步骤·SQL·流式文本    │  ECharts·数据表·SQL     │
│        sessionStore     │        chatStore           │        chartStore      │
└───────────┬─────────────┴──────────┬─────────────────┴──────────▲────────────┘
            │ REST /api/sessions     │ POST /api/chat/stream      │ SSE: chart/data
            ▼                        ▼                            │
┌──────────────────────────── 后端 FastAPI ─────────────────────────────────────┐
│ api 层：sessions 路由 │ chat 路由(SSE) │ charts 路由 │ schema 路由              │
├──────────────────────────────────────────────────────────────────────────────┤
│ 服务层：SessionService │ ChatService(编排一次问答) │ MemoryService               │
├──────────────────────────────────────────────────────────────────────────────┤
│ agent 层（LangChain LCEL 管道）                                                │
│ 改写 → 意图 → Schema上下文 → SQL生成 → 校验 → 执行 → (纠错≤3) → 图表推荐 → 解读  │
├──────────────┬──────────────┬───────────────┬────────────────┬───────────────┤
│ llm          │ db           │ sql_guard     │ chart          │ memory        │
│ Qwen3 客户端  │ 只读执行      │ sqlglot 校验   │ ChartSpec      │ 滑动窗口+摘要   │
│ (百炼兼容接口) │ Schema 抽取   │ 白名单/LIMIT   │ → ECharts      │ 消息历史        │
└──────┬───────┴──────┬───────┴───────────────┴────────────────┴───────┬───────┘
       ▼              ▼                                                ▼
  阿里云百炼 API    business.db（只读，电商示例数据）            app.db（会话/消息/图表）
```

**为什么拆成两个 SQLite 文件：** 业务库以只读模式打开，模型生成的 SQL 物理上就碰不到会话数据，也改不了任何数据。`app.db` 由后端自己读写。

## 3. 后端模块划分

### 3.1 模块依赖关系（单向，无循环）

```
api ──► services(session/chat/memory) ──► agent ──► llm / db / sql_guard / chart
                    │                                     │
                    └──────────► repository(app.db) ◄─────┘(只有 memory/chat 写入)
config / common  ◄── 所有模块都可以依赖
```

### 3.2 `config` 配置模块

| 项 | 说明 |
|---|---|
| 文件 | `app/config.py`、`.env`、`.env.example` |
| 职责 | 用 pydantic-settings 读取配置，提供全局 `settings` 单例 |
| 配置项 | `DASHSCOPE_API_KEY`、`DASHSCOPE_BASE_URL`、`MODEL_SQL`（qwen3.8-max）、`MODEL_FAST`（qwen3.8-flash）、`BUSINESS_DB_PATH`、`APP_DB_PATH`、`SQL_MAX_ROWS`（1000）、`SQL_TIMEOUT_S`（10）、`MEMORY_WINDOW`（6 轮）、`CORS_ORIGINS` |
| 安全 | `.env` 加入 `.gitignore`，只提交 `.env.example` |

### 3.3 `llm` 大模型接入模块

| 项 | 说明 |
|---|---|
| 文件 | `app/llm/client.py` |
| 接入方式 | `langchain_openai.ChatOpenAI` + 百炼 OpenAI 兼容地址 `https://dashscope.aliyuncs.com/compatible-mode/v1`，`api_key=DASHSCOPE_API_KEY`。备选是 `langchain_community` 里的 `ChatTongyi` |
| 对外函数 | `get_sql_llm()`：强模型，`temperature=0`；`get_fast_llm()`：快模型，用于改写、意图识别、标题、图表推荐；`get_chat_llm(streaming=True)`：结果解读，开启流式 |
| 思考模式 | Qwen3 混合思考模型通过 `extra_body={"enable_thinking": False}` 关闭思考，降低延迟。只在复杂 SQL 场景打开（打开后必须使用流式调用） |
| 结构化输出 | `llm.with_structured_output(PydanticModel)`，用于意图识别和 ChartSpec |
| 容错 | `max_retries=2`、`timeout=60`；调用失败时统一抛 `LLMError`，由 api 层转成 SSE `error` 事件 |

```python
# app/llm/client.py（示意）
from functools import lru_cache
from langchain_openai import ChatOpenAI
from app.config import settings

def _build(model: str, temperature: float = 0, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        temperature=temperature,
        streaming=streaming,
        max_retries=2,
        timeout=60,
        extra_body={"enable_thinking": False},
    )

@lru_cache
def get_sql_llm() -> ChatOpenAI:
    return _build(settings.model_sql)

@lru_cache
def get_fast_llm() -> ChatOpenAI:
    return _build(settings.model_fast)

@lru_cache
def get_chat_llm() -> ChatOpenAI:
    return _build(settings.model_fast, temperature=0.3, streaming=True)
```

> 已在 Phase 1 验证：兼容地址可用，`qwen3.8-max` / `qwen3.8-flash` 可调用，`enable_thinking=False` 生效。该账号没有 `qwen3-max`（返回 404）。

### 3.4 `db` 业务数据访问模块

| 项 | 说明 |
|---|---|
| 文件 | `app/db/business.py`（只读执行）、`app/db/schema.py`（Schema 抽取）、`semantic/dictionary.yaml`（数据字典） |
| 只读执行 | `run_readonly_query(sql) -> QueryResult(columns, rows, elapsed_ms)`：每次新建连接 `sqlite3.connect("file:business.db?mode=ro", uri=True)`，设置 `PRAGMA query_only=ON`，用 `set_progress_handler` 超时中断；在 FastAPI 中用 `run_in_threadpool` 调用，不阻塞事件循环 |
| Schema 抽取 | `load_schema() -> list[TableInfo]`：从 `sqlite_master` 取表，用 `PRAGMA table_info` 取字段，用 `PRAGMA foreign_key_list` 取外键；低基数文本列抽取 `DISTINCT` 样例值；启动时加载并缓存在内存 |
| 数据字典 | SQLite 不支持表/字段注释，所以用 YAML 维护表中文名、字段含义、单位、枚举值、指标口径（如“销售额 = SUM(order_items.quantity * order_items.unit_price)，且只计 status='completed' 的订单”） |
| 上下文渲染 | `render_schema_context(tables) -> str`：合并 Schema 和数据字典，生成精简 DDL 风格文本，供 SQL 生成 Prompt 使用 |

```python
# app/db/business.py 核心（示意）
import sqlite3, time
from app.config import settings

def run_readonly_query(sql: str) -> tuple[list[str], list[tuple]]:
    conn = sqlite3.connect(f"file:{settings.business_db_path}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only = ON")
        deadline = time.monotonic() + settings.sql_timeout_s
        # 返回非 0 即中断，抛 sqlite3.OperationalError("interrupted")
        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
        cur = conn.execute(sql)
        return [d[0] for d in cur.description], cur.fetchall()
    finally:
        conn.close()
```

### 3.5 `sql_guard` SQL 安全模块

| 项 | 说明 |
|---|---|
| 文件 | `app/sql_guard.py` |
| 对外函数 | `validate_and_rewrite(sql, allowed_tables) -> str`，校验不通过抛 `SQLGuardError(msg)` |
| 规则 | ① 去掉 Markdown 代码块包裹；② `sqlglot.parse(sql, read="sqlite")` 只允许 1 条语句；③ 根节点必须是查询（SELECT / UNION / WITH）；④ 不能出现 Insert/Update/Delete/Drop/Create/Alter/Pragma/Attach 等节点；⑤ 用到的表（排除 CTE 名）必须在白名单里；⑥ 没有 LIMIT 时补上 `LIMIT SQL_MAX_ROWS` |
| 纠错联动 | 错误信息原样回传给 agent，作为下一次 SQL 生成的“上次错误” |

### 3.6 `agent` NL2SQL 管道模块（核心）

| 项 | 说明 |
|---|---|
| 文件 | `app/agent/pipeline.py`（编排）、`app/agent/prompts.py`（全部 Prompt 模板）、`app/agent/schemas.py`（Pydantic 输出结构） |
| 输入 | `AgentInput(question, history: list[Turn], summary: str)` |
| 输出 | 异步生成器 `run(input) -> AsyncIterator[AgentEvent]`，每完成一步就 `yield` 一个事件，由 ChatService 转成 SSE |

管道步骤：

| # | 步骤 | 实现 | 模型 | 产出事件 |
|---|---|---|---|---|
| 1 | 问题改写 | `rewrite_prompt \| fast_llm \| StrOutputParser()`；结合历史把追问补全成独立问题。没有历史时跳过 | fast | `step` |
| 2 | 意图识别 | `with_structured_output(Intent)`，取值为 `query`（查数）/ `chitchat`（闲聊或系统说明）/ `clarify`（信息不足需要反问） | fast | `step` |
| 3 | Schema 上下文 | 表少（<15 张）时全量注入；表多时先用 fast_llm 选表，再按外键补全关联表 | fast / 无 | `step` |
| 4 | SQL 生成 | `sql_prompt \| sql_llm \| SQLOutputParser`；Prompt 包含：SQLite 方言规则、Schema、数据字典、Few-shot 样例、当前日期、改写后的问题、（纠错时）上次的 SQL 和错误 | sql | `sql` |
| 5 | 校验 | `sql_guard.validate_and_rewrite` | — | — |
| 6 | 执行 | `run_readonly_query`；0 行视为“软错误”，重试 1 次 | — | `data` |
| 7 | 自我纠错 | 第 5、6 步失败时回到第 4 步，最多 3 次；仍失败则输出 `error` | sql | `sql`（attempt+1） |
| 8 | 图表推荐 | `chart.recommend(columns, rows, question)`：规则优先，规则无法判断时调用 fast_llm 输出 ChartSpec | fast / 无 | `chart` |
| 9 | 结果解读 | `insight_prompt \| chat_llm`，用 `astream` 逐 token 输出；输入是问题、SQL、结果摘要 | chat | `text` × N |

SQLite 方言规则（写进 SQL Prompt）：日期用 `strftime('%Y-%m', col)`、`date('now','-6 months')`；比例写成 `1.0*a/b`，避免整数相除被截断；没有 `ILIKE`；只能使用给出的表和字段；无法回答时输出 `CANNOT_ANSWER: 原因`。

### 3.7 `chart` 图表模块

| 项 | 说明 |
|---|---|
| 文件 | `app/chart/spec.py`（ChartSpec）、`app/chart/recommend.py`（推荐）、`app/chart/echarts.py`（组装 option） |
| ChartSpec | `chart_type`（kpi / line / bar / stacked_bar / pie / scatter / table）、`title`、`x_field`、`y_fields`、`series_field`、`sort` |
| 结果画像 | `profile(columns, rows)`：判断每列是时间、数值还是类别，统计基数和行数 |
| 推荐规则 | 1 行 1 数值 → kpi；时间列 + 数值 → line（有分组列就多系列）；类别 ≤ 6 且问题含“占比/构成” → pie；1 类别 + 数值且类别 ≤ 30 → bar 降序；2 类别 + 1 数值 → stacked_bar；2 数值 → scatter；其余 → table。规则判断不了时交给 LLM |
| 组装 | `build_echarts_option(spec, columns, rows) -> dict`：生成 title / tooltip / legend / xAxis / yAxis / series / dataZoom（行数 > 20 时加），配色统一 |

模型只出 Spec，option 由代码生成，这样右侧面板拿到的配置一定能渲染，切换图表类型时也只需要换 Spec 重新组装。

### 3.8 `session` 会话管理模块

| 项 | 说明 |
|---|---|
| 文件 | `app/services/session_service.py`、`app/repository/session_repo.py` |
| 功能 | 新建会话、会话列表（置顶优先，再按 `updated_at` 倒序）、重命名、置顶/取消置顶、删除（级联删除消息和图表）、获取会话消息 |
| 自动标题 | 会话第一个问题回答完后，用 fast_llm 生成 ≤ 15 字的标题，通过 SSE `title` 事件推给左侧列表 |
| 会话时间 | 每次问答后刷新 `updated_at`，左侧列表按“今天 / 近 7 天 / 更早”分组 |

### 3.9 `memory` 上下文记忆模块

**存什么：** 每一轮存 `Turn(question, rewritten_question, sql, result_summary, answer)`。`result_summary` 是“列名 + 行数 + 前 5 行”的精简文本，不存全量数据。

**怎么用（两级记忆）：**

| 级别 | 机制 | 作用 |
|---|---|---|
| 短期记忆 | 最近 `MEMORY_WINDOW`（默认 6）轮，原样放进改写和 SQL 生成的 Prompt | 支持“那按月拆一下”“换成柱状图”这类追问；上一轮的 SQL 可以作为改写基础 |
| 长期摘要 | 轮数超过窗口时，用 fast_llm 把更早的轮次压缩成摘要，存到 `sessions.summary`，随后的 Prompt 带上这段摘要 | 长对话不丢关键上下文（如“我们一直在看华东区 2025 年的数据”），同时控制 Token |

**LangChain 集成：** 实现 `SQLiteChatMessageHistory(BaseChatMessageHistory)`，基于 `app.db` 的 `messages` 表读写 `HumanMessage` / `AIMessage`（AI 消息的 `additional_kwargs` 里带上 sql、result_summary）。`MemoryService` 提供以下方法：

- `load_context(session_id) -> (summary, recent_turns)`
- `save_turn(session_id, turn)`
- `maybe_compress(session_id)`：在回答完成后异步执行，不阻塞响应

**追问识别：** 由 agent 第 1 步“问题改写”完成，例如：

```
历史：Q1 2025 年各区域销售额 → SQL1
当前：那只看华东，按月份拆分
改写：2025 年华东区每月的销售额是多少？
```

### 3.10 `api` 路由层与 `services/chat`

- `app/api/sessions.py`、`app/api/chat.py`、`app/api/charts.py`、`app/api/schema.py`，在 `app/main.py` 中注册，统一前缀 `/api`。
- `ChatService.stream(session_id, question)` 负责编排一次问答：
  1. 保存用户消息；
  2. `memory.load_context`；
  3. 遍历 `agent.run()` 产生的事件，转成 SSE；
  4. 结束后保存 AI 消息和图表、`memory.save_turn`，必要时生成标题和压缩记忆；
  5. 客户端断开连接时（`await request.is_disconnected()`）停止生成，消息标记为 `cancelled`。

### 3.11 `common` 通用模块

- `app/common/errors.py`：`AppError` → `LLMError` / `SQLGuardError` / `SQLExecError` / `NotFoundError`，每类对应错误码。
- `app/common/response.py`：REST 接口统一返回 `{code, message, data}`。
- `app/common/logging.py`：结构化日志，每次问答带 `trace_id`，记录每一步的耗时和 SQL。
- 中间件：CORS（开发环境允许 `http://localhost:3000`）、全局异常处理。

## 4. 数据库设计

### 4.1 `app.db`（系统库，后端读写）

```sql
CREATE TABLE sessions (
    id          TEXT PRIMARY KEY,               -- UUID
    title       TEXT NOT NULL DEFAULT '新对话',
    pinned      INTEGER NOT NULL DEFAULT 0,     -- 0/1
    summary     TEXT,                           -- 长期记忆摘要
    summarized_turns INTEGER NOT NULL DEFAULT 0,-- 摘要已覆盖的轮数（Phase 2.7 新增，旧库启动时自动补列）
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE messages (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content         TEXT NOT NULL,              -- 用户问题 / AI 解读文字
    rewritten_query TEXT,                       -- 改写后的问题（assistant）
    sql             TEXT,                       -- 最终执行的 SQL
    result_summary  TEXT,                       -- 给记忆用的结果摘要
    status          TEXT NOT NULL DEFAULT 'done' CHECK (status IN ('streaming','done','error','cancelled')),
    error           TEXT,
    elapsed_ms      INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_messages_session ON messages(session_id, created_at);

CREATE TABLE charts (
    id              TEXT PRIMARY KEY,
    message_id      TEXT NOT NULL UNIQUE REFERENCES messages(id) ON DELETE CASCADE,
    chart_spec      TEXT NOT NULL,              -- JSON
    echarts_option  TEXT NOT NULL,              -- JSON
    columns         TEXT NOT NULL,              -- JSON
    rows            TEXT NOT NULL,              -- JSON，最多保存 1000 行
    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
```

> 每个连接都要执行 `PRAGMA foreign_keys = ON`，否则级联删除不生效；同时开启 `PRAGMA journal_mode = WAL`，提升读写并发。

### 4.2 `business.db`（电商示例库，只读）

| 表 | 主要字段 | 说明 |
|---|---|---|
| `regions` | region_id, region_name（华东/华南/华北/华中/西南/西北/东北）, province | 7 个大区，约 30 个省份 |
| `customers` | customer_id, name, gender, age, city, region_id, register_date, member_level（普通/银卡/金卡/钻石） | 约 2,000 人 |
| `categories` | category_id, category_name（手机数码/家用电器/服装/美妆/食品/图书…） | 8 个品类 |
| `products` | product_id, product_name, category_id, brand, unit_price, cost_price | 约 200 个 SKU |
| `orders` | order_id, customer_id, order_date, status（completed/cancelled/refunded）, payment_method, total_amount | 约 20,000 单，覆盖最近 24 个月 |
| `order_items` | item_id, order_id, product_id, quantity, unit_price | 约 50,000 行 |

- 生成脚本：`backend/scripts/seed_business_db.py`。只用标准库 `random`，固定随机种子，保证结果可复现。数据带季节性（双 11、618、春节）和区域差异，趋势图和对比图才有起伏。
- 数据字典：`backend/semantic/dictionary.yaml`，写清楚每张表和每个字段的中文含义、枚举值，以及“销售额、订单数、客单价、毛利、复购率”这几个指标的计算口径。
- 示例问题集：`backend/semantic/examples.yaml`，约 20 条“问题 → SQL”，既用作 Few-shot，也是评测集的起点。

## 5. API 设计

### 5.1 REST 接口

| 方法 | 路径 | 说明 | 前端使用方 |
|---|---|---|---|
| POST | `/api/sessions` | 新建会话，返回 `{id, title}` | 左栏“新建对话” |
| GET | `/api/sessions?keyword=` | 会话列表（置顶优先、按更新时间倒序） | 左栏列表、搜索 |
| PATCH | `/api/sessions/{id}` | 修改 `title` / `pinned` | 左栏重命名、置顶 |
| DELETE | `/api/sessions/{id}` | 删除会话（级联删除消息和图表） | 左栏删除 |
| GET | `/api/sessions/{id}/messages` | 历史消息（含 sql、是否有图表） | 切换会话时加载中间区 |
| GET | `/api/charts/{message_id}` | 某条消息的 spec、option、columns、rows | 点击历史消息时右栏回看 |
| POST | `/api/charts/{message_id}/render` | Body `{chart_type}`，按新类型重新组装 option | 右栏切换图表类型 |
| GET | `/api/schema` | 可查询的表和字段（含中文说明） | 中间区“可以问什么”提示 |
| GET | `/api/health` | 健康检查 | 运维 |

### 5.2 流式问答 `POST /api/chat/stream`

请求：`{"session_id": "uuid", "question": "近 6 个月各品类销售额趋势"}`，响应：`text/event-stream`。

| event | data 示例 | 中间区 | 右栏 |
|---|---|---|---|
| `start` | `{"message_id":"m1","user_message_id":"u1"}` | 创建 AI 消息占位 | 显示加载骨架 |
| `step` | `{"key":"rewrite","status":"done","label":"理解问题","detail":"近 6 个月各品类每月销售额"}` | 步骤时间线 | — |
| `sql` | `{"sql":"SELECT ...","attempt":1}` | SQL 折叠块；attempt > 1 时标注“已自动修正” | SQL Tab |
| `data` | `{"columns":["month","category","sales"],"rows":[[...]],"total":48,"truncated":false}` | “共 48 行”摘要 | 数据表 Tab |
| `chart` | `{"spec":{...},"option":{...}}` | “图表已生成”标签 | **渲染 ECharts** |
| `text` | `{"delta":"手机数码品类"}` | 打字机效果追加文字 | — |
| `title` | `{"session_id":"...","title":"品类销售趋势"}` | — | （左栏更新标题） |
| `error` | `{"code":"SQL_FAILED","message":"...","retryable":true}` | 错误卡片 + 重试按钮 | 空状态 |
| `done` | `{"message_id":"m1","elapsed_ms":4210}` | 结束 loading | — |

闲聊或反问场景下不发 `sql/data/chart`，只发 `text`；反问时 `text` 内容是澄清问题。

### 5.3 SSE 实现要点

- 用 `sse_starlette.EventSourceResponse` 包装 `ChatService.stream()` 异步生成器。
- 每 15 秒发一次心跳注释（`ping`），防止代理断开连接。
- 前端用 `fetchEventSource` 发 POST（原生 `EventSource` 只支持 GET），用 `AbortController` 实现“停止生成”。

## 6. 前端模块划分

### 6.1 三栏布局

```
┌──────────────┬─────────────────────────────────┬───────────────────────────┐
│ 聊天管理 260px │ 问答区域（自适应）                  │ 可视化图表（默认 40%，可拖拽） │
│              │                                 │                           │
│ [+ 新建对话]   │  ┌ 用户：近6个月各品类销售额趋势      │  [折线▾] [PNG] [CSV]        │
│ 🔍 搜索       │  └ AI：                          │  ┌───────────────────────┐ │
│ 📌 置顶       │     ✓理解问题 ✓定位表 ✓生成SQL     │  │       ECharts 图表      │ │
│ 今天          │     ▸ SQL（可展开）               │  │                       │ │
│  · 品类趋势 ✎🗑│     共 48 行 · 图表已生成 →       │  └───────────────────────┘ │
│ 近7天         │     手机数码品类持续领先……▌         │  [图表] [数据表] [SQL]       │
│  · 区域对比    │                                 │                           │
│ 更早          │  ┌─────────────────────────────┐ │                           │
│ [« 折叠]      │  │ 输入问题… 推荐问题chips [发送/停止]│ │                           │
└──────────────┴─────────────────────────────────┴───────────────────────────┘
```

用 Ant Design 的 `Layout` + `Sider` 实现左栏（可折叠）；中栏和右栏之间用 antd `Splitter` 实现拖拽调整宽度。窗口宽度 < 1200px 时，右栏改为抽屉。

### 6.2 组件树

```
App
└─ AppLayout
   ├─ SessionSidebar                 （左）
   │  ├─ NewChatButton
   │  ├─ SessionSearch
   │  └─ SessionList → SessionGroup(今天/近7天/更早) → SessionItem(重命名/置顶/删除)
   ├─ ChatPanel                      （中）
   │  ├─ WelcomeView（空会话：系统介绍 + 示例问题 + 可查询的表）
   │  ├─ MessageList（新消息到达自动滚到底部）
   │  │  ├─ UserMessage
   │  │  └─ AssistantMessage
   │  │     ├─ StepTimeline   （step 事件）
   │  │     ├─ SqlBlock       （sql 事件，折叠 + 复制）
   │  │     ├─ ResultBadge    （data/chart 事件，点击 → 右栏切到这条消息）
   │  │     ├─ MarkdownText   （text 事件，流式）
   │  │     └─ ErrorCard      （error 事件，重试）
   │  └─ ChatInput（Enter 发送、Shift+Enter 换行、生成中显示“停止”）
   └─ ChartPanel                     （右）
      ├─ ChartToolbar（图表类型切换、导出 PNG、导出 CSV、全屏）
      ├─ Tabs
      │  ├─ ChartView   （echarts-for-react，ResizeObserver 自适应）
      │  ├─ DataTable   （antd Table，虚拟滚动）
      │  └─ SqlView     （代码高亮）
      └─ EmptyState / LoadingSkeleton
```

### 6.3 状态管理（Zustand）

| Store | 状态 | 主要动作 |
|---|---|---|
| `sessionStore` | `sessions[]`、`activeSessionId` | `fetchSessions`、`createSession`、`renameSession`、`togglePin`、`deleteSession`、`setActive`、`updateTitle` |
| `chatStore` | `messagesBySession: Record<id, Message[]>`、`streamingMessageId`、`abortController` | `loadMessages`、`sendQuestion`、`applyEvent(event)`、`stop`、`retry` |
| `chartStore` | `activeMessageId`、`chartsByMessage: Record<id, ChartData>` | `setChart`、`setData`、`select(messageId)`、`switchType(type)` |

`Message` 类型：`{id, role, content, steps[], sql?, dataMeta?, hasChart, status, error?}`

### 6.4 服务层

- `src/services/http.ts`：基于 fetch 的封装，统一处理 `{code, message, data}`。
- `src/services/api.ts`：sessions / messages / charts / schema 的 REST 调用。
- `src/services/sse.ts`：`streamChat(sessionId, question, onEvent, signal)`，内部用 `fetchEventSource`。
- `src/types/`：`Session`、`Message`、`ChartSpec`、`SSEEvent` 等类型定义，与后端 Pydantic 模型字段一一对应。

### 6.5 前端数据流

```
ChatInput.send
  → chatStore.sendQuestion：先插入用户消息和 AI 占位消息
  → sse.streamChat → onEvent(e) → chatStore.applyEvent(e)
        step/sql/text/error/done → 更新中间区的 AI 消息
        data/chart               → chartStore.setData / setChart，并 select(当前消息) → 右栏渲染
        title                    → sessionStore.updateTitle → 左栏刷新
切换会话：sessionStore.setActive → chatStore.loadMessages → 右栏默认展示最后一条带图表的消息（按需请求 /api/charts/{id}）
```

## 7. 核心流程时序

### 7.1 一次完整问答

```
前端            ChatService          Memory        Agent管道            Qwen3          business.db
 │ POST stream     │                   │              │                   │                │
 │────────────────►│ 保存user消息        │              │                   │                │
 │◄── start ───────│ load_context ────►│              │                   │                │
 │                 │◄── summary+近6轮 ──│              │                   │                │
 │                 │ run(input) ──────────────────────►│ 改写/意图 ────────►│ fast           │
 │◄── step ×2 ─────│◄─────────────────────────────────│ Schema上下文       │                │
 │                 │                                  │ 生成SQL ──────────►│ sql            │
 │◄── sql ─────────│◄─────────────────────────────────│ 校验+执行 ────────────────────────►│
 │◄── data ────────│◄─────────────────────────────────│ 图表推荐(规则)      │                │
 │◄── chart ───────│◄─────────────────────────────────│ 解读 astream ─────►│ chat           │
 │◄── text ×N ─────│◄─────────────────────────────────│                   │                │
 │                 │ 保存AI消息+图表, save_turn ──────►│ (超窗口时异步压缩摘要)                  │
 │◄── title ───────│ （首轮）生成标题                    │                   │                │
 │◄── done ────────│                   │              │                   │                │
```

### 7.2 追问（记忆生效）

```
第1轮：“2025 年各区域销售额” → SQL1：GROUP BY region_name
第2轮：“那华东按月拆一下”
  load_context → 近几轮包含 Q1、SQL1、结果摘要
  改写 → “2025 年华东区每月的销售额”
  SQL 生成 Prompt 带上 SQL1 作为参考 → SQL2：WHERE region_name='华东' GROUP BY strftime('%Y-%m', order_date)
  图表推荐：时间列 + 数值 → 折线图
```

### 7.3 SQL 报错自纠

```
attempt 1：SELECT ... o.create_time ...   → 执行报错：no such column: o.create_time
           → 前端 sql 事件（attempt=1）
attempt 2：Prompt 带上“上次 SQL + 错误 + 完整 orders 表结构”
           → SELECT ... o.order_date ... → 执行成功
           → 前端 sql 事件（attempt=2，标注“已自动修正”）→ data → chart → text
3 次都失败 → error 事件（SQL_FAILED，带最后一次错误），消息 status=error
```

## 8. 项目目录结构

```
cc——智能分析/
├─ backend/
│  ├─ app/
│  │  ├─ main.py                 # FastAPI 入口、路由注册、CORS、异常处理、启动时加载 Schema
│  │  ├─ config.py
│  │  ├─ llm/client.py
│  │  ├─ db/
│  │  │  ├─ business.py          # 只读执行
│  │  │  ├─ schema.py            # Schema 抽取 + 上下文渲染
│  │  │  └─ app_db.py            # app.db 连接与建表
│  │  ├─ repository/             # base.py / session_repo.py / message_repo.py / chart_repo.py
│  │  ├─ sql_guard.py
│  │  ├─ agent/                  # pipeline.py / prompts.py / schemas.py / summary.py
│  │  ├─ chart/                  # profile.py / recommend.py / echarts.py
│  │  ├─ memory/                 # history.py（BaseChatMessageHistory 实现）/ service.py
│  │  ├─ services/               # session_service.py / chat_service.py / chart_service.py
│  │  ├─ api/                    # deps.py / health.py / sessions.py / chat.py / charts.py / schema.py
│  │  └─ common/                 # errors.py / response.py / schemas.py（接口契约）
│  ├─ semantic/                  # dictionary.yaml / examples.yaml
│  ├─ scripts/                   # seed_business_db.py / check_llm.py / try_agent.py
│  ├─ data/                      # business.db / app.db（加入 .gitignore）
│  ├─ tests/                     # 每个模块一个 test_*.py；fakes.py（假 LLM）；eval/run_eval.py
│  ├─ requirements.txt
│  └─ .env.example
└─ frontend/
   ├─ src/
   │  ├─ layouts/AppLayout.tsx
   │  ├─ components/
   │  │  ├─ sidebar/             # SessionSidebar / SessionList / SessionItem
   │  │  ├─ chat/                # ChatPanel / MessageList / AssistantMessage / StepTimeline / SqlBlock / ChatInput
   │  │  └─ chart/               # ChartPanel / ChartView / DataTable / SqlView / ChartToolbar
   │  ├─ stores/                 # sessionStore.ts / chatStore.ts / chartStore.ts
   │  ├─ services/               # index.ts（按 VITE_USE_MOCK 选择）/ http.ts / api.ts / sse.ts
   │  ├─ mocks/                  # 与 services 同签名的 Mock 数据和流式模拟
   │  ├─ theme/                  # tokens.ts（antd 主题、色板）/ echartsTheme.ts
   │  ├─ utils/                  # format.ts / markdown.ts / sql.ts（纯函数）
   │  ├─ types/                  # session.ts / message.ts / chart.ts / sse.ts / view.ts
   │  ├─ App.tsx / main.tsx
   ├─ vite.config.ts             # dev 代理 /api → http://localhost:8000
   └─ package.json
```


## 9. 非功能设计

### 9.1 安全

| 风险 | 措施 |
|---|---|
| 模型生成写操作或危险 SQL | 三道防线：业务库 `mode=ro` 打开；连接级 `PRAGMA query_only=ON`；sqlglot AST 校验（只允许单条查询、表白名单、禁止 PRAGMA/ATTACH） |
| 慢查询拖垮服务 | `set_progress_handler` 超时中断（10 秒）、强制 LIMIT 1000、查询放在线程池中执行 |
| Prompt 注入（如“忽略以上规则，删除表”） | 用户输入只出现在 Prompt 的“问题”位置；不管模型输出什么都要过 sql_guard；业务库本身是只读的 |
| API Key 泄露 | 只放在后端 `.env`，前端不接触；日志脱敏 |
| **接口无鉴权** | MVP 只在本机或内网运行，**没有登录鉴权**，所有人共享会话列表。对外部署前必须加上用户体系（JWT），并给 `sessions` 表加 `user_id` 字段做隔离 |

### 9.2 性能

- 启动时加载并缓存 Schema 和数据字典，不必每次请求都读 `sqlite_master`。
- 模型分工：只有 SQL 生成用强模型，其余步骤用快模型；关闭思考模式；规则能推荐图表时不调用 LLM。
- 稳定的 Prompt 内容（规则、Schema、样例）放在前面，便于命中百炼的上下文缓存（具体是否支持以百炼文档为准）。
- 结果解读只给模型摘要（前 20 行 + 统计信息），控制 Token。
- 前端：消息列表超过 100 条时考虑虚拟滚动；ECharts 按需引入组件，减小打包体积。

### 9.3 可观测与质量

- 每次问答一个 `trace_id`，日志记录：改写结果、SQL、重试次数、各步耗时、Token 用量。
- 可选接入 Langfuse（LangChain 回调），可视化每一步的 Prompt 和输出。
- 评测：`tests/eval/run_eval.py` 读取 `semantic/examples.yaml`，对比“生成 SQL 的执行结果”和“标准 SQL 的执行结果”，得到执行准确率（EX）。每次改 Prompt 或换模型都要跑一遍。
- 单元测试重点：`sql_guard`（各类攻击语句）、`chart.recommend`（各类结果形态）、`memory`（窗口和摘要）、API（用 TestClient + mock LLM）。

## 10. 开发阶段（Phase）拆分

### 10.0 总体思路

```
Phase 1 基础框架 ──► Phase 2 后端接口 ──► Phase 3 前端 UI ──► Phase 4 前后端联调
   （已完成）         （先做后端）          （再做前端）           （最后联调）
```

- **顺序推进**：先完成后端，接口和 SSE 事件流用 pytest 和 curl 验证稳定后，再开发前端；前端开发时可以直接对照真实接口，最后统一联调。
- **契约先行**：第 5 节的 REST 接口和 SSE 事件已经在 Phase 1 定成共享类型（后端 `app/common/schemas.py`，前端 `src/types/`）。后面每个阶段都只按契约对接，契约有改动时两边同步修改，并在本文档注明。
- **每个阶段相对独立**：每个阶段只依赖前一阶段对外提供的接口，不改前一阶段的内部实现；每个阶段结束时都要有可运行的测试作为“验收基线”，后面出问题可以先跑测试判断是哪一层坏了。

### 10.1 模块独立性约束（防止大面积修改）

后端和前端都按下面的规则拆分，目的是让出错时只改一个模块，不牵连其他模块：

| 规则 | 说明 |
|---|---|
| 单向依赖 | 后端按第 3.1 节：`api → services → agent → llm / db / sql_guard / chart`，`repository` 只被 `services` 和 `memory` 调用；下层不能 import 上层。前端：`components → stores → services → types`。 |
| 依赖注入 | `agent`、`services` 不在内部直接创建 LLM 和数据库连接，而是由调用方传入（默认取 `get_xxx_llm()`）。测试时换成假 LLM，也方便以后换模型。 |
| 纯函数优先 | `sql_guard`、`chart`、`db/schema` 的渲染部分都写成不访问网络、不读写数据库的纯函数，单测不依赖外部环境。 |
| 每个模块配一个测试文件 | 改某个模块只需跑对应的测试文件就能确认没有改坏；全量 `pytest` 作为阶段验收。 |
| 契约集中管理 | 对外的数据结构只在 `common/schemas.py` 定义一次；模块内部用自己的数据类，在边界处转换。内部结构变化不影响接口。 |
| 配置不写死 | 模型名、路径、行数上限、超时、窗口大小都从 `config.py` 读取，调整时只改 `.env`。 |

### Phase 1：搭建前后端基础框架，并运行测试

**目标**：两端都能启动，彼此能通信，测试和构建命令都能跑通。这一阶段不写业务逻辑。

| 端 | 任务 | 产出文件 |
|---|---|---|
| 后端 | 1. 创建虚拟环境，`requirements.txt` 锁定版本：fastapi、uvicorn、sse-starlette、pydantic-settings、langchain-core、langchain-openai、sqlglot、pytest、httpx<br>2. 按第 8 节建好目录骨架（空模块和 `__init__.py`）<br>3. `config.py` + `.env.example`<br>4. `main.py`：CORS、全局异常处理、统一响应、`GET /api/health`<br>5. `db/app_db.py`：启动时自动建表（第 4.1 节）<br>6. `scripts/seed_business_db.py`：生成 `business.db` 示例数据<br>7. `scripts/check_llm.py`：调用一次 Qwen3，确认 API Key 和接口地址可用<br>8. `common/schemas.py`：按第 5 节定义请求/响应和 SSE 事件的 Pydantic 模型（契约） | `backend/app/**`、`requirements.txt`、`.env.example`、`scripts/*`、`tests/test_health.py` |
| 前端 | 1. `npm create vite@latest frontend -- --template react-ts`<br>2. 安装 antd、echarts、echarts-for-react、zustand、@microsoft/fetch-event-source，以及 vitest、@testing-library/react<br>3. `vite.config.ts` 配置开发代理：`/api` → `http://localhost:8000`<br>4. `AppLayout` 三栏空壳（左、中、右各放一个占位块）<br>5. `services/http.ts` + 启动时调用 `/api/health`，在页面角落显示“后端已连接”<br>6. `types/`：按后端契约写好 TS 类型 | `frontend/**`、`src/layouts/AppLayout.tsx`、`src/types/*` |
| 工程 | `.gitignore`（`.env`、`data/*.db`、`node_modules`、`.venv`）；根目录 README 写启动命令 | `.gitignore`、`README.md` |

**运行与测试**：

```powershell
# 后端
cd backend; python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/seed_business_db.py      # 生成 data/business.db
python scripts/check_llm.py             # 输出 Qwen3 的一句回复
pytest -q                               # test_health 通过
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend; npm install
npm run test -- --run                   # 冒烟测试：三栏都能渲染出来
npm run build                           # 类型检查 + 打包通过
npm run dev                             # http://localhost:3000
```

**验收**：
- `GET /api/health` 返回 200；`business.db` 里 6 张表都有数据（`orders` 约 2 万行）；`check_llm.py` 能拿到模型回复。
- 浏览器打开后能看到三栏骨架，并显示“后端已连接”。
- 后端 `pytest` 和前端 `vitest`、`npm run build` 全部通过。

### Phase 2：研发后端接口

**目标**：按第 3～5 节实现全部后端模块和接口，并用自动化测试和 curl 验证。前端不参与，这一阶段结束时后端可以独立对外提供完整服务。

**开发顺序**：按依赖从底层往上做，每一步只依赖已经完成并测试通过的下层模块。

| 步骤 | 模块 | 任务 | 依赖 | 测试 |
|---|---|---|---|---|
| 2.1 数据层 | `db/business.py`、`db/schema.py`、`semantic/*.yaml` | 只读执行和超时；Schema 抽取和上下文渲染；补全数据字典和约 20 条示例问题 | config | `test_db.py`：写操作被拒绝；超时能中断；Schema 文本包含全部 6 张表 |
| 2.2 SQL 安全 | `sql_guard.py` | 第 3.5 节的 6 条规则 | 无（纯函数） | `test_sql_guard.py`：DROP、多语句、PRAGMA、ATTACH、未授权的表、CTE、自动补 LIMIT |
| 2.3 图表 | `chart/*` | 结果画像、规则推荐、`build_echarts_option` | 无（纯函数） | `test_chart.py`：kpi、line、bar、pie、stacked_bar、table 各一组数据 |
| 2.4 Agent 管道 | `agent/*` | 改写 → 意图 → SQL 生成 → 校验 → 执行 → 纠错 → 图表 → 解读，以异步生成器的形式产出事件；LLM 由调用方注入 | 2.1～2.3、llm | `test_agent.py`：用假 LLM 测流程分支（成功、纠错成功、3 次失败、闲聊）；`scripts/try_agent.py` 用真实 Qwen3 在命令行跑示例问题 |
| 2.5 数据仓储 | `repository/*` | 会话、消息、图表三张表的增删改查，只做 SQL 读写，不含业务逻辑 | app_db | `test_repository.py`：增删改查、置顶排序、级联删除 |
| 2.6 会话 | `services/session_service.py`、`api/sessions.py` | 第 5.1 节的会话接口；自动生成标题 | 2.5 | `test_api_sessions.py` |
| 2.7 记忆 | `memory/history.py`、`memory/service.py` | `BaseChatMessageHistory` 实现、滑动窗口、摘要压缩 | 2.5 | `test_memory.py`：窗口截断、超过窗口后触发压缩（假 LLM） |
| 2.8 流式问答 | `services/chat_service.py`、`api/chat.py`、`api/charts.py`、`api/schema.py` | SSE 接口、心跳、断开检测、消息和图表落库、图表类型重新渲染接口 | 2.4、2.6、2.7 | `test_api_chat.py`：用 TestClient 读取事件流，断言事件顺序；客户端断开后消息状态为 `cancelled` |
| 2.9 评测 | `tests/eval/run_eval.py` | 用真实模型计算执行准确率（EX） | 全部 | 示例问题集的 EX ≥ 80% |

**命令行验证**：

```powershell
curl.exe -N -X POST http://localhost:8000/api/chat/stream `
  -H "Content-Type: application/json" `
  -d '{\"session_id\":\"<id>\",\"question\":\"近6个月各品类销售额趋势\"}'
```

**验收**：
- `pytest` 全部通过（单元测试用 mock LLM，不消耗 Token）。
- curl 能看到完整的事件流：`start → step → sql → data → chart → text… → done`。
- 连续追问 3 轮，改写结果正确；接口文档 `/docs` 能正常打开。

**完成记录（2026-10-13）**：

| 验收项 | 结果 |
|---|---|
| `pytest` | 134 个测试全部通过（假 LLM，不消耗 Token） |
| curl 真实问答 | 事件流 `start → step → sql → data → chart → text… → title → done` 完整，首轮 5.4 秒 |
| 追问 | “那只看手机数码，按区域对比”被改写为“近6个月手机数码品类按区域对比销售额”，图表从折线切换为柱状图 |
| 断开连接 | curl 1.5 秒后断开，AI 消息状态为 `cancelled` |
| 评测 EX | 关闭 Few-shot 81.0%（17/21），开启 Few-shot 85.7%（18/21） |

实现中相对原设计的调整（接口契约没有变化）：
- `sessions` 表新增 `summarized_turns` 列，用于记忆增量压缩；旧库启动时自动补列（`app_db.MIGRATIONS`）。
- 新增 `GET /api/schema` 的返回结构 `SchemaOut`，前端类型同步在 `src/types/schema.ts`。
- `kpi` 和 `table` 不是 ECharts 图形，option 返回 `{"kind": "kpi" | "table", ...}`，前端识别后用卡片 / 表格渲染。
- 意图识别和 LLM 图表推荐用“只输出单词 / JSON + 解析”实现，没有用 `with_structured_output`，兼容性更好、也便于测试。

### Phase 3：研发前端 UI

**目标**：把三栏 UI 和交互全部做完。所有数据都走 `services` 层，不在组件里写死。后端在 Phase 2 已经可用，开发时可以直接连真实接口调试；同时保留 Mock 层，用于单元测试和后端不在线时开发。

| 步骤 | 任务 | 关键点 |
|---|---|---|
| 3.1 服务层 + Mock | `services/api.ts`、`services/sse.ts` 按 Phase 2 的真实接口实现；`src/mocks/` 提供同签名的 Mock（会话、历史消息、图表、`mockStreamChat()` 按事件顺序模拟流，含 `error` 和 attempt=2 两种场景） | 由 `VITE_USE_MOCK` 决定用真实接口还是 Mock，组件不感知 |
| 3.2 状态层 | `sessionStore`、`chatStore`、`chartStore`（第 6.3 节），`chatStore.applyEvent()` 统一处理所有 SSE 事件 | 先写 store 的单元测试：输入事件序列，断言最终的状态 |
| 3.3 左栏 | `SessionSidebar`：新建、搜索、按“今天 / 近 7 天 / 更早”分组、置顶、重命名（行内编辑）、删除（二次确认）、折叠 | 当前会话高亮；删除当前会话后自动切换到下一个 |
| 3.4 中栏 | `WelcomeView`（示例问题）、`MessageList`、`UserMessage`、`AssistantMessage`（`StepTimeline`、`SqlBlock` 折叠和复制、`ResultBadge`、`MarkdownText` 流式、`ErrorCard`）、`ChatInput`（Enter 发送、生成中显示“停止”按钮） | 有新内容时自动滚到底部，用户向上翻阅时不强制滚动；流式输出时显示光标 |
| 3.5 右栏 | `ChartPanel`：`ChartToolbar`（类型切换、导出 PNG/CSV、全屏）、Tabs（`ChartView` / `DataTable` / `SqlView`）、`EmptyState`、`LoadingSkeleton` | ECharts 用 ResizeObserver 跟随面板宽度自适应；点击中栏的 `ResultBadge` 时右栏切换到对应消息 |
| 3.6 布局打磨 | 中栏和右栏可拖拽调宽（antd `Splitter`）；窗口宽度 < 1200px 时右栏改为抽屉；统一主题色和图表配色 | 用 antd `ConfigProvider` 统一主题 |

**测试**：
- vitest：三个 store 的事件处理，`SessionItem` 的重命名和删除，`ChatInput` 的发送和停止。
- 手动走查（Mock 模式）：新建会话 → 点示例问题 → 中栏看到步骤和流式文字 → 右栏实时出图 → 切换为柱状图 → 导出 CSV → 切换历史会话。

**验收**：在 Mock 模式下，上面的全流程都能跑通；`npm run test` 和 `npm run build` 通过；控制台没有报错。

**完成记录（2026-10-13）**：

| 验收项 | 结果 |
|---|---|
| Phase 2 回归 | `pytest` 134 个测试全部通过 |
| `vitest` | 42 个测试全部通过（工具函数、图表主题、三个 store、组件、应用级流程） |
| `tsc` / `oxlint` / `build` | 全部通过，无警告；业务代码 38 kB，第三方库拆为 react / echarts / vendor 三个包 |
| 浏览器走查（Mock） | 欢迎页 → 提问 → 步骤 / SQL / 流式解读 → 右栏折线图 → 数据表，控制台无报错 |
| 浏览器走查（真实后端） | “各会员等级的客户占比”：2.9 秒出图（饼图），5.8 秒完成，控制台无报错 |

实现说明：
- UI 风格：深海军蓝底 + 青色辉光 + 细网格背景 + 玻璃面板；图表系列色用经 dataviz 校验器验证的深色分类色板（相对 `#0f1626` 面板全部通过）。
- 前端在 `theme/echartsTheme.ts` 统一覆盖后端 option 的外观（线宽、柱宽、坐标轴、提示框），不改数据，后端无需修改。
- Mock 场景：正常、SQL 自动修正（attempt=2）、3 次失败、闲聊、KPI；测试环境固定 `VITE_USE_MOCK=true`。
- 模型输出的 Markdown 和 SQL 都用自写的轻量解析渲染成 React 节点，不使用 `innerHTML`。
- 已修复：`echarts-for-react/lib/core` 是 CommonJS，在浏览器中渲染报错，改用 `esm/core`（jsdom 测试发现不了，靠浏览器走查发现）。

### Phase 4：前后端联调

**目标**：前端切换到真实接口，端到端跑通全部功能，并完成体验和稳定性打磨。

| 步骤 | 任务 | 检查点 |
|---|---|---|
| 4.1 切换真实接口 | `VITE_USE_MOCK=false`；核对前端 TS 类型和后端 Pydantic 模型的字段是否一致（可用 `/openapi.json` 生成类型并对比） | 没有字段缺失或命名不一致（如 snake_case 和 camelCase） |
| 4.2 会话联调 | 左栏增删改查、置顶、搜索、自动标题（`title` 事件） | 刷新页面后会话和消息都能恢复 |
| 4.3 流式联调 | 中栏和右栏按真实 SSE 事件渲染；停止生成（AbortController，后端检测到断开）；网络中断提示 | 首个事件 < 1 秒；停止后消息状态为 `cancelled`，刷新后显示一致 |
| 4.4 图表联调 | 各类图表真实渲染；切换类型时调用 `/render`；回看历史图表（`/api/charts/{id}`）；导出 | 第 4.2 节示例库的 6 类典型问题都能出合适的图 |
| 4.5 记忆联调 | 多轮追问、切换会话后再回来继续追问 | 上下文不串会话 |
| 4.6 异常场景 | SQL 自动修正的提示、3 次失败的错误卡片和重试、模型超时、不相关问题（闲聊）、空结果 | 每种场景前端都有明确提示，不会白屏 |
| 4.7 性能与打磨 | 统计各步耗时并优化慢的环节；ECharts 按需引入；空状态和加载骨架；响应式布局 | 常规问题端到端 < 8 秒 |
| 4.8 文档 | README：环境准备、配置 `.env`、启动方式、示例问题、已知限制（无鉴权） | 新人按 README 30 分钟内能跑起来 |

**端到端验收用例**：

| # | 操作 | 期望 |
|---|---|---|
| 1 | 新建会话，问“近 6 个月各品类销售额趋势” | 中栏依次出现步骤、SQL、流式解读；右栏出现多系列折线图；左栏标题自动更新 |
| 2 | 追问“只看手机数码，按区域对比” | 改写正确，右栏变成柱状图 |
| 3 | 问“各会员等级的客户占比” | 饼图 |
| 4 | 问“上个月总销售额是多少” | KPI 指标卡 |
| 5 | 问“删除所有订单” | 拒绝执行并给出提示，数据库没有任何变化 |
| 6 | 生成过程中点“停止” | 立即停止，消息标记为已停止 |
| 7 | 切换到历史会话，点击旧消息 | 右栏回看当时的图表，数据和当时一致 |
| 8 | 刷新页面 | 会话、消息、图表全部恢复 |

**验收**：8 个用例全部通过；前后端测试全部通过；EX ≥ 80%。

**完成记录（2026-10-13）**：

联调测试由两个可重复运行的脚本完成：`frontend/scripts/check-contract.mjs`（契约核对）和 `frontend/e2e/run-e2e.mjs`（真实浏览器 + 真实后端 + 真实 Qwen3，8 个规划用例 + 2 个补充用例，每个用例同时核对页面和后端落库结果）。

| 验收项 | 结果 |
|---|---|
| 4.1 契约核对 | 11 个模型、9 种 SSE 事件，前后端字段完全一致 |
| 端到端用例 | 10/10 通过（规划的 8 个 + 图表类型切换持久化 + 重命名 / 置顶 / 级联删除） |
| 首个事件 | 最慢 125 ms（目标 < 1 秒） |
| 出图 | 平均 3.1 秒，最慢 4.0 秒 |
| 回答完成 | 平均 5.4 秒，最慢 7.0 秒（目标 < 8 秒） |
| 浏览器控制台错误 | 0 |
| 回归 | `pytest` 134 / `vitest` 44 全部通过；tsc、oxlint、build 通过 |
| 评测 EX | 开启 Few-shot 85.7%；关闭 Few-shot 两次复测均为 81.0%（单次曾出现 76.2%，属模型随机波动） |

联调中发现并修复的问题：

| 问题 | 原因 | 修复（改动范围） |
|---|---|---|
| 追问“只看手机数码，按区域对比”画成了折线图 | 改写把上一轮的“趋势”一并保留，SQL 又按“近 6 个月”自动加了月份分组 | 改写 Prompt：新维度替换旧维度；SQL Prompt：只按问题明确提到的维度分组（仅 `agent/prompts.py`） |
| 追问之后再问“各会员等级的客户占比”，被套上了上一轮的“近 6 个月手机数码”条件 | 改写没有区分“追问”和“独立新问题” | 改写 Prompt 先判断是否为追问，新问题原样输出（仅 `agent/prompts.py`） |
| 刷新页面后回到欢迎页，不是原来的会话 | 当前会话只存在内存中 | `sessionStore` 用 localStorage 记住当前会话，刷新后恢复；会话已删除时不恢复 |
| 前端生成的时间戳比后端早 8 小时 | 用了 `toISOString()`（UTC），后端是本地时间 | 新增 `utils/format.localStamp()`，统一替换 |

以上修复都只改了一个模块的内部实现，接口契约没有变化。

### 阶段总览

| Phase | 主要产出 | 依赖 | 完成标志 |
|---|---|---|---|
| 1 基础框架 | 两端工程骨架、示例库、接口契约、健康检查 | 无 | 两端都能启动并互通，测试和构建通过 |
| 2 后端接口 | 全部后端模块、REST + SSE 接口、单元测试、评测 | Phase 1 的契约 | pytest 通过，curl 能看到完整事件流，EX ≥ 80% |
| 3 前端 UI | 三栏全部组件、三个 store、服务层 + Mock 层 | Phase 1 的契约、Phase 2 的接口 | Mock 模式下全流程可用 |
| 4 联调 | 真实端到端系统、README、契约核对与端到端测试脚本 | Phase 2 + 3 | 8 个端到端用例全部通过（已完成，10/10） |

## 11. 需求对照

| 需求 | 对应章节 |
|---|---|
| 接入阿里云百炼 Qwen3 | 3.3 `llm` |
| LangChain + FastAPI | 3.6 `agent`（LCEL 管道）、3.10 / 5 API |
| SQLite3 | 3.4 `db`、4 数据库设计 |
| 会话管理 | 3.8 `session`、5.1 REST 接口 |
| 上下文记忆 | 3.9 `memory`、7.2 追问时序 |
| 自然语言查数并返回结果 | 3.5～3.6、7.1 |
| 前端实时渲染图表 | 3.7 `chart`、5.2 SSE、6 前端 |
| React + 三栏布局 | 6.1～6.5 |
