"""Load cleaned and synthetic CSV files into PostgreSQL or Supabase."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg import sql

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASETS = [
    ("customers", PROJECT_ROOT / "data/processed/customers.csv"),
    ("products", PROJECT_ROOT / "data/processed/products.csv"),
    ("stores", PROJECT_ROOT / "data/processed/stores.csv"),
    ("campaigns", PROJECT_ROOT / "data/processed/campaigns.csv"),
    ("transactions", PROJECT_ROOT / "data/processed/transactions.csv"),
    ("interactions", PROJECT_ROOT / "data/processed/interactions.csv"),
    ("support_tickets", PROJECT_ROOT / "data/processed/support_tickets.csv"),
    ("customer_reviews", PROJECT_ROOT / "data/processed/customer_reviews.csv"),
    ("inventory", PROJECT_ROOT / "data/synthetic/inventory.csv"),
    ("expenses", PROJECT_ROOT / "data/synthetic/expenses.csv"),
    ("returns_refunds", PROJECT_ROOT / "data/synthetic/returns_refunds.csv"),
    ("campaign_attribution", PROJECT_ROOT / "data/synthetic/campaign_attribution.csv"),
]


def database_url() -> str:
    load_dotenv(PROJECT_ROOT / ".env")
    value = os.getenv("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is missing. Copy .env.example to .env first.")
    return value


def validate_files() -> None:
    missing = [str(path) for _, path in DATASETS if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Run clean_data.py and generate_synthetic_data.py first. "
            f"Missing files: {missing}"
        )


def load_csv(connection: psycopg.Connection, table: str, path: Path) -> int:
    """Use PostgreSQL COPY to load one CSV efficiently."""

    with path.open("r", encoding="utf-8", newline="") as source:
        columns = source.readline().strip().split(",")
        copy_statement = sql.SQL(
            "COPY {} ({}) FROM STDIN WITH (FORMAT CSV, NULL '')"
        ).format(
            sql.Identifier(table),
            sql.SQL(", ").join(map(sql.Identifier, columns)),
        )
        with connection.cursor().copy(copy_statement) as copy:
            while chunk := source.read(1024 * 1024):
                copy.write(chunk)

    with connection.cursor() as cursor:
        cursor.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table)))
        return int(cursor.fetchone()[0])


def main() -> None:
    validate_files()
    with psycopg.connect(database_url(), autocommit=False) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                TRUNCATE business_documents, campaign_attribution, returns_refunds,
                         expenses, inventory, customer_reviews, support_tickets,
                         interactions, transactions, campaigns, stores, products,
                         customers RESTART IDENTITY CASCADE
                """
            )
        for table, path in DATASETS:
            count = load_csv(connection, table, path)
            print(f"Loaded {table}: {count} rows")
        connection.commit()
    print("Database load completed successfully.")


if __name__ == "__main__":
    main()
