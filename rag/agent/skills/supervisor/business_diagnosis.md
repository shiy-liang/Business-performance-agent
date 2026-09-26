# Skill: Business Diagnosis

## When to use

Use this skill when the user asks what happened, why it happened, what is urgent,
or what the business should do next.

## Diagnostic sequence

1. Identify the business object: company, store, channel, category, product,
   campaign, customer segment, or support queue.
2. Identify the period and comparison basis.
3. Classify the request as finance, operations, knowledge, or cross-domain.
4. Decompose the evidence request into the minimum necessary atomic subtasks,
   then dispatch each required specialist once with its complete group.
5. Retrieve policy evidence only when it changes interpretation or action.
6. Compare returned evidence for period, scope, freshness, and synthetic-data
   warnings.
7. Rank no more than three drivers by evidence strength and likely business impact.
8. Recommend specific actions, responsible business roles, and a review horizon.

## Failure behavior

- Missing period for an exact metric: ask a clarification question.
- Missing specialist: explain the prototype boundary.
- Empty knowledge retrieval: do not invent a policy.
- Conflicting evidence: lower confidence and show the conflict.
- Stale data: state the latest available date before giving a conclusion.

## Example

User question: "What severity applies when stock equals 25% of reorder level?"

Expected behavior:

1. Format one Supervisor-owned `search_knowledge` subtask.
2. Search the knowledge base for inventory risk thresholds.
3. Quote the matching rule ID and threshold.
4. Answer the percentage-to-severity mapping directly and cite the source chunk.
