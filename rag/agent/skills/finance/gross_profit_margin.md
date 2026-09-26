# Skill: Gross Profit and Gross Margin

## Trigger

Use this skill when the task asks to query or calculate gross profit or gross
margin from transactions already recorded in the database, either for the full
dataset or one specified scope. Do not use it for a forecast, prediction,
projection, budget, future period, or any forward-looking result. This workflow
calculates recorded-data metrics; it does not predict them.
Use generic SQL for grouped breakdowns, rankings, comparisons, or time series.

## Dedicated workflow

1. For gross-profit amount only, call `calculate_gross_profit` exactly once.
2. For gross-margin percentage, call `calculate_gross_margin` exactly once. Its
   result also contains the supporting gross-profit amount, so use this Tool alone
   when both profit and margin are requested.
3. Do not retrieve schema, generate SQL, or call `execute_finance_sql` for either
   calculation.
4. Use `start_date` as an inclusive transaction-date bound and `end_date` as an
   exclusive bound. Leave both empty when no period is supplied.
5. Apply product, category, store, or payment-method filters only when explicitly
   requested. Resolve a fuzzy product through `find_real_name` first.
6. Report the requested metric together with `cost_of_goods_sold`,
   `costed_recognized_revenue`, and `cost_coverage_percent`. If reporting margin,
   use the exact returned `gross_margin_percent`; do not calculate another ratio
   in the model.
7. Preserve the returned database citation and stop. Do not repeat the Tool or
   reconstruct the calculation with generic SQL.

## Metric definitions

The Tools join `transactions` to completed `returns_refunds` and `products`.
For transactions with a matched product cost:

`gross_profit = refund-adjusted net sales - quantity × unit_cost`.

`gross_margin_percent = gross_profit / costed recognized revenue × 100`.

Revenue without a matched `products.unit_cost` is excluded from both metrics and
reported through cost coverage. Completed refunds reduce revenue; cost of goods
sold remains the full original transaction quantity, matching the project's
governed profitability definition.

## Interpretation

- These are calculations over recorded transactions, not forecasts.
- Product cost can be synthetic; disclose that limitation without describing the
  calculation as a prediction.
- Currency is unspecified unless supplied by the delegated task.
- The period follows transaction date, not return date.
