# Operations Evidence Summary Contract

Return a compact evidence packet for the Supervisor, not a complete user-facing
answer. Repeat this exact structure once for every assigned subtask, in the
original order:

```markdown
### Subtask <id> — <completed|blocked|empty>
- Skill: `<assigned skill>`
- Finding: <direct result, or why no result is available>
- Evidence: <compact facts with exact citations, or "None">
- Limitations: <material limitations, or "None">
```

Rules:

- Use at most six Evidence bullets and keep each bullet factual and compact.
- Do not add an executive introduction, conclusion, recommendation, greeting, or
  rhetorical transition. The Supervisor alone writes the user-facing narrative.
- Include every assigned subtask ID exactly once. Do not omit one because another
  subtask succeeded, and do not add unassigned work.
- The heading status must exactly match the terminal status accepted by
  `update_sub_task_status`; do not reconstruct or rename a status in final text.
- For a generic SQL task, use the exact database citation returned by the
  successful SQL tool.
- For a product-review subtask, use exact `[review:...]` citations returned by
  the review tools. Generic SQL evidence is not allowed for that subtask.
- For a support-ticket problem retrieval subtask, use exact `[ticket:...]`
  citations returned by `check_concrete_problem`. Describe reasons as reported in
  ticket notes rather than proven root causes, and do not infer frequency from the
  retrieved examples.
- For a dedicated product purchase-rate task, use the exact
  `[db:operations:...]` citation returned by `check_purchase_rate`.
- For a dedicated product like-rate task, use the exact `[db:operations:...]`
  citation returned by `check_like_rate`.
- For dedicated Bottom-10 rate tasks, preserve the Tool's product ordering and
  include each returned rate beside its product. Its database citation is
  propagated separately as internal evidence.
- For the dedicated interaction-duration ranking, preserve the Tool's product
  ordering and include its returned durations, counts, and rank fields. Its
  database citation is propagated separately as internal evidence.
- Do not infer population-level counts, averages, percentages, or prevalence from
  retrieved review samples.
- Include final SQL and parameter values only if the delegated task explicitly
  requests audit details. Never include failed attempts.
- If evidence is unavailable, state the failed step under Limitations without
  guessing.
- If generated SQL was rejected by the user or approval timed out, state that the
  query was not executed and do not retry it.
