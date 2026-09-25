# Skill: Net Sales

## Trigger

Use this skill when the task asks for net sales, refund-adjusted sales, or sales
after discounts and completed refunds as one aggregate for the full dataset or a
specified scope. Use the generic SQL skill for grouped breakdowns, rankings, or
time series.

## Dedicated workflow

1. Call `calculate_net_sales` exactly once. Do not retrieve schema, generate SQL,
   or call `execute_finance_sql` for this calculation.
2. Use `start_date` as an inclusive transaction-date bound and `end_date` as an
   exclusive bound. Leave both empty when no period is supplied; do not invent a
   period.
3. Pass product, category, store, or payment-method filters only when explicitly
   requested. If a product name is fuzzy or non-standard, resolve it with
   `find_real_name` first and use only an exact returned name.
4. Report `net_sales` together with the returned `net_sales_before_refunds`,
   `completed_refunds`, and transaction count. Preserve the exact database
   citation.
5. Stop after the Tool result. Do not repeat the Tool or use generic SQL as a
   second route for the same metric.

## Metric definition

`net_sales = SUM(transactions.net_sales) - SUM(completed refund_amount)`.
`transactions.net_sales` is already after discounts. Only rows whose
`returns_refunds.refund_status` is `completed` reduce net sales. The requested
period is based on the original transaction date, not the later return date.

## Interpretation

- Currency is unspecified unless the delegated task supplies one.
- Refund fields are synthetic in this dataset; disclose that limitation.
- Requested, pending, or failed refunds do not reduce this metric.
