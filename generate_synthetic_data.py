"""Generate deterministic synthetic datasets for the project demo.

Run ``python clean_data.py`` first. This script reads only processed datasets
and writes clearly labelled synthetic data under ``data/synthetic``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
SYNTHETIC_DIR = PROJECT_ROOT / "data" / "synthetic"
RANDOM_SEED = 42


def load_processed() -> dict[str, pd.DataFrame]:
    """Load the clean datasets required by the generators."""

    filenames = ["transactions.csv", "products.csv", "stores.csv", "campaigns.csv"]
    missing = [name for name in filenames if not (PROCESSED_DIR / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing processed files {missing}. Run 'python clean_data.py' first."
        )

    return {
        Path(name).stem: pd.read_csv(PROCESSED_DIR / name)
        for name in filenames
    }


def enrich_products_with_costs(
    transactions: pd.DataFrame,
    products: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Add one stable synthetic unit cost to every known product."""

    average_prices = (
        transactions.dropna(subset=["product_id"])
        .groupby("product_id", as_index=False)["price"]
        .mean()
        .rename(columns={"price": "average_selling_price"})
    )
    enriched = products[["product_id", "product_name", "product_category"]].merge(
        average_prices, on="product_id", how="left", validate="one_to_one"
    )
    if enriched["average_selling_price"].isna().any():
        raise ValueError("A product has no selling price for cost estimation")

    # Cost is intentionally synthetic: 45%-75% of each product's observed
    # average selling price, with a fixed seed for reproducible output.
    enriched["cost_ratio"] = rng.uniform(0.45, 0.75, size=len(enriched)).round(4)
    enriched["average_selling_price"] = enriched["average_selling_price"].round(2)
    enriched["unit_cost"] = (
        enriched["average_selling_price"] * enriched["cost_ratio"]
    ).round(2)
    # Only the cost fields are synthetic; product names and categories come
    # from the cleaned transaction data.
    enriched["is_cost_synthetic"] = True
    return enriched[
        [
            "product_id",
            "product_name",
            "product_category",
            "average_selling_price",
            "cost_ratio",
            "unit_cost",
            "is_cost_synthetic",
        ]
    ]


def generate_inventory(
    transactions: pd.DataFrame, products: pd.DataFrame, stores: pd.DataFrame, rng: np.random.Generator
) -> pd.DataFrame:
    """Create one inventory snapshot for observed product/store combinations."""

    combinations = (
        transactions[["product_id", "store_id"]]
        .dropna()
        .drop_duplicates()
        .sort_values(["store_id", "product_id"])
        .reset_index(drop=True)
    )
    snapshot_date = pd.to_datetime(transactions["transaction_date"]).max()
    combinations.insert(
        0, "inventory_id", [f"INV{i:05d}" for i in range(1, len(combinations) + 1)]
    )
    combinations["stock_quantity"] = rng.integers(0, 501, size=len(combinations))
    combinations["reorder_level"] = rng.integers(20, 101, size=len(combinations))
    days_since_restock = rng.integers(1, 91, size=len(combinations))
    combinations["last_restock_date"] = (
        snapshot_date - pd.to_timedelta(days_since_restock, unit="D")
    ).strftime("%Y-%m-%d")
    combinations["snapshot_date"] = snapshot_date.strftime("%Y-%m-%d")
    combinations["needs_reorder"] = (
        combinations["stock_quantity"] <= combinations["reorder_level"]
    )
    combinations["is_synthetic"] = True

    valid_products = set(products["product_id"])
    valid_stores = set(stores["store_id"])
    if not combinations["product_id"].isin(valid_products).all():
        raise ValueError("Synthetic inventory contains an unknown product_id")
    if not combinations["store_id"].isin(valid_stores).all():
        raise ValueError("Synthetic inventory contains an unknown store_id")
    return combinations


def generate_expenses(
    transactions: pd.DataFrame, stores: pd.DataFrame, rng: np.random.Generator
) -> pd.DataFrame:
    """Create store expenses scaled to each store's monthly sales.

    The source data has relatively low sales per physical location. Fixed random
    ranges made operating costs larger than company revenue in every month, so
    the prototype now generates each category as a modest share of that store's
    sales. Campaign budget remains the separate marketing-cost source.
    """

    transaction_dates = pd.to_datetime(transactions["transaction_date"])
    months = pd.date_range(
        transaction_dates.min().to_period("M").to_timestamp(),
        transaction_dates.max().to_period("M").to_timestamp(),
        freq="MS",
    )
    category_ratios = {
        "physical": {
            "payroll": 0.045,
            "rent": 0.020,
            "logistics": 0.015,
            "utilities": 0.006,
            "other": 0.009,
        },
        "online": {
            "payroll": 0.035,
            "logistics": 0.025,
            "other": 0.010,
        },
    }

    sales = transactions.copy()
    sales["expense_month"] = pd.to_datetime(sales["transaction_date"]).dt.to_period(
        "M"
    ).dt.to_timestamp()
    monthly_store_sales = (
        sales.dropna(subset=["store_id"])
        .groupby(["store_id", "expense_month"])["net_sales"]
        .sum()
    )

    rows: list[dict[str, object]] = []
    expense_number = 1
    for store in stores.itertuples(index=False):
        ratios = category_ratios[store.store_type]
        for month in months:
            store_sales = float(monthly_store_sales.get((store.store_id, month), 0))
            for category, ratio in ratios.items():
                variation = float(rng.uniform(0.90, 1.10))
                rows.append(
                    {
                        "expense_id": f"EXP{expense_number:06d}",
                        "expense_date": month.strftime("%Y-%m-%d"),
                        "store_id": store.store_id,
                        "expense_category": category,
                        "amount": round(store_sales * ratio * variation, 2),
                        "is_synthetic": True,
                    }
                )
                expense_number += 1
    return pd.DataFrame(rows)


