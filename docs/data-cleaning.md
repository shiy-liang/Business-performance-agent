# Data Cleaning Specification

## 1. Purpose

This document defines how the raw business data should be cleaned before it is used by the Business Performance Agent. The goal is to create consistent, traceable datasets for analysing sales, customers, marketing campaigns, customer interactions, reviews, and support performance.

The raw files must remain unchanged. Cleaned files should be written to `data/processed/`, while rejected records and validation results should be written to `data/quality/`.

## 2. Source datasets

| Dataset | Business use | Expected main identifier |
| --- | --- | --- |
| `customers.csv` | Customer profile and segmentation | `customer_id` |
| `transactions.csv` | Revenue, products, and purchasing behaviour | Transaction identifier if available |
| `interactions.csv` | Customer engagement across channels | Interaction identifier if available |
| `campaigns.csv` | Marketing cost and campaign performance | `campaign_id` |
| `support_tickets.csv` | Support workload and service quality | Ticket identifier |
| `customer_reviews_complete.csv` | Ratings and customer feedback | Review identifier if available |

All identifier names must be confirmed against the actual CSV headers before the cleaning pipeline is implemented.

## 3. Cleaning principles

1. Keep every raw file immutable.
2. Preserve the original row reference using `_source_file` and `_source_row_number`.
3. Do not silently replace missing financial or quantity values with zero.
4. Standardise values before checking duplicates and relationships.
5. Quarantine invalid records instead of deleting them without an audit trail.
6. Record every applied rule in a data-quality report.

## 4. Common cleaning rules

### Column names and text

- Convert column names to lowercase `snake_case`.
- Trim leading and trailing whitespace.
- Convert empty strings, `N/A`, `NA`, `null`, and equivalent placeholders to null.
- Standardise categorical values using an approved mapping table.
- Preserve free-text review and support fields; only remove invalid control characters.

### Identifiers and duplicates

- Store identifiers as strings so leading zeroes are preserved.
- Reject rows with missing required primary identifiers.
- Remove exact duplicate rows after retaining one copy and logging the duplicate count.
- For repeated identifiers with different values, quarantine the affected rows for review.

### Dates and times

- Parse dates into ISO 8601 format: `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SS`.
- Use one documented timezone for timestamps.
- Reject impossible dates and flag future dates unless the field represents a planned event.
- Check that end or resolution dates are not earlier than start or creation dates.

### Numeric values

- Remove currency symbols and thousands separators before numeric conversion.
- Reject negative quantities, prices, budgets, durations, impressions, clicks, and conversions unless the field explicitly permits them.
- Keep missing numeric values as null until a documented imputation rule is approved.
- Round derived currency values to two decimal places only after calculations.

## 5. Dataset-specific rules

### Customers

- Validate that `customer_id` is present and unique.
- Normalise email addresses to lowercase and validate their structure.
- Standardise phone numbers while preserving country codes.
- Standardise state, postcode, and country values.
- Check that age is within a plausible business-approved range.
- Ensure registration dates are valid and do not occur after related activity dates.

### Transactions

- Require a valid customer reference and transaction date.
- Convert quantity, unit price, and discount fields to numeric values.
- Require quantity and unit price to be greater than zero for valid sales rows.
- Confirm whether discount is stored as a percentage or decimal before calculating revenue.
- After that definition is confirmed, calculate:
  - `gross_sales = quantity * unit_price`
  - `discount_amount = gross_sales * discount_rate`
  - `net_sales = gross_sales - discount_amount`
- Standardise product and category names.
- Do not invent product or transaction identifiers when none exist; document the resulting aggregation limitation.

### Customer interactions

- Standardise interaction channel and interaction type.
- Validate customer references and timestamps.
- Require duration values to be non-negative.
- Identify exact duplicate events using customer, timestamp, channel, and event details.

### Campaigns

- Validate campaign identifiers, names, dates, and budget values.
- Require the campaign end date to be on or after its start date.
- Require impressions, clicks, and conversions to be non-negative integers.
- Flag records where clicks exceed impressions.
- Confirm the business definition of conversion before enforcing `conversions <= clicks`.
- Derive click-through rate, conversion rate, and cost per conversion only when their denominators are greater than zero.

### Support tickets

- Standardise status, priority, category, and channel values.
- Validate customer references and creation dates.
- Allow an unresolved ticket to have a missing resolution date.
- Require resolved tickets to have a resolution date that is not earlier than the creation date.
- Require resolution time to be non-negative.
- Validate satisfaction scores against the scale documented by the data owner.

### Customer reviews

- Validate rating values against the documented rating scale.
- Validate customer references and review dates.
- Standardise product and category text without changing the meaning of review content.
- Do not attribute a review to a specific transaction unless a reliable transaction key exists.
- Remove only true duplicate reviews; repeated ratings from one customer may represent separate purchases.

## 6. Cross-dataset validation

- Every non-null customer reference should exist in `customers.csv`.
- Product and category labels should use the same canonical mapping across transactions and reviews.
- Campaign attribution should only be produced when a reliable shared key or documented attribution rule exists.
- Review-to-purchase attribution should only be produced when a transaction key or defensible matching rule exists.
- Dates should follow a logical sequence: customer registration, transaction or interaction, review, and ticket resolution.

## 7. Missing-value policy

| Field type | Default treatment |
| --- | --- |
| Required identifier | Quarantine the row |
| Quantity or price | Keep null and exclude from revenue calculations |
| Optional category | Map to `Unknown` only in reporting output |
| Free text | Keep null; do not generate replacement text |
| Resolution date for an open ticket | Keep null as a valid business state |
| Rating or satisfaction score | Keep null and exclude from average-score calculations |

The current raw-data review found missing quantity and/or price values in the transaction data. These records must not contribute to revenue until the source values are corrected or an approved imputation rule is documented.

## 8. Output structure

```text
data/
├── raw/                 # Original, unchanged CSV files
├── processed/           # Clean datasets used by the application
└── quality/
    ├── rejected_rows/   # Records that fail mandatory rules
    └── quality_report.csv
```

Each processed dataset should include these audit fields where practical:

- `_source_file`
- `_source_row_number`
- `_cleaned_at`
- `_quality_status`
- `_quality_issues`

## 9. Quality gates

A dataset is ready for analysis when:

- required identifiers are present and unique;
- required dates and numeric fields parse successfully;
- customer foreign keys are valid;
- invalid financial values do not enter KPI calculations;
- duplicates and rejected rows are counted and reported;
- derived measures use documented formulas;
- processed row counts reconcile with raw, rejected, and deduplicated row counts.

The reconciliation rule is:

```text
raw rows = processed rows + rejected rows + removed duplicate rows
```

## 10. Decisions required before implementation

The team should confirm the following definitions:

1. Currency used for prices and campaign budgets.
2. Whether unit price is recorded before or after discount.
3. Whether discount values are percentages or decimal rates.
4. Valid ranges for customer age, review rating, and satisfaction score.
5. The permitted method for handling missing transaction quantities and prices.
6. Whether campaign and review attribution keys exist outside the supplied raw files.
