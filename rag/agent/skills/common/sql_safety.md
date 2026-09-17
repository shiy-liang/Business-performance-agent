# Skill: SQL Safety

## Purpose

Generate useful PostgreSQL queries without giving the model direct database
access or write capability.

## Mandatory sequence

1. Retrieve the agent-scoped schema.
2. Resolve uncertain entity values when required.
3. Generate one explicit-column `SELECT` statement.
4. Submit the query to the agent-scoped execution tool.
5. Distinguish validation errors, SQL errors, empty results, and successful data.
6. Correct only from concrete schema or error evidence, with no more than three
   execution attempts.
7. Return only the final successful query and its database citation.

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
