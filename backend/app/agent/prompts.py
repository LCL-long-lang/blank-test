"""全部 Prompt 模板集中在这里，调 Prompt 只改这个文件。

稳定内容（规则、Schema、样例）放在 system 消息前部，便于命中模型侧的上下文缓存。
"""
from langchain_core.prompts import ChatPromptTemplate

from app.agent.schemas import Turn

# ---------- 1. 问题改写 ----------

REWRITE_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "你负责把数据分析对话中的追问改写成一个完整、独立的问题。\n"
     "第一步，判断当前问题是“追问”还是“新问题”：\n"
     "- 追问：缺少指标或分析对象，需要依赖上文才能理解，通常带有“那 / 这个 / 再 / 只看 / 换成 / 按…拆 / 同样 / 上面”等指代词；\n"
     "- 新问题：自己说清了指标和分析对象（如“各会员等级的客户占比”“上个月总销售额是多少”），"
     "即使和上文主题相近也是新问题。新问题必须原样输出，不得继承上文的时间范围、品类、区域等筛选条件。\n"
     "第二步，只对追问做改写：\n"
     "1. 结合历史补全省略的时间范围、指标、筛选条件；\n"
     "2. 追问给出了新的分析维度（如“按区域对比”“按月拆分”“换成按品牌”）时，用新维度替换上一轮的维度，"
     "不要同时保留上一轮的“趋势 / 按月 / 各品类”等分组方式；只有用户明确说“再加上 / 同时按”时才叠加；\n"
     "3. 追问给出了新的筛选（如“只看手机数码”）时，在原筛选上收窄。\n"
     "只输出最终的问题，不要解释，不要加引号。\n"
     "示例 1（追问）：上一轮“近 6 个月各品类销售额趋势”，当前“只看手机数码，按区域对比” → "
     "“近 6 个月手机数码品类各区域的销售额对比”\n"
     "示例 2（新问题）：上一轮“近 6 个月手机数码品类各区域的销售额对比”，当前“各会员等级的客户占比” → "
     "“各会员等级的客户占比”"),
    ("human", "{summary_block}历史对话：\n{history}\n\n当前问题：{question}\n\n改写后的问题："),
])

# ---------- 2. 意图识别 ----------

INTENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "你是电商数据分析助手的意图分类器。数据库包含：{table_labels}。\n"
     "分类规则：\n"
     "- query：需要查询上述数据才能回答的问题（统计、排名、趋势、明细、对比等）；\n"
     "- chitchat：问候、闲聊、询问系统能做什么，或与这些数据无关的问题；\n"
     "- clarify：想查数据，但关键信息缺失到无法写出查询（如“那个怎么样”且没有上下文）。\n"
     "大多数和业务相关的问题都应判为 query，信息不全时按常理补全默认值，不要轻易判 clarify。\n"
     "只输出一个单词：query、chitchat 或 clarify。"),
    ("human", "{question}"),
])

# ---------- 4. SQL 生成 ----------

SQL_SYSTEM = """你是资深数据分析师，负责把问题翻译成一条 SQLite 查询。

## 数据库结构
{schema}

## SQLite 方言规则
- 日期是 TEXT：按月 strftime('%Y-%m', col)，按年 strftime('%Y', col)，按天 date(col)
- 比例写成 1.0 * a / b，避免整数相除被截断；需要时用 ROUND(x, 2)
- 没有 ILIKE，模糊匹配用 LIKE；字符串用单引号
- 列别名用英文 snake_case（如 sales、order_count），便于后续画图
- 时间维度、排名类问题要加 ORDER BY；排名类问题加 LIMIT

## 业务约定（问题没有特别说明时）
- 相对时间以今天为基准，按自然月/年计算：
  “近 N 个月 / 过去 N 个月”包含本月，起点 date('now', 'start of month', '-(N-1) months')；
  “过去一年 / 近一年 / 近 12 个月”即近 12 个月；“上个月”= date('now', 'start of month', '-1 month') 所在月；
  “近 N 天”起点 date('now', '-N days')；“今年 / 去年”按 strftime('%Y', ...) 判断
- “占比 / 分布 / 构成”类问题返回各类别的数量或金额（饼图会自动计算百分比），可以再附加比例列
- 多个系列的对比（如今年 vs 去年、各大区 × 各品类）用长表输出：维度列 + 系列列 + 数值列，不要用 CASE WHEN 拼成宽表
- 订单层面的比率（退款率、取消率）按订单去重计算：COUNT(DISTINCT order_id)
- 明细 / 排名类问题只返回问题提到的字段，加上必要的名称列，不要额外返回 ID 列
- 分组维度只取问题明确提到的：问“各区域对比 / 按区域”只按区域分组；
  问题出现“趋势 / 每月 / 按月 / 走势”才按时间分组；时间范围只用作 WHERE 筛选，不自动变成分组

## 约束
- 只能使用上面给出的表和字段，只能写一条 SELECT（可用 WITH）
- 严格遵循“指标口径”，销售类指标默认只统计 status='completed' 的订单
- 只输出 SQL 本身，不要解释，不要 Markdown 代码块
- 如果问题无法用这些数据回答，只输出：CANNOT_ANSWER: 原因

## 参考示例
{few_shots}"""

