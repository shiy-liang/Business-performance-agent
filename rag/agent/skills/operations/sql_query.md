# Skill: Operations SQL Query

## Use this skill for

Sales units and breakdowns, inventory status, product and store performance,
customer activity, returns by count or reason, support service, and operational
campaign conversion metrics.

Assign this skill to an atomic structured-data subtask only when no dedicated
Operations skill covers that subtask. It may coexist with dedicated skills in the
same task packet when they own different subtasks.

## Do not use this skill for

Profitability, margin, expenses, financial ROI conclusions, policy interpretation,
or product feedback and review questions covered by the Product Review Retrieval
skill. Never generate SQL for, verify, enrich, or retry a subtask assigned to a
dedicated skill.

## Procedure

1. Identify the operational measure, grain, period, scope, and filters.
2. If the query involves a product name, first call `find_real_name` to obtain
   the exact canonical name. Use only a name returned in `items`. Once it returns
   `result_status=matched`, do not call `find_real_name` again for this task.
3. Only when the query concerns a campaign and the user supplied a fuzzy,
   abbreviated, non-standard, or translated campaign name, call
   `find_real_campaign_name` before retrieving schema or generating SQL. Use only
   exact `campaign_name` values returned in `items`. If multiple names are
   returned, select one or more according to the user's wording and requested
   scope; never invent another name. After `result_status=matched`, reuse the
   selected names and do not call the Tool again. Do not call it when no campaign
   name was supplied or when the supplied name is already exact.
4. Retrieve only relevant Operations schema.
5. If a column's type, meaning, or allowed values are unclear, call
   `get_columns_detail` for its table before generating SQL.
6. Resolve uncertain stores, customers, or categories with the general entity
   resolver. Product names must use `find_real_name`; fuzzy campaign names must
   use `find_real_campaign_name`.
7. Choose the correct fact date and avoid mixing transaction, return, review, and
   inventory grains.
8. For inventory, select one appropriate snapshot before aggregating.
9. Generate parameterized, explicit-column SQL with deterministic ordering.
10. Execute through the Operations SQL tool and check for fan-out or truncation.
11. Label synthetic fields and describe relationships as associations.
12. Provide the result, citation, final SQL, parameters, and visible limitations.

## Positive example

For "Which product was returned most last month?", sum `return_quantity` by the
product joined through its transaction, filter `return_date` with a half-open
monthly range, and rank with a deterministic product-name tie breaker.

## Negative example

Do not sum stock across every `snapshot_date`; that would add repeated snapshots
and overstate inventory.
