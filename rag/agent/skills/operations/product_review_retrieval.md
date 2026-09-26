# Skill: Product Review Retrieval

## Trigger

Use this skill whenever the delegated task asks for customer feedback, reviews,
ratings, opinions, praise, complaints, likes, dislikes, or perceived strengths and
weaknesses of a product or product category.

## Execution procedure

1. Do not call `find_real_name` for this skill. Review retrieval uses semantic
   matching, so fuzzy or cross-language phrases such as "苹果平板" and
   "ipad pro" can be passed directly to `search_customer_reviews`; do not
   require an exact stored product name first.
2. Call `search_customer_reviews` as the first evidence-retrieval tool. Do not
   search schema, resolve an entity, generate SQL, or call
   `execute_operations_sql` for a task that matches this skill.
3. The first semantic search must include the requested product in `product_name`
   or the requested category in `product_category`; also preserve that wording in
   `query`. If neither scope is present, return a compact clarification request
   instead of querying unfiltered reviews.
4. Make exactly one semantic search by default. Make a second or third sequential
   search only when the question contains distinct themes, rating segments, or an
   explicit product comparison that one search cannot cover. Within the current
   subtask, never exceed three semantic searches and never call them in parallel.
5. Set `comparison_mode=true` on the first search only when the user explicitly
   asks to compare products. Without an explicit comparison, every later search
   or expansion must remain on the first product, and querying another product is
   forbidden.
6. Base the finding on returned `product_name`, `product_category`, `rating`,
   `review_date`, `review_title`, and `review_text` values. Cite the exact
   `[review:...]` evidence used.
7. If the semantic results are insufficient for the requested comparison or
   negative-feedback analysis, optionally call `find_other_comment_product` or
   `find_other_comment_category` using one exact value returned by the semantic
   search.
8. Within the current subtask, the two `find_other_comment_*` tools share a
   maximum of two sequential calls. Both review limits reset when that subtask
   reaches a terminal status. Select product versus category according to the
   user's scope. For a
   product-specific non-comparison request, only
   `find_other_comment_product` with that same product is allowed. Do not call
   both expansion tools merely to collect more text.
9. Omit `rating` from an expansion call unless a stricter low-rating threshold is
   required. The default threshold is 5 and the tool returns rows strictly below
   the selected threshold.
10. Stop as soon as the evidence is sufficient. Do not use generic SQL as a
   second route for the same review subtask.

## Interpretation

- Semantic and expansion results are retrieved review samples, not a complete
  distribution. Do not infer total review counts, average ratings, percentages,
  or prevalence from them.
- Summarize recurring positive and negative feedback only when supported by the
  retrieved text. Preserve differences between products or categories when the
  results contain multiple values.
- If no matching reviews are returned, report that retrieval result without
  inventing an overall evaluation.