SQL_HUMAN = """今天是 {today}。
{history_block}问题：{question}{retry_block}

SQL："""

SQL_PROMPT = ChatPromptTemplate.from_messages([("system", SQL_SYSTEM), ("human", SQL_HUMAN)])

RETRY_TEMPLATE = """

上一次生成的 SQL 执行失败，请修正：
```
{last_sql}
```
错误信息：{last_error}"""

EMPTY_RESULT_HINT = "查询成功但返回 0 行。请检查筛选条件（枚举值、日期范围、关联条件）是否过严；如果确实没有数据，可以保持原 SQL 不变。"

# ---------- 8. 图表推荐（规则判断不了时） ----------

CHART_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "根据查询结果的列和样例数据，为问题选择最合适的图表。\n"
     "可选类型：kpi（单个指标）、line（趋势）、bar（分类对比/排名）、stacked_bar（两个维度对比）、"
     "pie（≤6 类的占比）、scatter（两个数值的相关性）、table（明细或不适合画图）。\n"
     "x_field、y_fields、series_field 必须是结果中真实存在的列名；y_fields 必须是数值列。\n"
     "类别很多（> 30）时优先选 table，或 bar 并设置 sort=desc。\n"
     "只输出一个 JSON 对象，不要解释，格式：\n"
     '{{"chart_type": "bar", "x_field": "列名", "y_fields": ["列名"], "series_field": null, "sort": "desc"}}'),
    ("human", "问题：{question}\n\n结果：\n{result}"),
])

# ---------- 9. 结果解读 ----------

INSIGHT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "你是数据分析师，根据查询结果给业务人员写简短解读。\n"
     "要求：\n"
     "- 先直接回答问题，再列 1~3 个关键发现（最高/最低、趋势、占比、异常）；\n"
     "- 只使用结果中出现的数字，不要编造；金额保留两位小数并加千分位，比例用百分数；\n"
     "- 用 Markdown，控制在 150 字以内；不要复述 SQL，不要说“根据查询结果”。"),
    ("human", "问题：{question}\n\n查询结果摘要：\n{summary}"),
])

# ---------- 闲聊 / 反问 ----------

CHITCHAT_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "你是电商智能数据分析助手，可以用自然语言查询以下数据并生成图表：{table_labels}。\n"
     "用户在闲聊或询问能力时，简短友好地回答，并给出 2~3 个可以问的示例问题。"
     "与数据无关的问题，礼貌说明你只负责数据分析。回答控制在 100 字以内。"),
    ("human", "{question}"),
])

CLARIFY_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "用户想查询数据，但信息不足以写出查询。可查询的数据：{table_labels}。\n"
     "用一两句话反问用户缺少的关键信息（如时间范围、指标、维度），并给出 2 个具体的问法示例。"),
    ("human", "{question}"),
])


# ---------- 渲染辅助（纯函数） ----------

def format_history(turns: list[Turn], with_sql: bool = True) -> str:
    if not turns:
        return "（无）"
    lines = []
    for i, t in enumerate(turns, 1):
        lines.append(f"Q{i}：{t.rewritten_question or t.question}")
        if with_sql and t.sql:
            lines.append(f"SQL{i}：{' '.join(t.sql.split())}")
        if t.result_summary:
            lines.append(f"结果{i}：{t.result_summary.splitlines()[0]}")
    return "\n".join(lines)


def format_summary_block(summary: str) -> str:
    return f"更早对话的摘要：{summary}\n\n" if summary else ""


def format_history_block(turns: list[Turn], summary: str) -> str:
    """SQL 生成时带上最近几轮的问题和 SQL，作为追问的参考。"""
    if not turns and not summary:
        return ""
    block = format_summary_block(summary)
    if turns:
        block += ("最近的对话（之前的 SQL 只用于参考表关联和筛选条件；分组维度以当前问题为准）：\n"
                  + format_history(turns) + "\n\n")
    return block


def format_few_shots(examples: list[dict], limit: int = 6) -> str:
    shots = [e for e in examples if e.get("few_shot")][:limit]
    return "\n\n".join(f"问题：{e['question']}\nSQL：\n{e['sql'].strip()}" for e in shots) or "（无）"


def format_retry_block(last_sql: str | None, last_error: str | None) -> str:
    if not last_sql:
        return ""
    return RETRY_TEMPLATE.format(last_sql=last_sql, last_error=last_error)
