# Skill: Support Ticket Problem Retrieval

## Trigger

Use this skill only when the delegated task requires semantic understanding of
the concrete problem description stored in support-ticket `notes`, such as what
payment failures customers encountered, what happened in specific incidents, or
what reasons customers described. Do not use it for structured ticket counts,
priority/status breakdowns, resolution times, satisfaction metrics, or other
questions answerable from ordinary columns.

## Dedicated workflow

1. Call `check_concrete_problem` exactly once. Do not retrieve schema, resolve an
   entity, generate SQL, or call `execute_operations_sql` for this workflow.
2. Put the requested concrete issue and business context in `query`. Preserve
   explicit payment methods, symptoms, dates, products, channels, or failure
   descriptions from the delegated task.
3. Apply `start_date`, `end_date`, `issue_category`, `priority`, or
   `resolution_status` only when the task explicitly provides that restriction or
   an exact canonical value. Do not guess a structured filter; semantic concepts
   belong in `query`.
4. Use the returned `ticket_id`, `customer_id`, `issue_category`, `priority`,
   dates, resolution fields, satisfaction score, and `notes` to produce a compact
   evidence summary. Cite every concrete example with its exact `[ticket:...]`
   citation.
5. Stop after the Tool result. Do not repeat the Tool and do not use generic SQL
   as a second route for the same concrete-description request.

## Interpretation

- Retrieved tickets are semantically relevant examples, not a complete issue
  distribution. Do not infer totals, percentages, frequency, prevalence, or a
  "most common" problem from the sample.
- Treat reasons mentioned in `notes` as customer-reported or ticket-recorded
  descriptions, not proven root causes.
- Clearly distinguish unresolved, resolved, and missing resolution data.
- If no ticket matches, report that retrieval result without inventing examples.
