"""Clean and validate the Business Performance Agent datasets.

Current stage: date validation and transaction sales calculations.

The script never modifies files under data/raw. Date checks run in memory and
do not create a separate report.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


@dataclass(frozen=True)
class DateRule:
    """Date columns and ordering rules for one CSV file."""

    columns: tuple[str, ...]
    ordered_pairs: tuple[tuple[str, str], ...] = ()
    required_when: tuple[tuple[str, str, tuple[str, ...]], ...] = ()


DATE_RULES: dict[str, DateRule] = {
    "customers.csv": DateRule(columns=("registration_date",)),
    "transactions.csv": DateRule(columns=("transaction_date",)),
    "interactions.csv": DateRule(columns=("interaction_date",)),
    "campaigns.csv": DateRule(
        columns=("start_date", "end_date"),
        ordered_pairs=(("start_date", "end_date"),),
    ),
    "support_tickets.csv": DateRule(
        columns=("submission_date", "resolution_date"),
        ordered_pairs=(("submission_date", "resolution_date"),),
        required_when=(
            ("resolution_date", "resolution_status", ("resolved",)),
        ),
    ),
    "customer_reviews_complete.csv": DateRule(
        columns=("transaction_date", "review_date"),
        ordered_pairs=(("transaction_date", "review_date"),),
    ),
}


def append_issue(issues: pd.Series, mask: pd.Series, message: str) -> None:
    """Append a validation message to every row selected by mask."""

    selected = issues.loc[mask]
    issues.loc[mask] = selected.where(selected.eq(""), selected + "; ") + message


def validate_dates(path: Path, rule: DateRule) -> pd.DataFrame:
    """Parse and validate all configured dates in one CSV file."""

    frame = pd.read_csv(path, dtype=str, keep_default_na=True)
    frame.columns = frame.columns.str.strip().str.lower()
    issues = pd.Series("", index=frame.index, dtype="string")

    missing_columns = [column for column in rule.columns if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"{path.name} is missing date columns: {missing_columns}")

    for column in rule.columns:
        original = frame[column].astype("string").str.strip()
        supplied = original.notna() & original.ne("")
        parsed = pd.to_datetime(original, errors="coerce")
        invalid = supplied & parsed.isna()

        append_issue(issues, invalid, f"invalid {column}")

        # Store valid dates in one stable ISO format; missing values stay empty.
        frame[column] = parsed.dt.strftime("%Y-%m-%d")
        frame[f"_{column}_parsed"] = parsed

    for earlier, later in rule.ordered_pairs:
        invalid_order = (
            frame[f"_{earlier}_parsed"].notna()
            & frame[f"_{later}_parsed"].notna()
            & (frame[f"_{later}_parsed"] < frame[f"_{earlier}_parsed"])
        )
        append_issue(issues, invalid_order, f"{later} is before {earlier}")

    for required_date, condition_column, condition_values in rule.required_when:
        if condition_column not in frame.columns:
            raise ValueError(f"{path.name} is missing condition column: {condition_column}")

        condition = frame[condition_column].astype("string").str.strip().str.lower()
        required_missing = condition.isin(condition_values) & frame[
            f"_{required_date}_parsed"
        ].isna()
        append_issue(
            issues,
            required_missing,
            f"{required_date} is required when {condition_column} is "
            + "/".join(condition_values),
        )

    parsed_helper_columns = [f"_{column}_parsed" for column in rule.columns]
    frame = frame.drop(columns=parsed_helper_columns)
    frame["_date_validation_issues"] = issues
    return frame


def clean_transactions(frame: pd.DataFrame) -> pd.DataFrame:
    """Clean transaction values and calculate sales after discount."""

    required_columns = {"quantity", "price", "discount_applied"}
    missing_columns = required_columns.difference(frame.columns)
    if missing_columns:
        raise ValueError(
            f"transactions.csv is missing columns: {sorted(missing_columns)}"
        )

    cleaned = frame.copy()

    text_columns = [
        "transaction_id",
        "customer_id",
        "product_name",
        "product_category",
        "store_location",
        "payment_method",
    ]
    for column in text_columns:
        cleaned[column] = cleaned[column].astype("string").str.strip()
        cleaned[column] = cleaned[column].replace("", pd.NA)

    # Empty or invalid numeric values become missing values.
    for column in required_columns:
        original = cleaned[column].astype("string").str.strip()
        numeric = pd.to_numeric(original, errors="coerce")
        invalid = original.notna() & original.ne("") & numeric.isna()
        if invalid.any():
            raise ValueError(
                f"transactions.csv contains {int(invalid.sum())} invalid "
                f"numeric values in {column}"
            )
        cleaned[column] = numeric

    invalid_quantity = cleaned["quantity"].notna() & (
        (cleaned["quantity"] <= 0) | cleaned["quantity"].mod(1).ne(0)
    )
    invalid_price = cleaned["price"].notna() & (cleaned["price"] < 0)
    invalid_discount = cleaned["discount_applied"].notna() & ~cleaned[
        "discount_applied"
    ].between(0, 100)

    if invalid_quantity.any() or invalid_price.any() or invalid_discount.any():
        raise ValueError(
            "transactions.csv contains out-of-range quantity, price, or discount values"
        )

    # Revenue analysis requires all three inputs. The raw file remains intact;
    # only incomplete rows are excluded from the processed transaction dataset.
    cleaned = cleaned.dropna(
        subset=["quantity", "price", "discount_applied"]
    ).copy()
    # Quantity is a count. Explicitly restore an integer dtype after missing
    # values caused pandas to parse the source column as floating point.
    cleaned["quantity"] = cleaned["quantity"].astype("Int64")

    cleaned["gross_sales"] = (cleaned["quantity"] * cleaned["price"]).round(2)
    cleaned["discount_amount"] = (
        cleaned["gross_sales"] * cleaned["discount_applied"] / 100
    ).round(2)
    cleaned["net_sales"] = (
        cleaned["gross_sales"] - cleaned["discount_amount"]
    ).round(2)

    return cleaned.drop(columns="_date_validation_issues")


def build_product_and_store_dimensions(
    transactions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Derive product and store tables and add their IDs to transactions."""

    products = (
        transactions[["product_name", "product_category"]]
        .dropna()
        .drop_duplicates()
        .sort_values(["product_category", "product_name"])
        .reset_index(drop=True)
    )
    products.insert(0, "product_id", [f"P{i:04d}" for i in range(1, len(products) + 1)])

    # Every observed product name maps to exactly one category in this dataset.
    # Use that reliable mapping to recover rows whose category alone is missing.
    if products["product_name"].duplicated().any():
        raise ValueError("Product names map to multiple categories; cannot infer safely")
    product_categories = products.set_index("product_name")["product_category"]
    enriched_base = transactions.copy()
    missing_category = (
        enriched_base["product_name"].notna()
        & enriched_base["product_category"].isna()
    )
    enriched_base.loc[missing_category, "product_category"] = enriched_base.loc[
        missing_category, "product_name"
    ].map(product_categories)

    stores = (
        transactions[["store_location"]]
        .dropna()
        .drop_duplicates()
        .sort_values("store_location")
        .reset_index(drop=True)
    )
    stores.insert(0, "store_id", [f"S{i:03d}" for i in range(1, len(stores) + 1)])
    stores["store_type"] = stores["store_location"].apply(
        lambda value: "online" if value.lower() == "online" else "physical"
    )

    enriched = enriched_base.merge(
        products,
        on=["product_name", "product_category"],
        how="left",
        validate="many_to_one",
    )
    enriched = enriched.merge(
        stores,
        on="store_location",
        how="left",
        validate="many_to_one",
    )

    transaction_columns = list(transactions.columns)
    product_position = transaction_columns.index("product_name")
    transaction_columns.insert(product_position, "product_id")
    store_position = transaction_columns.index("store_location")
    transaction_columns.insert(store_position, "store_id")
    enriched = enriched[transaction_columns]

    return enriched, products, stores


