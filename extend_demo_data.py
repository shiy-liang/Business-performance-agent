"""Extend the checked-in demo datasets with deterministic synthetic recent data."""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
END = pd.Timestamp("2026-09-30")
START = pd.Timestamp("2025-03-01")
RNG = np.random.default_rng(20260927)


def read(name: str, synthetic: bool = False) -> pd.DataFrame:
    folder = "synthetic" if synthetic else "processed"
    return pd.read_csv(DATA / folder / name)


def main() -> None:
    tx = read("transactions.csv")
    tx["transaction_date"] = pd.to_datetime(tx["transaction_date"])
    customers = read("customers.csv")
    products = read("products.csv")
    stores = read("stores.csv")

    source = tx[tx.transaction_date >= "2024-03-01"].copy()
    months = pd.date_range(START, END, freq="MS")
    new_tx = []
    next_id = len(tx) + 1
    for month in months:
        sample = source.sample(n=max(300, round(len(source) / 12)), replace=True, random_state=int(month.month + month.year))
        sample = sample.copy()
        offsets = RNG.integers(0, month.days_in_month, len(sample))
        sample["transaction_date"] = month + pd.to_timedelta(offsets, unit="D")
        sample["transaction_id"] = [f"TXN{next_id + i:07d}" for i in range(len(sample))]
        next_id += len(sample)
        sample["customer_id"] = RNG.choice(customers.customer_id, len(sample))
        sample["product_id"] = RNG.choice(products.product_id, len(sample))
        product_map = products.set_index("product_id")
        sample["product_name"] = sample.product_id.map(product_map.product_name)
        sample["product_category"] = sample.product_id.map(product_map.product_category)
        sample["quantity"] = RNG.integers(1, 5, len(sample))
        sample["price"] = sample.product_id.map(product_map.average_selling_price).round(2)
        sample["discount_applied"] = RNG.choice([0, 5, 10, 15], len(sample), p=[.55, .25, .15, .05])
        sample["gross_sales"] = (sample.quantity * sample.price).round(2)
        sample["discount_amount"] = (sample.gross_sales * sample.discount_applied / 100).round(2)
        sample["net_sales"] = (sample.gross_sales - sample.discount_amount).round(2)
        sample["store_id"] = RNG.choice(stores.store_id, len(sample))
        store_map = stores.set_index("store_id")
        sample["store_location"] = sample.store_id.map(store_map.store_location)
        new_tx.append(sample[tx.columns])
    tx = pd.concat([tx, *new_tx], ignore_index=True)
    tx["transaction_date"] = tx.transaction_date.dt.strftime("%Y-%m-%d")
    tx.to_csv(DATA / "processed/transactions.csv", index=False)

    interactions = read("interactions.csv")
    rows = []
    for month in months:
        n = 900
        rows.append(pd.DataFrame({
            "interaction_id": [f"INT{len(interactions)+sum(map(len, rows))+i+1:07d}" for i in range(n)],
            "customer_id": RNG.choice(customers.customer_id, n),
            "channel": RNG.choice(["web", "mobile_app", "in_store_kiosk"], n),
            "interaction_type": RNG.choice(["page_view", "product_view", "add_to_cart", "search", "purchase"], n),
            "interaction_date": (month + pd.to_timedelta(RNG.integers(0, month.days_in_month, n), unit="D")).strftime("%Y-%m-%d"),
            "duration": RNG.uniform(5, 300, n).round(2),
            "page_or_product": RNG.choice(products.product_name, n),
            "session_id": [f"SES{month.strftime('%Y%m')}{i:05d}" for i in range(n)],
        }))
    pd.concat([interactions, *rows], ignore_index=True).to_csv(DATA / "processed/interactions.csv", index=False)

    tickets = read("support_tickets.csv")
    rows = []
    for month in months:
        n = 35
        submit = month + pd.to_timedelta(RNG.integers(0, month.days_in_month, n), unit="D")
        resolved = submit + pd.to_timedelta(RNG.integers(1, 8, n), unit="D")
        rows.append(pd.DataFrame({
            "ticket_id": [f"TKT{len(tickets)+sum(map(len, rows))+i+1:06d}" for i in range(n)],
            "customer_id": RNG.choice(customers.customer_id, n), "issue_category": RNG.choice(["shipping", "technical", "billing", "returns"], n),
            "priority": RNG.choice(["low", "medium", "high"], n, p=[.5,.4,.1]), "submission_date": submit.strftime("%Y-%m-%d"),
            "resolution_date": resolved.strftime("%Y-%m-%d"), "resolution_status": "resolved", "resolution_time_hours": RNG.uniform(4, 96, n).round(2),
            "customer_satisfaction_score": RNG.integers(2, 6, n), "notes": "Synthetic recent support ticket",
        }))
    pd.concat([tickets, *rows], ignore_index=True).to_csv(DATA / "processed/support_tickets.csv", index=False)

    # Rebuild all derived synthetic tables from the now-extended transactions.
    import generate_synthetic_data
    generate_synthetic_data.main()
    print(f"transactions={len(tx)} latest={tx.transaction_date.max()}")
    print(f"interactions={len(interactions)+sum(map(len, rows))}")


if __name__ == "__main__":
    main()
