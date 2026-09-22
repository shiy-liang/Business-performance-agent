# Operations Result Contract

Return concise Markdown for the Supervisor with these elements:

1. `Finding`: the direct operational result with period and scope.
2. `Supporting metrics`: only the rows or comparisons required for the finding.
3. `Interpretation`: aggregation grain, filters, entity resolution, and defaults.
4. `Limitations`: synthetic data, snapshot constraints, truncation, empty results,
   or correlation warnings.
5. `Evidence`: the exact database citation returned by the successful SQL tool.
   Include exact `[review:...]` citations when semantic review evidence was used.
6. `Final SQL`: include the successful SQL and parameter values only when the
   delegated task explicitly requests SQL or audit detail. Otherwise omit it to
   keep the Supervisor context compact. Never include failed attempts.

If evidence is unavailable, state that clearly and identify the failed step. Do
not return JSON and do not write a user-facing executive narrative.