def clean_customers(frame: pd.DataFrame) -> pd.DataFrame:
    """Standardise customer details while preserving missing optional values."""

    required_columns = {
        "customer_id",
        "full_name",
        "age",
        "gender",
        "email",
        "phone",
        "street_address",
        "city",
        "state",
        "zip_code",
        "preferred_channel",
    }
    missing_columns = required_columns.difference(frame.columns)
    if missing_columns:
        raise ValueError(f"customers.csv is missing columns: {sorted(missing_columns)}")

    cleaned = frame.copy()
    text_columns = cleaned.select_dtypes(include=["object", "string"]).columns
    for column in text_columns:
        cleaned[column] = cleaned[column].astype("string").str.strip()
        cleaned[column] = cleaned[column].replace("", pd.NA)

    if cleaned["customer_id"].isna().any():
        raise ValueError("customers.csv contains missing customer_id values")
    if cleaned["customer_id"].duplicated().any():
        raise ValueError("customers.csv contains duplicate customer_id values")

    original_age = cleaned["age"]
    age = pd.to_numeric(original_age, errors="coerce")
    invalid_age_type = original_age.notna() & age.isna()
    invalid_age_range = age.notna() & (~age.between(18, 80) | age.mod(1).ne(0))
    if invalid_age_type.any() or invalid_age_range.any():
        raise ValueError("customers.csv contains invalid age values")
    cleaned["age"] = age.astype("Int64")

    cleaned["email"] = cleaned["email"].str.lower()
    valid_email = cleaned["email"].str.fullmatch(
        r"[^@\s]+@[^@\s]+\.[^@\s]+", na=True
    )
    if (~valid_email).any():
        raise ValueError(
            f"customers.csv contains {int((~valid_email).sum())} invalid email addresses"
        )

    # ZIP codes are identifiers rather than numbers. Keeping them as strings
    # preserves leading zeroes such as 09806.
    cleaned["zip_code"] = cleaned["zip_code"].str.replace(r"\.0$", "", regex=True)

    return cleaned.drop(columns="_date_validation_issues")


