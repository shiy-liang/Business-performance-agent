# Skill: Product Like Rate

## Trigger

Use this skill when the task asks what proportion of a product's views became
expressed interest through an add-to-cart or wishlist-add event, including
wording about like rate, interest rate, view-to-like conversion, carts after
views, or wishlists after views.

## Dedicated workflow

1. Use `find_real_name` first only when the product wording is fuzzy,
   non-standard, or cross-language. If it returns multiple plausible products
   and the user did not explicitly request a comparison, request clarification.
2. Call `check_like_rate` with one exact canonical `product_name`. Do not search
   schema, generate SQL, call an entity resolver, or call
   `execute_operations_sql` for this metric.
3. For an explicit comparison, call the tool sequentially once per requested
   canonical product. Do not introduce products the user did not request.
4. Interpret `result_status` explicitly:
   - `ok`: report `like_rate` and the component event counts.
   - `empty_result`: no interaction group exists for the product.
   - `undefined_rate`: there are zero product views, so no rate can be calculated.
   - `query_failed`: report that database evidence is unavailable.
5. Cite a successful result with the exact returned `[db:operations:...]`
   citation. Never invent a percentage when `like_rate` is null.

## Metric definition

`like_rate` is the combined count of `wishlist_add` and `add_to_cart`
interactions divided by the count of `product_view` interactions, rounded by
PostgreSQL to four decimal places. Describe it as an interaction-event ratio, not
as a unique-customer conversion funnel or causal probability.
