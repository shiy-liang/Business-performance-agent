# Skill: SQL Safety

## Purpose

Generate useful PostgreSQL queries without giving the model direct database
access or write capability.

Apply this skill only after the Agent has selected the generic SQL workflow. If
another injected skill defines a dedicated non-SQL workflow for the task, follow
that dedicated skill and do not run the mandatory SQL sequence below.

## Mandatory sequence

1. If a product name is fuzzy, non-standard, or cross-language, resolve it with
   `find_real_name` and use only returned exact database values.
2. Retrieve the agent-scoped schema.
3. Resolve other uncertain entity values when required.
4. Generate one explicit-column `SELECT` statement.
5. Submit the query to the agent-scoped execution tool.
   Submit exactly one SQL call at a time. Never issue parallel alternatives.
6. Distinguish validation errors, SQL errors, empty results, and successful data.
7. Correct only from concrete schema or error evidence, with no more than three
   execution attempts.
8. Return only the final successful query and its database citation.
9. Stop SQL execution after the cumulative result limits are reached. You may run
   at most three sequential queries when separate evidence is necessary; the
   successful rows and result characters across all queries must stay within the
   configured limits. Do not issue parallel alternatives or optional extra queries.

## Query rules

- Use named parameters for user terms, dates, limits, and categorical values.
- Use half-open date ranges: `date >= start` and `date < end`.
- Never use `SELECT *`.
- Add deterministic tie breakers to rankings.
- For highest, lowest, top, or bottom questions, return only the requested Top N;
  use `LIMIT 1` when the user asks for a single winner.
- Aggregate in SQL instead of returning raw rows for the model to calculate.
- Prevent fan-out joins from multiplying transaction, refund, attribution, or
  inventory facts.
- Use `NULLIF` for divisions and make null handling explicit.
- Do not query system schemas, hidden vector columns, or personal contact fields.
- Never produce DDL, DML, COPY, transaction control, locking reads, or multiple
  statements.

## Failure behavior

- Validation error: fix only the stated policy violation.
- Missing table or column: return to retrieved schema and correct the identifier.
- Empty rows: inspect entities, dates, statuses, and filter strictness.
- Timeout: simplify the query or reduce the time range; do not remove safety caps.
- Attempt limit or database outage: stop and report insufficient evidence.
