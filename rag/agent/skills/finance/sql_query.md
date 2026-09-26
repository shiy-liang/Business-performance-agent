# Skill: Finance SQL Query

## Use this skill for

Finance questions not covered by a dedicated skill, including gross sales,
refund analysis by value or status, campaign spend or ROI, attributed revenue,
expenses, estimated operating profit, and custom financial breakdowns or
rankings.

Assign this skill to an atomic structured-data subtask only when no dedicated
Finance skill covers that subtask. It may coexist with dedicated skills in the
same task packet when they own different subtasks.

## Do not use this skill for

Policy interpretation, inventory diagnosis, review themes, service root causes,
operational recommendations, the dedicated net-sales total, or the dedicated
gross-profit and gross-margin calculations. Never use SQL to verify, enrich, or
retry a subtask assigned to those dedicated skills. Do not use it to manufacture a
forecast, prediction, projection, budget, or future-period estimate from recorded
transactions.

## Procedure

1. Identify the financial metric and its governed source.
2. Identify the requested period, comparison period, dimensions, and filters.
3. If the query involves a product name, first call `find_real_name` to obtain
   the exact canonical name. Use only a name returned in `items`. Once it returns
   `result_status=matched`, do not call `find_real_name` again for this task.
4. Retrieve only relevant Finance schema.
5. If a column's type, meaning, or allowed values are unclear, call
   `get_columns_detail` for its table before generating SQL.
6. Resolve non-product business entities before exact filtering when needed.
   Product names must use `find_real_name`, not the general entity resolver.
7. Prefer governed profitability views for their defined calculations.
8. Generate parameterized SQL at the requested grain.
9. Execute through the Finance SQL tool and verify totals, units, and row count.
10. Mark lifecycle campaign metrics, attribution, synthetic costs, refunds, and
   expenses accurately.
11. Provide the result, citation, final SQL, parameters, and visible limitations.

## Positive example

For "Which campaign delivered the highest return?", interpret return as reported
ROI unless the task says otherwise, retrieve campaign schema, rank `roi` descending
with deterministic tie breakers, and disclose that ROI is a lifecycle metric.

## Negative example

Do not infer that a campaign caused all attributed sales. Attribution is an
association in this dataset and must be labeled synthetic.