def validate_customer_references(
    customers: pd.DataFrame, transactions: pd.DataFrame
) -> None:
    """Ensure every transaction belongs to a known customer."""

    missing_customer = transactions["customer_id"].isna()
    unknown_customer = ~transactions["customer_id"].isin(customers["customer_id"])
    invalid = missing_customer | unknown_customer
    if invalid.any():
        raise ValueError(
            f"transactions.csv contains {int(invalid.sum())} missing or unknown customer IDs"
        )


def clean_campaigns(frame: pd.DataFrame) -> pd.DataFrame:
    """Clean campaign metrics used for marketing-performance analysis."""

    metric_columns = [
        "budget",
        "impressions",
        "clicks",
        "conversions",
        "conversion_rate",
        "roi",
    ]
    required_columns = {
        "campaign_id",
        "campaign_name",
        "campaign_type",
        "target_segment",
        *metric_columns,
    }
    missing_columns = required_columns.difference(frame.columns)
    if missing_columns:
        raise ValueError(f"campaigns.csv is missing columns: {sorted(missing_columns)}")

    cleaned = frame.copy()
    text_columns = [
        "campaign_id",
        "campaign_name",
        "campaign_type",
        "target_segment",
    ]
    for column in text_columns:
        cleaned[column] = cleaned[column].astype("string").str.strip()
        cleaned[column] = cleaned[column].replace("", pd.NA)

    if cleaned["campaign_id"].isna().any():
        raise ValueError("campaigns.csv contains missing campaign_id values")
    if cleaned["campaign_id"].duplicated().any():
        raise ValueError("campaigns.csv contains duplicate campaign_id values")

    for column in metric_columns:
        original = cleaned[column].astype("string").str.strip()
        numeric = pd.to_numeric(original, errors="coerce")
        invalid = original.notna() & original.ne("") & numeric.isna()
        if invalid.any():
            raise ValueError(f"campaigns.csv contains invalid values in {column}")
        cleaned[column] = numeric

    # Campaign KPIs cannot be compared reliably without all core metrics.
    cleaned = cleaned.dropna(subset=metric_columns).copy()

    count_columns = ["impressions", "clicks", "conversions"]
    fractional_counts = cleaned[count_columns].mod(1).ne(0)
    if fractional_counts.any().any():
        raise ValueError("campaigns.csv contains non-integer count metrics")
    for column in count_columns:
        cleaned[column] = cleaned[column].astype("Int64")

    non_negative = ["budget", "impressions", "clicks", "conversions"]
    if (cleaned[non_negative] < 0).any().any():
        raise ValueError("campaigns.csv contains negative campaign metrics")
    if (cleaned["clicks"] > cleaned["impressions"]).any():
        raise ValueError("campaigns.csv contains clicks greater than impressions")
    if (cleaned["conversions"] > cleaned["clicks"]).any():
        raise ValueError("campaigns.csv contains conversions greater than clicks")

    cleaned["campaign_name"] = cleaned["campaign_name"].fillna("Unknown")
    cleaned["campaign_type"] = cleaned["campaign_type"].fillna("Unknown")

    # Recalculate the rate from clicks and conversions so every row uses the
    # same definition. The source values match this formula after rounding.
    cleaned["conversion_rate"] = (
        cleaned["conversions"] / cleaned["clicks"] * 100
    ).round(2)

    return cleaned.drop(columns="_date_validation_issues")


