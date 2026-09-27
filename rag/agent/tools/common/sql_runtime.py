"""Safe schema discovery, entity resolution, and read-only SQL execution."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from time import perf_counter
from typing import Any, Literal

import psycopg
import sqlglot
from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from psycopg import sql as psycopg_sql
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator
from sqlglot import exp

from config.settings import (
    load_agent_settings,
    load_application_settings,
    load_environment_settings,
)
from observability import logger
from rag.agent.sql_approval import sql_approval_manager
from rag.agent.tools.common.schema_catalog import (
    AGENT_TABLES,
    COLUMN_DETAILS,
    ENTITY_FIELDS,
    PROHIBITED_COLUMNS,
    SCHEMA_CATALOG,
    SqlAgentName,
)


_SQL_SETTINGS = load_agent_settings().sql
_APPLICATION_SETTINGS = load_application_settings()

# Compatibility names retained for integrations that import the old constants.
DEFAULT_MAX_ROWS = _SQL_SETTINGS.max_rows_per_subtask
DEFAULT_MAX_RESULT_CHARS = _SQL_SETTINGS.max_result_chars_per_subtask
DEFAULT_TIMEOUT_MS = _SQL_SETTINGS.statement_timeout_ms
DEFAULT_MAX_ATTEMPTS = _SQL_SETTINGS.max_attempts_per_subtask
PARAMETER_PATTERN = re.compile(r"%\(([A-Za-z_][A-Za-z0-9_]*)\)s")


def sql_max_rows() -> int:
    return _SQL_SETTINGS.max_rows_per_subtask


def sql_timeout_ms() -> int:
    return _SQL_SETTINGS.statement_timeout_ms


def sql_max_result_chars() -> int:
    return _SQL_SETTINGS.max_result_chars_per_subtask


def sql_max_attempts() -> int:
    return _SQL_SETTINGS.max_attempts_per_subtask


class SchemaSearchInput(BaseModel):
    query: str = Field(
        min_length=_SQL_SETTINGS.schema_search_min_query_length,
        max_length=_SQL_SETTINGS.schema_search_max_query_length,
        description="An English schema-search phrase containing the required metrics, entities, and filters.",
    )
    top_k: int = Field(
        default=_SQL_SETTINGS.schema_search_default_top_k,
        ge=1,
        le=_SQL_SETTINGS.schema_search_max_top_k,
    )


class EntityResolutionInput(BaseModel):
    entity_type: str = Field(
        min_length=_SQL_SETTINGS.entity_type_min_length,
        max_length=_SQL_SETTINGS.entity_type_max_length,
        description=(
            "One supported non-product-name entity type returned by the schema "
            "tool. Never use entity_type='product' for a product name; resolve "
            "product names with find_real_name. product_category remains allowed."
        ),
    )
    user_term: str = Field(
        min_length=_SQL_SETTINGS.entity_term_min_length,
        max_length=_SQL_SETTINGS.entity_term_max_length,
        description="The user's entity phrase or a careful translated candidate.",
    )
    limit: int = Field(
        default=_SQL_SETTINGS.entity_resolution_default_limit,
        ge=1,
        le=_SQL_SETTINGS.entity_resolution_max_limit,
    )


class ColumnDetailInput(BaseModel):
    table_name: str = Field(
        min_length=1,
        max_length=_SQL_SETTINGS.table_name_max_length,
        description="One authorized table name returned by the schema search tool.",
    )


SqlParameter = str | int | float | bool | None


class ReadonlySqlInput(BaseModel):
    sql: str = Field(
        min_length=_SQL_SETTINGS.min_sql_length,
        max_length=_SQL_SETTINGS.max_sql_length,
        description="One PostgreSQL SELECT query using only schema returned by the schema tool.",
    )
    parameters: dict[str, SqlParameter] = Field(
        default_factory=dict,
        description="Values for psycopg named placeholders such as %(period_start)s.",
    )
    purpose: str = Field(
        min_length=3,
        max_length=_SQL_SETTINGS.max_purpose_length,
        description="A short public explanation of what this query measures.",
    )

    @field_validator("parameters")
    @classmethod
    def validate_parameter_count(
        cls, value: dict[str, SqlParameter]
    ) -> dict[str, SqlParameter]:
        maximum = _SQL_SETTINGS.max_parameters_per_query
        if len(value) > maximum:
            raise ValueError(f"No more than {maximum} SQL parameters are allowed")
        return value


ValidationErrorType = Literal[
    "column_not_exposed",
    "empty_sql",
    "forbidden_function",
    "forbidden_statement",
    "locking_select_forbidden",
    "missing_authorized_table",
    "multiple_statements",
    "non_select_statement",
    "parameter_mismatch",
    "parse_error",
    "positional_parameter_forbidden",
    "prohibited_column",
    "schema_scope_violation",
    "select_into_forbidden",
    "select_star_forbidden",
    "unauthorized_table",
    "unknown_qualifier",
]


class SqlValidationError(ValueError):
    """Raised with a stable code when SQL violates one real validator branch."""

    def __init__(self, validation_error_type: ValidationErrorType, message: str) -> None:
        super().__init__(message)
        self.validation_error_type = validation_error_type


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return "[binary data omitted]"
    maximum = _SQL_SETTINGS.max_string_cell_chars
    if isinstance(value, str) and len(value) > maximum:
        return value[:maximum] + "… [truncated]"
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _parse_for_validation(query: str) -> exp.Expression:
    parseable = PARAMETER_PATTERN.sub("NULL", query)
    try:
        statements = sqlglot.parse(parseable, read="postgres")
    except sqlglot.errors.ParseError as exc:
        raise SqlValidationError(
            "parse_error",
            f"PostgreSQL parse failed: {exc}",
        ) from exc
    if len(statements) != 1 or statements[0] is None:
        raise SqlValidationError(
            "multiple_statements",
            "Exactly one SQL statement is required",
        )
    return statements[0]


def validate_readonly_sql(
    query: str,
    parameters: dict[str, SqlParameter],
    agent_name: SqlAgentName,
) -> tuple[str, list[str]]:
    """Validate one generated query and return its normalized text and tables."""

    clean_query = query.strip().rstrip(";").strip()
    if not clean_query:
        raise SqlValidationError("empty_sql", "SQL must not be empty")

    placeholder_names = set(PARAMETER_PATTERN.findall(clean_query))
    parameter_names = set(parameters)
    if placeholder_names != parameter_names:
        missing = sorted(placeholder_names - parameter_names)
        extra = sorted(parameter_names - placeholder_names)
        raise SqlValidationError(
            "parameter_mismatch",
            f"SQL parameter mismatch; missing={missing}, extra={extra}"
        )
    if re.search(r"(?<!%)%s", clean_query):
        raise SqlValidationError(
            "positional_parameter_forbidden",
            "Only named psycopg placeholders are allowed",
        )

    expression = _parse_for_validation(clean_query)
    allowed_roots = tuple(
        node_type
        for node_type in (
            getattr(exp, "Select", None),
            getattr(exp, "Union", None),
            getattr(exp, "Intersect", None),
            getattr(exp, "Except", None),
        )
        if node_type is not None
    )
    if not isinstance(expression, allowed_roots):
        raise SqlValidationError(
            "non_select_statement",
            "Only SELECT queries are allowed",
        )

    forbidden_types = tuple(
        node_type
        for type_name in (
            "Insert", "Update", "Delete", "Create", "Drop", "Alter",
            "Command", "Merge", "Copy", "Grant", "Revoke", "Transaction",
        )
        if (node_type := getattr(exp, type_name, None)) is not None
    )
    if forbidden_types and any(expression.find_all(*forbidden_types)):
        raise SqlValidationError(
            "forbidden_statement",
            "DDL, DML, COPY, and transaction commands are forbidden",
        )
    if any(expression.find_all(exp.Into)):
        raise SqlValidationError(
            "select_into_forbidden",
            "SELECT INTO is forbidden",
        )
    lock_type = getattr(exp, "Lock", None)
    if lock_type is not None and any(expression.find_all(lock_type)):
        raise SqlValidationError(
            "locking_select_forbidden",
            "Locking SELECT statements are forbidden",
        )
    for star in expression.find_all(exp.Star):
        if isinstance(star.parent, exp.Count):
            continue
        raise SqlValidationError(
            "select_star_forbidden",
            "SELECT * is forbidden; name every required column",
        )

    for column in expression.find_all(exp.Column):
        if column.name.lower() in PROHIBITED_COLUMNS:
            raise SqlValidationError(
                "prohibited_column",
                f"Access to column '{column.name}' is forbidden",
            )

    dangerous_functions = {
        "dblink", "dblink_connect", "lo_export", "lo_import", "pg_ls_dir",
        "pg_read_binary_file", "pg_read_file", "pg_sleep", "set_config",
    }
    for function in expression.find_all(exp.Func):
        name = getattr(function, "name", "") or function.sql_name()
        if str(name).lower() in dangerous_functions:
            raise SqlValidationError(
                "forbidden_function",
                f"Function '{name}' is forbidden",
            )

    cte_names = {
        cte.alias_or_name.lower()
        for cte in expression.find_all(exp.CTE)
        if cte.alias_or_name
    }
    tables: set[str] = set()
    for table in expression.find_all(exp.Table):
        table_name = table.name.lower()
        if table_name in cte_names:
            continue
        schema_name = str(table.db or "").lower()
        catalog_name = str(table.catalog or "").lower()
        if catalog_name or schema_name not in {"", "public"}:
            raise SqlValidationError(
                "schema_scope_violation",
                "Only the public business schema is available",
            )
        tables.add(table_name)

    if not tables:
        raise SqlValidationError(
            "missing_authorized_table",
            "The query must read at least one authorized business table",
        )
    unauthorized = sorted(tables - set(AGENT_TABLES[agent_name]))
    if unauthorized:
        raise SqlValidationError(
            "unauthorized_table",
            f"{agent_name} is not authorized to query: {', '.join(unauthorized)}"
        )

    table_aliases: dict[str, str] = {}
    for table in expression.find_all(exp.Table):
        physical_name = table.name.lower()
        if physical_name in cte_names:
            continue
        table_aliases[physical_name] = physical_name
        if table.alias:
            table_aliases[str(table.alias).lower()] = physical_name

    projection_aliases = {
        str(item.alias).lower()
        for select in expression.find_all(exp.Select)
        for item in select.expressions
        if item.alias
    }
    derived_aliases = {
        subquery.alias_or_name.lower()
        for subquery in expression.find_all(exp.Subquery)
        if subquery.alias_or_name
    }
    allowed_columns_by_table = {
        table_name: {
            str(column).lower()
            for column in SCHEMA_CATALOG[table_name]["columns"]
        }
        for table_name in tables
    }
    allowed_unqualified = set().union(*allowed_columns_by_table.values())
    allowed_unqualified.update(projection_aliases)
    for column in expression.find_all(exp.Column):
        column_name = column.name.lower()
        qualifier = str(column.table or "").lower()
        if qualifier in cte_names or qualifier in derived_aliases:
            continue
        physical_table = table_aliases.get(qualifier) if qualifier else None
        if physical_table is not None:
            if column_name not in allowed_columns_by_table[physical_table]:
                raise SqlValidationError(
                    "column_not_exposed",
                    f"Column '{column.name}' is not exposed for table '{physical_table}'"
                )
        elif qualifier:
            raise SqlValidationError(
                "unknown_qualifier",
                f"Unknown table or derived-table qualifier '{column.table}'"
            )
        elif not qualifier and column_name not in allowed_unqualified:
            raise SqlValidationError(
                "column_not_exposed",
                f"Column '{column.name}' is not exposed by the authorized schema"
            )
    return clean_query, sorted(tables)


def search_schema_catalog(
    agent_name: SqlAgentName,
    query: str,
    top_k: int,
) -> dict[str, Any]:
    """Rank the small curated schema catalog without exposing system catalogs."""

    terms = {term for term in re.findall(r"[a-z0-9_]+", query.lower()) if len(term) > 1}
    ranked: list[tuple[int, str]] = []
    for table_name in AGENT_TABLES[agent_name]:
        entry = SCHEMA_CATALOG[table_name]
        searchable = " ".join(
            (
                table_name,
                str(entry["purpose"]),
                " ".join(entry["columns"]),
                str(entry["keywords"]),
            )
        ).lower()
        score = sum(3 if term in table_name else 1 for term in terms if term in searchable)
        ranked.append((score, table_name))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected = [name for _, name in ranked[:top_k]]

    return {
        "agent": agent_name,
        "query": query,
        "tables": [
            {
                "name": name,
                "purpose": SCHEMA_CATALOG[name]["purpose"],
                "columns": SCHEMA_CATALOG[name]["columns"],
                "relationships": SCHEMA_CATALOG[name]["relationships"],
            }
            for name in selected
        ],
        "allowed_tables": sorted(AGENT_TABLES[agent_name]),
        "supported_entity_types": sorted(
            entity_type
            for entity_type, (_, _, agents) in ENTITY_FIELDS.items()
            if agent_name in agents and entity_type != "product"
        ),
        "rules": [
            "Use only returned table and column names.",
            "Do not select hidden personal or vector columns.",
            "Campaign ROI and conversion metrics describe the full campaign lifecycle.",
            "Fields marked synthetic or estimated must be labeled in the answer.",
        ],
    }


@tool(args_schema=ColumnDetailInput)
async def get_columns_detail(
    table_name: str,
    config: RunnableConfig,
) -> str:
    """Get one authorized table's column types, meanings, examples, and categories.

    Call only when a column's type, meaning, or allowed values are unclear before
    generating SQL; do not call it for every table.
    """

    configurable = config.get("configurable")
    agent_name = (
        configurable.get("agent_name")
        if isinstance(configurable, dict)
        else None
    )
    normalized_table = table_name.strip().lower()
    if agent_name not in AGENT_TABLES:
        return json.dumps(
            {
                "success": False,
                "tool": "get_columns_detail",
                "error_type": "missing_agent_scope",
                "error": "The current agent scope is unavailable.",
            },
            ensure_ascii=False,
        )
    if normalized_table not in AGENT_TABLES[agent_name]:
        return json.dumps(
            {
                "success": False,
                "agent": agent_name,
                "tool": "get_columns_detail",
                "error_type": "unauthorized_table",
                "error": f"{agent_name} is not authorized to inspect: {normalized_table}",
                "columns": {},
            },
            ensure_ascii=False,
        )
    details = COLUMN_DETAILS.get(normalized_table)
    if details is None:
        return json.dumps(
            {
                "success": False,
                "agent": agent_name,
                "tool": "get_columns_detail",
                "error_type": "column_details_unavailable",
                "error": f"No curated column details are available for: {normalized_table}",
                "columns": {},
            },
            ensure_ascii=False,
        )
    return json.dumps(
        {
            "success": True,
            "agent": agent_name,
            "tool": "get_columns_detail",
            "table_name": normalized_table,
            "columns": details,
        },
        ensure_ascii=False,
        default=str,
    )


def readonly_database_url() -> str:
    environment = load_environment_settings()
    database_url = environment.agent_readonly_database_url or environment.database_url
    if not database_url:
        raise RuntimeError(
            "AGENT_READONLY_DATABASE_URL or DATABASE_URL must be configured"
        )
    return database_url


def connect_readonly() -> psycopg.Connection:
    return psycopg.connect(
        readonly_database_url(),
        connect_timeout=_APPLICATION_SETTINGS.database.connect_timeout_seconds,
        prepare_threshold=None,
    )


def set_readonly_guards(cursor: psycopg.Cursor) -> None:
    cursor.execute("SET TRANSACTION READ ONLY")
    cursor.execute(
        "SELECT set_config('statement_timeout', %s, true)",
        (str(sql_timeout_ms()),),
    )


def _resolve_entity_sync(
    agent_name: SqlAgentName,
    entity_type: str,
    user_term: str,
    limit: int,
) -> dict[str, Any]:
    definition = ENTITY_FIELDS.get(entity_type)
    if definition is None or agent_name not in definition[2]:
        supported = sorted(
            name for name, (_, _, agents) in ENTITY_FIELDS.items() if agent_name in agents
        )
        return {
            "success": False,
            "entity_type": entity_type,
            "candidates": [],
            "error": f"Unsupported entity type. Use one of: {', '.join(supported)}",
        }

    table_name, column_name, _ = definition
    pattern = f"%{user_term.strip()}%"
    statement = psycopg_sql.SQL(
        "SELECT DISTINCT {column} AS value FROM {table} "
        "WHERE {column} IS NOT NULL AND {column} ILIKE %s "
        "ORDER BY CASE WHEN LOWER({column}) = LOWER(%s) THEN 0 "
        "WHEN LOWER({column}) LIKE LOWER(%s) THEN 1 ELSE 2 END, {column} LIMIT %s"
    ).format(
        column=psycopg_sql.Identifier(column_name),
        table=psycopg_sql.Identifier(table_name),
    )
    prefix_pattern = f"{user_term.strip()}%"
    with connect_readonly() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            set_readonly_guards(cursor)
            cursor.execute(statement, (pattern, user_term.strip(), prefix_pattern, limit))
            rows = cursor.fetchall()
    return {
        "success": True,
        "entity_type": entity_type,
        "user_term": user_term,
        "source": f"{table_name}.{column_name}",
        "candidates": [row["value"] for row in rows],
        "match_count": len(rows),
    }


def _execute_sql_sync(
    agent_name: SqlAgentName,
    query: str,
    parameters: dict[str, SqlParameter],
    purpose: str,
    maximum_rows: int,
    maximum_result_chars: int,
) -> dict[str, Any]:
    validated_sql, tables = validate_readonly_sql(query, parameters, agent_name)
    executable = (
        f"SELECT * FROM ({validated_sql}) AS agent_query "
        f"LIMIT {maximum_rows + 1}"
    )
    fingerprint = sha256(
        json.dumps(
            {"agent": agent_name, "sql": validated_sql, "parameters": parameters},
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()[:16]

    with connect_readonly() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            set_readonly_guards(cursor)
            cursor.execute(executable, parameters)
            raw_rows = cursor.fetchall()
            columns = [description.name for description in cursor.description or []]

    truncated = len(raw_rows) > maximum_rows
    rows: list[dict[str, Any]] = []
    result_chars = 0
    for raw_row in raw_rows[:maximum_rows]:
        row = _json_value(dict(raw_row))
        row_chars = len(json.dumps(row, ensure_ascii=False, default=str))
        if result_chars + row_chars > maximum_result_chars:
            truncated = True
            break
        rows.append(row)
        result_chars += row_chars
    citation = f"[db:{agent_name}:{fingerprint}]"
    source = {
        "type": "database_query",
        "filename": f"PostgreSQL · {', '.join(tables)}",
        "citation": citation,
        "query_id": fingerprint,
        "tables": tables,
        "row_count": len(rows),
    }
    return {
        "success": True,
        "agent": agent_name,
        "purpose": purpose,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "result_chars": result_chars,
        "truncated": truncated,
        "fetched_row_count": min(len(raw_rows), maximum_rows),
        "error": None,
        "sql": validated_sql,
        "parameters": parameters,
        "tables": tables,
        "citation": citation,
        "sources": [source],
    }


def _sql_runtime_state(config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        configurable = {}
        config["configurable"] = configurable
    runtime_state = configurable.get("sql_runtime_state")
    if not isinstance(runtime_state, dict):
        runtime_state = {
            "attempts": 0,
            "in_flight": False,
            "successful_queries": 0,
            "successful_rows": 0,
            "successful_result_chars": 0,
        }
        configurable["sql_runtime_state"] = runtime_state
    return runtime_state


def _claim_attempt(config: RunnableConfig) -> tuple[str, int]:
    runtime_state = _sql_runtime_state(config)
    attempts = int(runtime_state.get("attempts", 0))
    if runtime_state.get("approval_denied") is True:
        return "user_rejected", attempts
    if runtime_state.get("in_flight") is True:
        return "concurrent_query_blocked", attempts
    maximum = sql_max_attempts()
    if attempts >= maximum:
        return "attempt_limit", attempts
    runtime_state["attempts"] = attempts + 1
    runtime_state["in_flight"] = True
    return "permitted", attempts + 1


def _finish_attempt(
    config: RunnableConfig,
    *,
    success: bool,
    row_count: int = 0,
    result_chars: int = 0,
) -> None:
    runtime_state = _sql_runtime_state(config)
    runtime_state["in_flight"] = False
    if success:
        runtime_state["successful_queries"] = int(
            runtime_state.get("successful_queries", 0)
        ) + 1
        runtime_state["successful_rows"] = int(
            runtime_state.get("successful_rows", 0)
        ) + row_count
        runtime_state["successful_result_chars"] = int(
            runtime_state.get("successful_result_chars", 0)
        ) + result_chars


def _selected_skills(config: RunnableConfig) -> tuple[bool, tuple[str, ...]]:
    """Read progressive skill state without coupling to either loader."""

    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return False, ()
    state = configurable.get("skill_runtime_state")
    if not isinstance(state, dict):
        return False, ()
    loaded = state.get("loaded") is True
    selected = state.get("selected_skills")
    if not isinstance(selected, list):
        return loaded, ()
    return loaded, tuple(str(name) for name in selected)


def _generic_sql_block(
    agent_name: SqlAgentName,
    config: RunnableConfig,
    tool_name: str,
) -> str | None:
    loaded, selected = _selected_skills(config)
    if not loaded:
        return json.dumps(
            {
                "success": False,
                "agent": agent_name,
                "tool": tool_name,
                "error_type": "skill_not_loaded",
                "error": (
                    f"Load the {agent_name} sql_query skill before using generic "
                    "SQL tools."
                ),
                "retryable": True,
                "sources": [],
            },
            ensure_ascii=False,
        )
    if "sql_query" in selected:
        return None
    return json.dumps(
        {
            "success": False,
            "agent": agent_name,
            "tool": tool_name,
            "error_type": "generic_sql_skill_not_selected",
            "error": (
                f"Generic {agent_name.title()} SQL tools require an assigned "
                "sql_query subtask. Loaded dedicated skills do not authorize SQL."
            ),
            "selected_skills": list(selected),
            "retryable": False,
            "sources": [],
        },
        ensure_ascii=False,
    )


def build_sql_tools(
    agent_name: SqlAgentName,
) -> tuple[BaseTool, BaseTool, BaseTool, BaseTool]:
    """Build schema, detail, entity, and SQL tools with fixed domain permissions."""

    schema_description = (
        f"Find {agent_name}-authorized business tables, columns, relationships, "
        "and entity types before generating SQL for a generic structured-data "
        "task. Do not call this for a dedicated non-SQL skill."
    )

    @tool(
        f"search_{agent_name}_schema",
        args_schema=SchemaSearchInput,
        description=schema_description,
    )
    async def search_schema(
        query: str,
        config: RunnableConfig,
        top_k: int = _SQL_SETTINGS.schema_search_default_top_k,
    ) -> str:
        started_at = perf_counter()
        tool_name = f"search_{agent_name}_schema"
        blocked = _generic_sql_block(agent_name, config, tool_name)
        if blocked is not None:
            return blocked
        logger.tool_event(status="started", tool_name=tool_name, query_length=len(query))
        result = search_schema_catalog(agent_name, query, top_k)
        logger.tool_event(
            status="completed",
            tool_name=tool_name,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
            table_count=len(result["tables"]),
        )
        return json.dumps(result, ensure_ascii=False, default=str)

    @tool(
        f"resolve_{agent_name}_entity",
        args_schema=EntityResolutionInput,
        description=(
            f"Resolve a user term to real values in {agent_name}-authorized columns. "
            "Use it for stores, campaigns, customers, product categories, or other "
            "non-product-name categorical filters when spelling, aliases, or exact "
            "database values are uncertain. Never use this tool for a product name; "
            "product names must be resolved with find_real_name."
        ),
    )
    async def resolve_entity(
        entity_type: str,
        user_term: str,
        config: RunnableConfig,
        limit: int = _SQL_SETTINGS.entity_resolution_default_limit,
    ) -> str:
        started_at = perf_counter()
        tool_name = f"resolve_{agent_name}_entity"
        blocked = _generic_sql_block(agent_name, config, tool_name)
        if blocked is not None:
            return blocked
        if entity_type.strip().lower() == "product":
            return json.dumps(
                {
                    "success": False,
                    "agent": agent_name,
                    "tool": tool_name,
                    "error_type": "product_resolver_required",
                    "error": (
                        "Product names must be resolved with find_real_name. "
                        "Do not use the general entity resolver for products."
                    ),
                    "retryable": False,
                    "candidates": [],
                    "sources": [],
                },
                ensure_ascii=False,
            )
        logger.tool_event(
            status="started",
            tool_name=tool_name,
            entity_type=entity_type,
            term_length=len(user_term),
        )
        try:
            result = await asyncio.to_thread(
                _resolve_entity_sync,
                agent_name,
                entity_type,
                user_term,
                limit,
            )
        except Exception as error:
            logger.exception("tool.failed", error, component="tool", tool_name=tool_name)
            return json.dumps(
                {
                    "success": False,
                    "entity_type": entity_type,
                    "candidates": [],
                    "error_type": "database_error",
                    "error": "Entity lookup could not reach the read-only database.",
                },
                ensure_ascii=False,
            )
        logger.tool_event(
            status="completed",
            tool_name=tool_name,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
            match_count=result.get("match_count", 0),
        )
        return json.dumps(result, ensure_ascii=False, default=str)

    @tool(
        f"execute_{agent_name}_sql",
        args_schema=ReadonlySqlInput,
        description=(
            f"Validate and execute one parameterized, read-only PostgreSQL SELECT for "
            f"the {agent_name} domain. It enforces a table whitelist, read-only transaction, "
            "timeout, row cap, and at most "
            f"{_SQL_SETTINGS.max_attempts_per_subtask} attempts."
        ),
    )
    async def execute_sql(
        sql: str,
        purpose: str,
        config: RunnableConfig,
        parameters: dict[str, SqlParameter] | None = None,
    ) -> str:
        started_at = perf_counter()
        tool_name = f"execute_{agent_name}_sql"
        blocked = _generic_sql_block(agent_name, config, tool_name)
        if blocked is not None:
            return blocked
        claim_status, attempt = _claim_attempt(config)
        if claim_status != "permitted":
            if claim_status == "concurrent_query_blocked":
                error = "Another SQL query is already running; parallel SQL calls are not allowed."
            elif claim_status == "user_rejected":
                error = (
                    "The user already rejected generated SQL for this task; "
                    "no database query may be executed."
                )
            else:
                error = f"The maximum of {sql_max_attempts()} SQL attempts was reached."
            return json.dumps(
                {
                    "success": False,
                    "agent": agent_name,
                    "error_type": claim_status,
                    "error": error,
                    "retryable": False,
                    "sources": [],
                },
                ensure_ascii=False,
            )
        actual_parameters = parameters or {}
        runtime_state = _sql_runtime_state(config)
        remaining_rows = sql_max_rows() - int(runtime_state.get("successful_rows", 0))
        remaining_result_chars = sql_max_result_chars() - int(
            runtime_state.get("successful_result_chars", 0)
        )
        if remaining_rows <= 0 or remaining_result_chars <= 0:
            _finish_attempt(config, success=False)
            return json.dumps(
                {
                    "success": False,
                    "agent": agent_name,
                    "error_type": "result_limit",
                    "error": (
                        "The cumulative successful SQL result limit was reached; "
                        "no additional rows can be returned."
                    ),
                    "retryable": False,
                    "sources": [],
                },
                ensure_ascii=False,
            )
        logger.tool_event(
            status="started",
            tool_name=tool_name,
            attempt=attempt,
            sql_length=len(sql),
            parameter_count=len(actual_parameters),
        )
        logger.info(
            "sql.generated",
            component="tool",
            tool_name=tool_name,
            attempt=attempt,
            agent_name=agent_name,
            sql=sql,
        )
        try:
            validated_sql, tables = validate_readonly_sql(
                sql,
                actual_parameters,
                agent_name,
            )
        except SqlValidationError as error:
            result = {
                "success": False,
                "error_type": "validation_error",
                "validation_error_type": error.validation_error_type,
                "error": str(error),
                "retryable": attempt < sql_max_attempts(),
                "sources": [],
            }
            _finish_attempt(config, success=False)
            result.setdefault("agent", agent_name)
            logger.tool_event(
                status="completed",
                tool_name=tool_name,
                duration_ms=round((perf_counter() - started_at) * 1000, 2),
                attempt=attempt,
                success=False,
                error_type="validation_error",
                validation_error_type=error.validation_error_type,
                validation_error=str(error),
            )
            return json.dumps(result, ensure_ascii=False, default=str)

        configurable = config.get("configurable")
        run_id = (
            str(configurable.get("run_id") or "")
            if isinstance(configurable, dict)
            else ""
        )
        auto_execute_sql = (
            bool(configurable.get("auto_execute_sql"))
            if isinstance(configurable, dict)
            else False
        )
        executable_sql = (
            f"SELECT * FROM ({validated_sql}) AS agent_query "
            f"LIMIT {remaining_rows + 1}"
        )
        if auto_execute_sql:
            logger.info(
                "sql.auto_execute",
                component="tool",
                tool_name=tool_name,
                attempt=attempt,
                agent_name=agent_name,
            )
            try:
                await adispatch_custom_event(
                    "sql_auto_execute",
                    {
                        "run_id": run_id,
                        "agent": agent_name,
                        "purpose": purpose,
                        "tables": tables,
                        "message": (
                            "Automatic SQL execution is enabled. The validated "
                            "read-only query is running without an approval prompt."
                        ),
                    },
                    config=config,
                )
            except asyncio.CancelledError:
                _finish_attempt(config, success=False)
                raise
            except Exception as error:
                logger.warning(
                    "sql.auto_execute_event_failed",
                    component="tool",
                    tool_name=tool_name,
                    error_type=type(error).__name__,
                )
        else:
            pending = await sql_approval_manager.create(
                run_id=run_id,
                agent_name=agent_name,
            )
            approval_wait = asyncio.create_task(sql_approval_manager.wait(pending))
            try:
                await adispatch_custom_event(
                    "sql_approval",
                    {
                        "approval_id": pending.approval_id,
                        "run_id": run_id,
                        "agent": agent_name,
                        "purpose": purpose,
                        "sql": executable_sql,
                        "generated_sql": validated_sql,
                        "parameters": actual_parameters,
                        "tables": tables,
                        "message": (
                            "No dedicated skill matched this request. The Agent is ready "
                            "to run the following read-only query. It may fail, take a "
                            "long time, or consume additional tokens. Do you want to execute it?"
                        ),
                    },
                    config=config,
                )
            except asyncio.CancelledError:
                approval_wait.cancel()
                try:
                    await approval_wait
                except asyncio.CancelledError:
                    pass
                _finish_attempt(config, success=False)
                raise
            except Exception:
                approval_wait.cancel()
                try:
                    await approval_wait
                except (asyncio.CancelledError, TimeoutError):
                    pass
                _finish_attempt(config, success=False)
                raise

            try:
                decision = await approval_wait
            except TimeoutError:
                decision = "cancel"
                approval_error_type = "approval_timeout"
            except asyncio.CancelledError:
                _finish_attempt(config, success=False)
                raise
            else:
                approval_error_type = "user_rejected"

            if decision != "execute":
                runtime_state["approval_denied"] = True
                _finish_attempt(config, success=False)
                result = {
                    "success": False,
                    "agent": agent_name,
                    "error_type": approval_error_type,
                    "error": (
                        "SQL approval timed out; the database query was not executed."
                        if approval_error_type == "approval_timeout"
                        else "The user rejected the generated SQL; the database query was not executed."
                    ),
                    "retryable": False,
                    "sql": validated_sql,
                    "parameters": actual_parameters,
                    "sources": [],
                }
                logger.tool_event(
                    status="completed",
                    tool_name=tool_name,
                    duration_ms=round((perf_counter() - started_at) * 1000, 2),
                    attempt=attempt,
                    success=False,
                    error_type=approval_error_type,
                )
                return json.dumps(result, ensure_ascii=False, default=str)

        try:
            result = await asyncio.to_thread(
                _execute_sql_sync,
                agent_name,
                sql,
                actual_parameters,
                purpose,
                remaining_rows,
                remaining_result_chars,
            )
        except SqlValidationError as error:
            result = {
                "success": False,
                "error_type": "validation_error",
                "validation_error_type": error.validation_error_type,
                "error": str(error),
                "retryable": attempt < sql_max_attempts(),
                "sources": [],
            }
        except psycopg.OperationalError:
            result = {
                "success": False,
                "error_type": "database_error",
                "error": "The read-only database connection is unavailable.",
                "retryable": False,
                "sources": [],
            }
        except psycopg.Error as error:
            primary_message = getattr(error.diag, "message_primary", None)
            result = {
                "success": False,
                "error_type": "sql_error",
                "sqlstate": error.sqlstate,
                "error": primary_message or type(error).__name__,
                "retryable": attempt < sql_max_attempts(),
                "sources": [],
            }
        except Exception as error:
            logger.exception("tool.failed", error, component="tool", tool_name=tool_name)
            result = {
                "success": False,
                "error_type": "database_error",
                "error": "The read-only database query could not be completed.",
                "retryable": False,
                "sources": [],
            }
        _finish_attempt(
            config,
            success=result.get("success") is True,
            row_count=int(result.get("row_count") or 0),
            result_chars=int(result.get("result_chars") or 0),
        )
        result.setdefault("agent", agent_name)
        logger.tool_event(
            status="completed",
            tool_name=tool_name,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
            attempt=attempt,
            success=result.get("success", False),
            row_count=result.get("row_count", 0),
            error_type=result.get("error_type"),
            validation_error_type=result.get("validation_error_type"),
            validation_error=(
                result.get("error")
                if result.get("error_type") == "validation_error"
                else None
            ),
        )
        return json.dumps(result, ensure_ascii=False, default=str)

    return search_schema, resolve_entity, execute_sql, get_columns_detail


__all__ = [
    "ColumnDetailInput",
    "connect_readonly",
    "EntityResolutionInput",
    "ReadonlySqlInput",
    "SchemaSearchInput",
    "SqlValidationError",
    "ValidationErrorType",
    "build_sql_tools",
    "get_columns_detail",
    "search_schema_catalog",
    "set_readonly_guards",
    "validate_readonly_sql",
]
