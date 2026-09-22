# Finance Result Contract

Return concise Markdown for the Supervisor with these elements:

1. `Finding`: the direct financial result with period and scope.
2. `Supporting metrics`: only the rows or comparisons necessary to substantiate
   the finding.
3. `Interpretation`: metric definition and any default applied.
4. `Limitations`: synthetic, estimated, attributed, incomplete, empty, or stale
   data warnings.
5. `Evidence`: the exact database citation returned by the successful SQL tool.
6. `Final SQL`: include the successful SQL and parameter values only when the
   delegated task explicitly requests SQL or audit detail. Otherwise omit it to
   keep the Supervisor context compact. Never include failed attempts.

If evidence is unavailable, state that clearly and identify the failed step. Do
not return JSON and do not write a user-facing executive narrative.
