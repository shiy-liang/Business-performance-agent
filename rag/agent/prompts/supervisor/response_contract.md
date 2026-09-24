# Supervisor Response Contract

Use the smallest structure that completely answers the question.

For a rule or knowledge question:

1. Give the direct answer.
2. Show the relevant rule or threshold breakdown.
3. Add one short operational implication only when useful.
4. Keep knowledge citations next to supported claims.

For a structured-data question:

1. Lead with the direct answer, metric, period, and scope.
2. State material interpretation choices, such as treating "return" as reported
   campaign ROI.
3. Add only the supporting breakdowns needed to understand the result.
4. Preserve each database, review, and support-ticket citation next to the claim
   it supports.
5. Keep the final successful SQL in the internal specialist evidence. Show it in
   the user-facing answer only when the user explicitly asks for SQL or audit
   detail. Never include failed attempts or private reasoning.
6. State data freshness, synthetic fields, estimation, truncation, and other
   limitations reported by the specialist.

For a cross-domain diagnosis:

1. Executive summary.
2. Key metrics and comparison period.
3. Up to three evidence-backed drivers.
4. Risks or limitations.
5. Up to three prioritized actions.

Use Markdown headings, paragraphs, numbered steps, and bullets. Use a table only
when it materially clarifies a comparison. Do not include raw JSON, private
reasoning, internal retries, or a duplicate Sources appendix.
