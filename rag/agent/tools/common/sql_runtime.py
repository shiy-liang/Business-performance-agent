"""Safe schema discovery, entity resolution, and read-only SQL execution."""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from time import perf_counter
from typing import Any, Literal

import psycopg
import sqlglot
from dotenv import load_dotenv
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from psycopg import sql as psycopg_sql
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator
from sqlglot import exp

from model.config import PROJECT_ROOT
from observability import logger
from rag.agent.tools.common.schema_catalog import (
    AGENT_TABLES,
    ENTITY_FIELDS,
    PROHIBITED_COLUMNS,
    SCHEMA_CATALOG,
    SqlAgentName,
)


load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_MAX_ROWS = 500
DEFAULT_MAX_RESULT_CHARS = 30000
DEFAULT_TIMEOUT_MS = 5000
DEFAULT_MAX_ATTEMPTS = 3
PARAMETER_PATTERN = re.compile(r"%\(([A-Za-z_][A-Za-z0-9_]*)\)s")


def _positive_env(name: str, default: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if 0 < value <= maximum else default


def sql_max_rows() -> int:
    return _positive_env("AGENT_SQL_MAX_ROWS", DEFAULT_MAX_ROWS, 5000)


def sql_timeout_ms() -> int:
    return _positive_env("AGENT_SQL_TIMEOUT_MS", DEFAULT_TIMEOUT_MS, 30000)


def sql_max_result_chars() -> int:
    return _positive_env(
        "AGENT_SQL_MAX_RESULT_CHARS",
        DEFAULT_MAX_RESULT_CHARS,
        200000,
    )


def sql_max_attempts() -> int:
    return _positive_env("AGENT_SQL_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS, 5)


class SchemaSearchInput(BaseModel):
    query: str = Field(
        min_length=2,
        max_length=500,
        description="An English schema-search phrase containing the required metrics, entities, and filters.",
    )
    top_k: int = Field(default=6, ge=1, le=8)


class EntityResolutionInput(BaseModel):
    entity_type: str = Field(
        min_length=2,
        max_length=40,
        description="One supported entity type returned by the schema tool.",
    )
    user_term: str = Field(
        min_length=1,
        max_length=120,
        description="The user's entity phrase or a careful translated candidate.",
    )
    limit: int = Field(default=8, ge=1, le=10)


SqlParameter = str | int | float | bool | None


class ReadonlySqlInput(BaseModel):
    sql: str = Field(
        min_length=8,
        max_length=12000,
        description="One PostgreSQL SELECT query using only schema returned by the schema tool.",
    )
    parameters: dict[str, SqlParameter] = Field(
        default_factory=dict,
        description="Values for psycopg named placeholders such as %(period_start)s.",
    )
    purpose: str = Field(
        min_length=3,
        max_length=300,
        description="A short public explanation of what this query measures.",
    )

    @field_validator("parameters")
    @classmethod
    def validate_parameter_count(
        cls, value: dict[str, SqlParameter]
    ) -> dict[str, SqlParameter]:
        if len(value) > 30:
            raise ValueError("No more than 30 SQL parameters are allowed")
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
    if isinstance(value, str) and len(value) > 4000:
        return value[:4000] + "… [truncated]"
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
            if agent_name in agents
        ),
        "rules": [
            "Use only returned table and column names.",
            "Do not select hidden personal or vector columns.",
            "Campaign ROI and conversion metrics describe the full campaign lifecycle.",
            "Fields marked synthetic or estimated must be labeled in the answer.",
        ],
    }


def readonly_database_url() -> str:
    database_url = (
        os.getenv("AGENT_READONLY_DATABASE_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )
    if not database_url:
        raise RuntimeError(
            "AGENT_READONLY_DATABASE_URL or DATABASE_URL must be configured"
        )
    return database_url


def connect_readonly() -> psycopg.Connection:
    return psycopg.connect(
        readonly_database_url(),
        connect_timeout=5,
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
) -> dict[str, Any]:
    validated_sql, tables = validate_readonly_sql(query, parameters, agent_name)
    maximum_rows = sql_max_rows()
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
        if rows and result_chars + row_chars > sql_max_result_chars():
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
        runtime_state = {"attempts": 0, "in_flight": False, "succeeded": False}
        configurable["sql_runtime_state"] = runtime_state
    return runtime_state


def _claim_attempt(config: RunnableConfig) -> tuple[str, int]:
    runtime_state = _sql_runtime_state(config)
    attempts = int(runtime_state.get("attempts", 0))
    if runtime_state.get("succeeded") is True:
        return "already_succeeded", attempts
    if runtime_state.get("in_flight") is True:
        return "concurrent_query_blocked", attempts
    maximum = sql_max_attempts()
    if attempts >= maximum:
        return "attempt_limit", attempts
    runtime_state["attempts"] = attempts + 1
    runtime_state["in_flight"] = True
    return "permitted", attempts + 1


def _finish_attempt(config: RunnableConfig, *, success: bool) -> None:
    runtime_state = _sql_runtime_state(config)
    runtime_state["in_flight"] = False
    if success:
        runtime_state["succeeded"] = True


def build_sql_tools(agent_name: SqlAgentName) -> tuple[BaseTool, BaseTool, BaseTool]:
    """Build three tools whose domain permission cannot be changed by the model."""

    schema_description = (
        "Find operations-authorized business tables, columns, relationships, and "
        "entity types before generating SQL for a generic structured-data task. "
        "Do not call this for a dedicated non-SQL skill."
        if agent_name == "operations"
        else "Find finance-authorized business tables, columns, relationships, and "
        "entity types before generating SQL. Call this first for every Finance task."
    )

    @tool(
        f"search_{agent_name}_schema",
        args_schema=SchemaSearchInput,
        description=schema_description,
    )
    async def search_schema(query: str, top_k: int = 6) -> str:
        started_at = perf_counter()
        tool_name = f"search_{agent_name}_schema"
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
            "Use it for products, stores, campaigns, customers, or categorical filters "
            "when spelling, aliases, or exact database values are uncertain."
        ),
    )
    async def resolve_entity(
        entity_type: str,
        user_term: str,
        limit: int = 8,
    ) -> str:
        started_at = perf_counter()
        tool_name = f"resolve_{agent_name}_entity"
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
            "timeout, row cap, and at most three attempts."
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
        claim_status, attempt = _claim_attempt(config)
        if claim_status != "permitted":
            if claim_status == "already_succeeded":
                error = "A successful SQL result already exists; use it to complete the analysis."
            elif claim_status == "concurrent_query_blocked":
                error = "Another SQL query is already running; parallel SQL calls are not allowed."
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
            result = await asyncio.to_thread(
                _execute_sql_sync,
                agent_name,
                sql,
                actual_parameters,
                purpose,
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
        _finish_attempt(config, success=result.get("success") is True)
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

    return search_schema, resolve_entity, execute_sql


__all__ = [
    "connect_readonly",
    "EntityResolutionInput",
    "ReadonlySqlInput",
    "SchemaSearchInput",
    "SqlValidationError",
    "ValidationErrorType",
    "build_sql_tools",
    "search_schema_catalog",
    "set_readonly_guards",
    "validate_readonly_sql",
]
