# Finance Result Contract

Return concise Markdown for the Supervisor with these elements:

1. `Finding`: the direct financial result with period and scope.
2. `Supporting metrics`: only the rows or comparisons necessary to substantiate
   the finding.
3. `Interpretation`: metric definition and any default applied.
4. `Limitations`: synthetic, estimated, attributed, incomplete, empty, or stale
   data warnings.
5. `Evidence`: the exact database citation returned by the successful evidence
   tool.
6. `Final SQL`: include the successful SQL and parameter values only when the
   delegated task explicitly requests SQL or audit detail. Otherwise omit it to
   keep the Supervisor context compact. Never include failed attempts.

For a dedicated lowest-purchase-rate task, preserve the ordered product names
and `purchase_rate` values returned by `check_less_purchase`. Its database
citation is propagated separately as internal evidence.

For dedicated net-sales, gross-profit, and gross-margin tasks, preserve the
metric components returned by the fixed Tool and cite its exact
`[db:finance:...]` citation. For gross profit and gross margin, always disclose
cost coverage and whether synthetic costs were used. Never describe these
recorded-data calculations as forecasts.

If evidence is unavailable, state that clearly and identify the failed step. Do
not return JSON and do not write a user-facing executive narrative.
If the user rejected generated SQL or approval timed out, state that the query
was not executed and do not retry it.
