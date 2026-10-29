"""业务库 Schema 抽取 + 数据字典合并 + Prompt 上下文渲染。

- load_schema：读 sqlite_master / PRAGMA，得到表结构（访问数据库）
- load_dictionary / load_examples：读 semantic/*.yaml（访问文件）
- render_schema_context：纯函数，把表结构和数据字典渲染成精简 DDL 文本
- get_catalog：启动时加载一次并缓存，供 agent 和 /api/schema 使用
"""
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import BACKEND_DIR
from app.db.business import connect_readonly

SEMANTIC_DIR = BACKEND_DIR / "semantic"
# 文本列不同取值不超过该数量时，抽取样例值写进上下文（帮助模型写对 WHERE 条件）
SAMPLE_MAX_DISTINCT = 10


@dataclass
class ColumnInfo:
    name: str
    type: str
    pk: bool = False
    description: str = ""
    samples: list[str] = field(default_factory=list)


@dataclass
class ForeignKey:
    column: str
    ref_table: str
    ref_column: str


@dataclass
class TableInfo:
    name: str
    columns: list[ColumnInfo]
    foreign_keys: list[ForeignKey] = field(default_factory=list)
    label: str = ""
    description: str = ""
    row_count: int = 0


@dataclass
class Catalog:
    tables: list[TableInfo]
    metrics: dict[str, str]
    examples: list[dict[str, Any]]
    context: str

    @property
    def table_names(self) -> set[str]:
        return {t.name for t in self.tables}


def load_schema(path: Path | None = None) -> list[TableInfo]:
    conn = connect_readonly(path)
    try:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
        )]
        tables = []
        for name in names:
            cols = []
            for _, cname, ctype, _, _, pk in conn.execute(f'PRAGMA table_info("{name}")'):
                col = ColumnInfo(name=cname, type=ctype or "TEXT", pk=bool(pk))
                if col.type.upper() == "TEXT" and not col.pk:
                    distinct = [r[0] for r in conn.execute(
                        f'SELECT DISTINCT "{cname}" FROM "{name}" WHERE "{cname}" IS NOT NULL LIMIT {SAMPLE_MAX_DISTINCT + 1}'
                    )]
                    if len(distinct) <= SAMPLE_MAX_DISTINCT:
                        col.samples = sorted(str(v) for v in distinct)
                cols.append(col)
            fks = [ForeignKey(column=r[3], ref_table=r[2], ref_column=r[4])
                   for r in conn.execute(f'PRAGMA foreign_key_list("{name}")')]
            row_count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            tables.append(TableInfo(name=name, columns=cols, foreign_keys=fks, row_count=row_count))
        return tables
    finally:
        conn.close()


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_dictionary(path: Path | None = None) -> dict:
    return _load_yaml(path or SEMANTIC_DIR / "dictionary.yaml")


def load_examples(path: Path | None = None) -> list[dict[str, Any]]:
    return _load_yaml(path or SEMANTIC_DIR / "examples.yaml").get("examples", [])


def merge_dictionary(tables: list[TableInfo], dictionary: dict) -> list[TableInfo]:
    """把数据字典的中文说明合并进表结构（字典里有、库里没有的表/字段直接忽略）。"""
    meta = dictionary.get("tables", {})
    for t in tables:
        tmeta = meta.get(t.name, {})
        t.label = tmeta.get("label", "")
        t.description = tmeta.get("description", "")
        col_meta = tmeta.get("columns", {})
        for c in t.columns:
            c.description = col_meta.get(c.name, "")
    return tables


def render_schema_context(tables: list[TableInfo], metrics: dict[str, str] | None = None) -> str:
    """渲染成精简 DDL 风格文本，供 SQL 生成 Prompt 使用。"""
    blocks = []
    for t in tables:
        head = f"-- {t.label}" if t.label else ""
        if t.description:
            head += f"：{t.description}" if head else f"-- {t.description}"
        lines = [head] if head else []
        lines.append(f"CREATE TABLE {t.name} (  -- 约 {t.row_count} 行")
        fk_map = {fk.column: fk for fk in t.foreign_keys}
        for i, c in enumerate(t.columns):
            parts = [f"  {c.name} {c.type}"]
            if c.pk:
                parts.append("PRIMARY KEY")
            if c.name in fk_map:
                fk = fk_map[c.name]
                parts.append(f"REFERENCES {fk.ref_table}({fk.ref_column})")
            line = " ".join(parts) + ("," if i < len(t.columns) - 1 else "")
            notes = c.description
            if c.samples and "取值" not in notes:
                notes = (notes + "；" if notes else "") + "取值：" + "、".join(c.samples)
            if notes:
                line += f"  -- {notes}"
            lines.append(line)
        lines.append(");")
        blocks.append("\n".join(lines))

    text = "\n\n".join(blocks)
    if metrics:
        text += "\n\n-- 指标口径\n" + "\n".join(f"-- {k}：{v}" for k, v in metrics.items())
    return text


def build_catalog(db_path: Path | None = None, dictionary_path: Path | None = None,
                  examples_path: Path | None = None) -> Catalog:
    dictionary = load_dictionary(dictionary_path)
    tables = merge_dictionary(load_schema(db_path), dictionary)
    metrics = dictionary.get("metrics", {})
    return Catalog(
        tables=tables,
        metrics=metrics,
        examples=load_examples(examples_path),
        context=render_schema_context(tables, metrics),
    )


@lru_cache
def get_catalog() -> Catalog:
    """进程内缓存；业务库或字典变更后调用 get_catalog.cache_clear() 重新加载。"""
    return build_catalog()