def clean_interactions(
    frame: pd.DataFrame, customers: pd.DataFrame
) -> pd.DataFrame:
    """Clean customer interaction events for channel and journey analysis."""

    required_columns = {
        "interaction_id",
        "customer_id",
        "channel",
        "interaction_type",
        "duration",
        "page_or_product",
        "session_id",
    }
    missing_columns = required_columns.difference(frame.columns)
    if missing_columns:
        raise ValueError(
            f"interactions.csv is missing columns: {sorted(missing_columns)}"
        )

    cleaned = frame.copy()
    text_columns = [
        "interaction_id",
        "customer_id",
        "channel",
        "interaction_type",
        "page_or_product",
        "session_id",
    ]
    for column in text_columns:
        cleaned[column] = cleaned[column].astype("string").str.strip()
        cleaned[column] = cleaned[column].replace("", pd.NA)

    if cleaned["interaction_id"].isna().any():
        raise ValueError("interactions.csv contains missing interaction_id values")
    if cleaned["interaction_id"].duplicated().any():
        raise ValueError("interactions.csv contains duplicate interaction_id values")

    invalid_customer = cleaned["customer_id"].isna() | ~cleaned[
        "customer_id"
    ].isin(customers["customer_id"])
    if invalid_customer.any():
        raise ValueError(
            f"interactions.csv contains {int(invalid_customer.sum())} "
            "missing or unknown customer IDs"
        )

    # These two fields are required to count behaviour by channel and event.
    cleaned = cleaned.dropna(subset=["channel", "interaction_type"]).copy()
    for column in ["channel", "interaction_type"]:
        cleaned[column] = (
            cleaned[column]
            .str.lower()
            .str.replace(r"[\s-]+", "_", regex=True)
        )

    original_duration = cleaned["duration"].astype("string").str.strip()
    duration = pd.to_numeric(original_duration, errors="coerce")
    invalid_duration = (
        original_duration.notna() & original_duration.ne("") & duration.isna()
    )
    if invalid_duration.any():
        raise ValueError("interactions.csv contains invalid duration values")
    if (duration.dropna() < 0).any():
        raise ValueError("interactions.csv contains negative duration values")
    cleaned["duration"] = duration

    return cleaned.drop(columns="_date_validation_issues")


