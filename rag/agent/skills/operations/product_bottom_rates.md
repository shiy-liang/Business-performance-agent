# Skill: Product Bottom Rates

## Trigger

Use this skill when the task asks which products have the lowest, worst, or least
effective like rate or purchase rate across the current product metrics view.

## Execution procedure

1. For lowest like-rate requests, call `check_less_like` with no arguments.
2. For lowest purchase-rate requests, call `check_less_purchase` with no
   arguments.
3. Do not search schema, generate SQL, resolve product names, or call the
   single-product rate tools for a Bottom-{{bottom_rate_result_limit}} request.
4. Preserve the returned order. The first item is the lowest-rate product, and
   the list contains at most {{bottom_rate_result_limit}} products.
5. Display the exact `like_rate` or `purchase_rate` returned beside each product.
   Do not invent causes, time ranges, or recommendations from this ranking. If
   deeper diagnosis is requested, treat it as a separate evidence requirement.
6. An empty list means the view query succeeded but found no non-null metric.
   A Tool error means the database query failed; never treat it as an empty list.

## Data contract

Both tools read precomputed metrics only from `public.v_product_metrics`. They do
not scan `public.interactions` or calculate rates in application code.