def generate_returns(
    transactions: pd.DataFrame, rng: np.random.Generator, return_rate: float = 0.05
) -> pd.DataFrame:
    """Create refunds for a deterministic sample of valid transactions."""

    sample_size = round(len(transactions) * return_rate)
    selected_indices = rng.choice(transactions.index, size=sample_size, replace=False)
    selected = transactions.loc[selected_indices].copy().reset_index(drop=True)
    reasons = np.array(
        ["damaged", "defective", "wrong_item", "not_as_expected", "changed_mind"]
    )
    statuses = rng.choice(
        ["completed", "pending"], size=len(selected), p=[0.85, 0.15]
    )
    return_quantities = [
        int(rng.integers(1, int(quantity) + 1)) for quantity in selected["quantity"]
    ]
    requested = (
        selected["net_sales"] / selected["quantity"] * return_quantities
    ).round(2)
    return_dates = pd.to_datetime(selected["transaction_date"]) + pd.to_timedelta(
        rng.integers(1, 31, size=len(selected)), unit="D"
    )

    result = pd.DataFrame(
        {
            "return_id": [f"RET{i:05d}" for i in range(1, len(selected) + 1)],
            "transaction_id": selected["transaction_id"],
            "customer_id": selected["customer_id"],
            "return_date": return_dates.dt.strftime("%Y-%m-%d"),
            "return_quantity": return_quantities,
            "return_reason": rng.choice(reasons, size=len(selected)),
            "refund_status": statuses,
            "requested_refund_amount": requested,
            "refund_amount": requested.where(statuses == "completed"),
            "is_synthetic": True,
        }
    )
    return result


def generate_campaign_attribution(
    transactions: pd.DataFrame, campaigns: pd.DataFrame, rng: np.random.Generator
) -> pd.DataFrame:
    """Attribute a subset of eligible transactions to one active campaign."""

    campaign_dates = campaigns.copy()
    campaign_dates["start_date"] = pd.to_datetime(campaign_dates["start_date"])
    campaign_dates["end_date"] = pd.to_datetime(campaign_dates["end_date"])

    candidate_count = round(len(transactions) * 0.25)
    candidate_indices = rng.choice(
        transactions.index, size=candidate_count, replace=False
    )
    rows: list[dict[str, object]] = []
    for transaction in transactions.loc[candidate_indices].itertuples(index=False):
        transaction_date = pd.Timestamp(transaction.transaction_date)
        active = campaign_dates.loc[
            campaign_dates["start_date"].le(transaction_date)
            & campaign_dates["end_date"].ge(transaction_date)
        ]
        if active.empty:
            continue
        campaign = active.iloc[int(rng.integers(0, len(active)))]
        rows.append(
            {
                "attribution_id": f"ATT{len(rows) + 1:06d}",
                "transaction_id": transaction.transaction_id,
                "campaign_id": campaign["campaign_id"],
                "attribution_date": transaction_date.strftime("%Y-%m-%d"),
                "attribution_method": "synthetic_last_touch",
                "attributed_revenue": transaction.net_sales,
                "is_synthetic": True,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    """Generate and save every synthetic demo dataset."""

    data = load_processed()
    rng = np.random.default_rng(RANDOM_SEED)
    cost_rng = np.random.default_rng(RANDOM_SEED + 100)
    SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)

    products_with_costs = enrich_products_with_costs(
        data["transactions"], data["products"], cost_rng
    )
    products_with_costs.to_csv(PROCESSED_DIR / "products.csv", index=False)
    print(f"Updated products.csv with synthetic costs: {len(products_with_costs)} rows")

    generated = {
        "inventory.csv": generate_inventory(
            data["transactions"], products_with_costs, data["stores"], rng
        ),
        "expenses.csv": generate_expenses(data["transactions"], data["stores"], rng),
        "returns_refunds.csv": generate_returns(data["transactions"], rng),
        "campaign_attribution.csv": generate_campaign_attribution(
            data["transactions"], data["campaigns"], rng
        ),
    }

    for filename, frame in generated.items():
        frame.to_csv(SYNTHETIC_DIR / filename, index=False)
        print(f"Generated {filename}: {len(frame)} rows")


if __name__ == "__main__":
    main()
