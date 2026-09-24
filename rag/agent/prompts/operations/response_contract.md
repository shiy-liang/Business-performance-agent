# Operations Evidence Summary Contract

Return a compact evidence packet for the Supervisor, not a complete user-facing
answer. Use this exact Markdown structure:

```markdown
### Scope
- <resolved scope, filters, and period>

### Evidence
- <short factual observation> <exact citation>

### Limitations
- <only material limitations, or "None">
```

Rules:

- Use at most six Evidence bullets and keep each bullet factual and compact.
- Do not add an executive introduction, conclusion, recommendation, greeting, or
  rhetorical transition. The Supervisor alone writes the user-facing narrative.
- When multiple dedicated workflows were selected, include compact evidence or an
  explicit limitation for each selected requirement. Do not omit one merely
  because another workflow succeeded.
- For a generic SQL task, use the exact database citation returned by the
  successful SQL tool.
- For a product-review workflow, use exact `[review:...]` citations returned by
  the review tools. Generic SQL evidence is neither required nor allowed; evidence
  from another selected dedicated workflow is allowed.
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
