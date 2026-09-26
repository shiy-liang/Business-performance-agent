# Skill: Product Bottom Purchase Rate

## Trigger

Use this skill when the task asks which products have the lowest, worst, or least
effective purchase rate across the current product metrics view.

## Execution procedure

1. Call `check_less_purchase` with no arguments.
2. Do not search schema, generate SQL, or use a single-product rate tool for this
   Bottom-10 request.
3. Preserve the returned order. The first item is the lowest-purchase-rate
   product, and the list contains at most ten products.
4. Display the exact `purchase_rate` returned beside each product. Do not invent
   causes, time ranges, or recommendations from this ranking.
5. An empty list means the view query succeeded but found no non-null purchase
   rate. A Tool error means the database query failed.

## Data contract

The Tool reads the precomputed `purchase_rate` only from
`public.v_product_metrics`. It does not scan `public.interactions` or calculate
the rate in application code.