def clean_support_tickets(
    frame: pd.DataFrame, customers: pd.DataFrame
) -> pd.DataFrame:
    """Clean support tickets without discarding valid unresolved tickets."""

    required_columns = {
        "ticket_id",
        "customer_id",
        "issue_category",
        "priority",
        "resolution_status",
        "resolution_time_hours",
        "customer_satisfaction_score",
        "notes",
    }
    missing_columns = required_columns.difference(frame.columns)
    if missing_columns:
        raise ValueError(
            f"support_tickets.csv is missing columns: {sorted(missing_columns)}"
        )

    cleaned = frame.copy()
    text_columns = [
        "ticket_id",
        "customer_id",
        "issue_category",
        "priority",
        "resolution_status",
        "notes",
    ]
    for column in text_columns:
        cleaned[column] = cleaned[column].astype("string").str.strip()
        cleaned[column] = cleaned[column].replace("", pd.NA)

    if cleaned["ticket_id"].isna().any():
        raise ValueError("support_tickets.csv contains missing ticket_id values")
    if cleaned["ticket_id"].duplicated().any():
        raise ValueError("support_tickets.csv contains duplicate ticket_id values")

    invalid_customer = cleaned["customer_id"].isna() | ~cleaned[
        "customer_id"
    ].isin(customers["customer_id"])
    if invalid_customer.any():
        raise ValueError(
            f"support_tickets.csv contains {int(invalid_customer.sum())} "
            "missing or unknown customer IDs"
        )

    categorical_columns = ["issue_category", "priority", "resolution_status"]
    for column in categorical_columns:
        cleaned[column] = (
            cleaned[column]
            .fillna("unknown")
            .str.lower()
            .str.replace(r"[\s-]+", "_", regex=True)
        )

    numeric_columns = ["resolution_time_hours", "customer_satisfaction_score"]
    for column in numeric_columns:
        original = cleaned[column].astype("string").str.strip()
        numeric = pd.to_numeric(original, errors="coerce")
        invalid = original.notna() & original.ne("") & numeric.isna()
        if invalid.any():
            raise ValueError(f"support_tickets.csv contains invalid values in {column}")
        cleaned[column] = numeric

    if (cleaned["resolution_time_hours"].dropna() < 0).any():
        raise ValueError("support_tickets.csv contains negative resolution times")

    score = cleaned["customer_satisfaction_score"]
    invalid_score = score.notna() & (~score.between(1, 5) | score.mod(1).ne(0))
    if invalid_score.any():
        raise ValueError("support_tickets.csv contains satisfaction scores outside 1-5")
    cleaned["customer_satisfaction_score"] = score.astype("Int64")

    return cleaned.drop(columns="_date_validation_issues")


def clean_reviews(frame: pd.DataFrame, customers: pd.DataFrame) -> pd.DataFrame:
    """Clean ratings and review text for customer-feedback analysis."""

    required_columns = {
        "review_id",
        "customer_id",
        "product_name",
        "product_category",
        "full_name",
        "rating",
        "review_title",
        "review_text",
    }
    missing_columns = required_columns.difference(frame.columns)
    if missing_columns:
        raise ValueError(
            f"customer_reviews_complete.csv is missing columns: {sorted(missing_columns)}"
        )

    cleaned = frame.copy()
    text_columns = [
        "review_id",
        "customer_id",
        "product_name",
        "product_category",
        "full_name",
        "review_title",
        "review_text",
    ]
    for column in text_columns:
        cleaned[column] = cleaned[column].astype("string").str.strip()
        cleaned[column] = cleaned[column].replace("", pd.NA)

    if cleaned["review_id"].isna().any():
        raise ValueError("customer_reviews_complete.csv contains missing review_id values")
    if cleaned["review_id"].duplicated().any():
        raise ValueError("customer_reviews_complete.csv contains duplicate review_id values")

    invalid_customer = cleaned["customer_id"].isna() | ~cleaned[
        "customer_id"
    ].isin(customers["customer_id"])
    if invalid_customer.any():
        raise ValueError(
            f"customer_reviews_complete.csv contains {int(invalid_customer.sum())} "
            "missing or unknown customer IDs"
        )

    original_rating = cleaned["rating"].astype("string").str.strip()
    rating = pd.to_numeric(original_rating, errors="coerce")
    invalid_rating = (
        rating.isna() | ~rating.between(1, 5) | rating.mod(1).ne(0)
    )
    if invalid_rating.any():
        raise ValueError("customer_reviews_complete.csv contains invalid ratings")
    cleaned["rating"] = rating.astype("Int64")

    # Product-level analysis requires both fields, so incomplete product
    # records are excluded from the processed review dataset.
    cleaned = cleaned.dropna(
        subset=["product_name", "product_category"]
    ).copy()

    # Recover missing display names from the canonical customer record.
    customer_names = customers.set_index("customer_id")["full_name"]
    cleaned["full_name"] = cleaned["full_name"].fillna(
        cleaned["customer_id"].map(customer_names)
    )

    return cleaned.drop(columns="_date_validation_issues")


