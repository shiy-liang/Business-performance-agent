# Skill: Product Review Retrieval

## Trigger

Use this skill whenever the delegated task asks for customer feedback, reviews,
ratings, opinions, praise, complaints, likes, dislikes, or perceived strengths and
weaknesses of a product or product category.

## Dedicated workflow

1. Call `search_customer_reviews` first. Do not search schema, resolve an entity,
   generate SQL, or call `execute_operations_sql` for a task that matches this
   skill.
2. The first semantic search must include the requested product in `product_name`
   or the requested category in `product_category`; also preserve that wording in
   `query`. If neither scope is present, return a compact clarification request
   instead of querying unfiltered reviews.
3. Make exactly one semantic search by default. Make a second or third sequential
   search only when the question contains distinct themes, rating segments, or an
   explicit product comparison that one search cannot cover. Never exceed three
   semantic searches and never call them in parallel.
4. Set `comparison_mode=true` on the first search only when the user explicitly
   asks to compare products. Without an explicit comparison, every later search
   or expansion must remain on the first product, and querying another product is
   forbidden.
5. Base the finding on returned `product_name`, `product_category`, `rating`,
   `review_date`, `review_title`, and `review_text` values. Cite the exact
   `[review:...]` evidence used.
6. If the semantic results are insufficient for the requested comparison or
   negative-feedback analysis, optionally call `find_other_comment_product` or
   `find_other_comment_category` using one exact value returned by the semantic
   search.
7. The two `find_other_comment_*` tools share a maximum of two sequential calls.
   Select product versus category according to the user's scope. For a
   product-specific non-comparison request, only
   `find_other_comment_product` with that same product is allowed. Do not call
   both expansion tools merely to collect more text.
8. Omit `rating` from an expansion call unless a stricter low-rating threshold is
   required. The default threshold is 5 and the tool returns rows strictly below
   the selected threshold.
9. Stop as soon as the evidence is sufficient. Do not use the generic SQL
   workflow as a second route for the same review task.

## Interpretation

- Semantic and expansion results are retrieved review samples, not a complete
  distribution. Do not infer total review counts, average ratings, percentages,
  or prevalence from them.
- Summarize recurring positive and negative feedback only when supported by the
  retrieved text. Preserve differences between products or categories when the
  results contain multiple values.
- If no matching reviews are returned, report that retrieval result without
  inventing an overall evaluation.
