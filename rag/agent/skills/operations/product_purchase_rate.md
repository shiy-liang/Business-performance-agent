# Skill: Product Purchase Rate

## Trigger

Use this skill when the task asks what proportion of a product's expressed
interest became a purchase, including wording about cart, wishlist, checkout,
purchase conversion, actual transaction rate, or loved-to-purchased rate.

## Execution procedure

1. Use `find_real_name` first only when the product wording is fuzzy,
   non-standard, or cross-language. If it returns multiple plausible products
   and the user did not explicitly request a comparison, request clarification.
   Never invent, infer, translate into, or guess a canonical product name. The
   resolver permits three sequential attempts with thresholds 0.70, 0.60, and
   0.55. Retry only when `retryable=true`, using a faithful rephrasing that does
   not add an unmentioned model. When `result_status=matched`, use an exact name
   from `items` and never call `find_real_name` again. If the third result is empty and
   `terminal=true`, stop immediately and ask for the exact product name.
2. Call `check_purchase_rate` with one exact canonical `product_name`. Do not
   search schema, generate SQL, call an entity resolver, or call
   `execute_operations_sql` for this metric.
   The name must be one of the exact values in the successful result's `items`
   returned by `find_real_name`
   whenever resolution was attempted; never call this tool after empty results.
3. For an explicit comparison, call the tool sequentially once per requested
   canonical product. Do not introduce products the user did not request.
4. Interpret `result_status` explicitly:
   - `ok`: report `purchase_rate` and the component event counts.
   - `empty_result`: no interaction group exists for the product.
   - `undefined_rate`: the denominator is zero, so no rate can be calculated.
   - `query_failed`: report that database evidence is unavailable.
5. Cite a successful result with the exact returned `[db:operations:...]`
   citation. Never invent a percentage when `purchase_rate` is null.

## Metric definition

`purchase_rate` is the count of `purchase` interactions divided by the combined
count of `checkout`, `wishlist_add`, and `add_to_cart` interactions, rounded by
PostgreSQL to four decimal places. Describe it as an interaction-event ratio, not
as a unique-customer conversion funnel or causal probability.
