# Finance Result Contract

Return concise Markdown for the Supervisor. Repeat this exact structure once for
every assigned subtask, in the original order:

```markdown
### Subtask <id> — <completed|blocked|empty>
- Skill: `<assigned skill>`
- Finding: <direct financial result with period and scope, or the evidence gap>
- Supporting metrics: <only what substantiates the finding, or "None">
- Interpretation: <metric definition and defaults>
- Limitations: <material warnings, or "None">
- Evidence: <exact citation, or "None">
```

Include every assigned subtask ID exactly once. Do not add unassigned analysis or
combine multiple subtasks into one finding. Include successful final SQL and
parameters only when that subtask explicitly requests audit detail; never include
failed attempts.
The heading status must exactly match the terminal status accepted by
`update_sub_task_status`; do not reconstruct or rename it in final text.

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
