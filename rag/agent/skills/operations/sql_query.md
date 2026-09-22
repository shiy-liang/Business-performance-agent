# Skill: Operations SQL Query

## Use this skill for

Sales units and breakdowns, inventory status, product and store performance,
customer activity, returns by count or reason, support service, reviews, and
operational campaign conversion metrics.

## Do not use this skill for

Profitability, margin, expenses, financial ROI conclusions, policy interpretation,
or unrestricted semantic analysis of long text.

## Procedure

1. Identify the operational measure, grain, period, scope, and filters.
2. Retrieve only relevant Operations schema.
3. Resolve uncertain products, stores, campaigns, customers, or categories.
4. Choose the correct fact date and avoid mixing transaction, return, review, and
   inventory grains.
5. For inventory, select one appropriate snapshot before aggregating.
6. Generate parameterized, explicit-column SQL with deterministic ordering.
7. Execute through the Operations SQL tool and check for fan-out or truncation.
8. Label synthetic fields and describe relationships as associations.
9. Provide the result, citation, final SQL, parameters, and visible limitations.
10. If the task requires customer-language themes, preserve the SQL population as
    the quantitative baseline and then use `search_customer_reviews` with matching
    product, category, date, and rating filters. Treat the returned reviews as
    qualitative evidence, not a statistically complete distribution.

## Positive example

For "Which product was returned most last month?", sum `return_quantity` by the
product joined through its transaction, filter `return_date` with a half-open
monthly range, and rank with a deterministic product-name tie breaker.

## Negative example

Do not sum stock across every `snapshot_date`; that would add repeated snapshots
and overstate inventory.