def main() -> None:
    """Validate dates and write the cleaned transaction dataset."""

    validated_data: dict[str, pd.DataFrame] = {}
    for filename, rule in DATE_RULES.items():
        source_path = RAW_DIR / filename
        if not source_path.exists():
            raise FileNotFoundError(f"Required raw dataset not found: {source_path}")

        cleaned = validate_dates(source_path, rule)
        invalid = cleaned["_date_validation_issues"].ne("")
        if invalid.any():
            examples = cleaned.loc[invalid, "_date_validation_issues"].head(5).tolist()
            raise ValueError(
                f"{filename} contains {int(invalid.sum())} rows with date errors. "
                f"Examples: {examples}"
            )
        validated_data[filename] = cleaned

    print(f"Date validation passed for all {len(DATE_RULES)} datasets.")

    customers = clean_customers(validated_data["customers.csv"])
    transactions = clean_transactions(validated_data["transactions.csv"])
    transactions, products, stores = build_product_and_store_dimensions(transactions)
    campaigns = clean_campaigns(validated_data["campaigns.csv"])
    interactions = clean_interactions(
        validated_data["interactions.csv"], customers
    )
    support_tickets = clean_support_tickets(
        validated_data["support_tickets.csv"], customers
    )
    reviews = clean_reviews(
        validated_data["customer_reviews_complete.csv"], customers
    )
    validate_customer_references(customers, transactions)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    customer_output_path = PROCESSED_DIR / "customers.csv"
    transaction_output_path = PROCESSED_DIR / "transactions.csv"
    campaign_output_path = PROCESSED_DIR / "campaigns.csv"
    product_output_path = PROCESSED_DIR / "products.csv"
    store_output_path = PROCESSED_DIR / "stores.csv"
    interaction_output_path = PROCESSED_DIR / "interactions.csv"
    support_output_path = PROCESSED_DIR / "support_tickets.csv"
    review_output_path = PROCESSED_DIR / "customer_reviews.csv"
    customers.to_csv(customer_output_path, index=False)
    transactions.to_csv(transaction_output_path, index=False)
    campaigns.to_csv(campaign_output_path, index=False)
    products.to_csv(product_output_path, index=False)
    stores.to_csv(store_output_path, index=False)
    interactions.to_csv(interaction_output_path, index=False)
    support_tickets.to_csv(support_output_path, index=False)
    reviews.to_csv(review_output_path, index=False)
    print(f"Cleaned customers written to: {customer_output_path}")
    print(f"Cleaned transactions written to: {transaction_output_path}")
    print(f"Cleaned campaigns written to: {campaign_output_path}")
    print(f"Derived products written to: {product_output_path}")
    print(f"Derived stores written to: {store_output_path}")
    print(f"Cleaned interactions written to: {interaction_output_path}")
    print(f"Cleaned support tickets written to: {support_output_path}")
    print(f"Cleaned customer reviews written to: {review_output_path}")


if __name__ == "__main__":
    main()
