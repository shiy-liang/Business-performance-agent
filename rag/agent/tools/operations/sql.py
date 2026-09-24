"""Operations-scoped instances of the shared SQL tools."""

from rag.agent.tools.common.sql_runtime import build_sql_tools


(
    search_operations_schema,
    resolve_operations_entity,
    execute_operations_sql,
    get_columns_detail,
) = build_sql_tools("operations")


__all__ = [
    "execute_operations_sql",
    "get_columns_detail",
    "resolve_operations_entity",
    "search_operations_schema",
]
