# Skill: Finance SQL Query

## Use this skill for

Revenue, refunds by value, campaign spend or ROI, attributed revenue, costs,
gross profit, gross margin, expenses, and estimated operating profit.

## Do not use this skill for

Policy interpretation, inventory diagnosis, review themes, service root causes,
or operational recommendations.

## Procedure

1. Identify the financial metric and its governed source.
2. Identify the requested period, comparison period, dimensions, and filters.
3. Retrieve only relevant Finance schema.
4. Resolve business entities before exact filtering when needed.
5. Prefer governed profitability views for their defined calculations.
6. Generate parameterized SQL at the requested grain.
7. Execute through the Finance SQL tool and verify totals, units, and row count.
8. Mark lifecycle campaign metrics, attribution, synthetic costs, refunds, and
   expenses accurately.
9. Provide the result, citation, final SQL, parameters, and visible limitations.

## Positive example

For "Which campaign delivered the highest return?", interpret return as reported
ROI unless the task says otherwise, retrieve campaign schema, rank `roi` descending
with deterministic tie breakers, and disclose that ROI is a lifecycle metric.

## Negative example

Do not infer that a campaign caused all attributed sales. Attribution is an
association in this dataset and must be labeled synthetic.
