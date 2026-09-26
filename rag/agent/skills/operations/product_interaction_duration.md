# Skill: Product Interaction Duration Ranking

## Trigger

Use this skill when the task asks which products receive the most or longest
interaction time across product-related user behaviors.

## Execution procedure

1. Call `check_most_interact` with no arguments.
2. Do not retrieve schema, generate SQL, resolve product names, or call another
   rate or ranking Tool for this request.
3. Preserve the returned order. The first product has the strongest combined
   interaction-duration ranking, and the list contains at most ten products.
4. Display the returned `total_duration`, `avg_duration`, `interaction_count`,
   `rank_total`, `rank_avg`, and `rank_combo` beside each product. Do not invent
   causes, time ranges, or recommendations.
5. An empty list means the query succeeded but no product met all filters. A Tool
   error means the database query failed and must not be described as no data.

## Ranking definition

The fixed SQL keeps products with non-null interaction duration and at least 20
interaction rows. It ranks both total duration and average duration descending,
averages those two ranks into `rank_combo`, then orders by `rank_combo` ascending
and total duration descending. This is a combined rank, not a pure total-duration
sort and not a unique-customer engagement measure.
