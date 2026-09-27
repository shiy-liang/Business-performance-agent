"""Load cleaned and synthetic CSV files into PostgreSQL or Supabase."""

from __future__ import annotations

import os
import argparse
import csv
import io
from pathlib import Path

import psycopg
from psycopg import sql

from config.settings import load_environment_settings

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
    value = load_environment_settings().database_url
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


def load_csv_incremental(
    connection: psycopg.Connection, table: str, path: Path
) -> int:
    """Load only new rows, preserving existing rows and vector columns."""

    staging = f"_{table}_staging"
    with path.open("r", encoding="utf-8", newline="") as source:
        content = source.read()
    reader = csv.DictReader(io.StringIO(content))
    columns = reader.fieldnames or []
    integer_columns = {
        "age",
        "customer_satisfaction_score",
        "resolution_time_hours",
        "return_quantity",
        "quantity",
    }
    if any(column in integer_columns for column in columns):
        rows = []
        for row in reader:
            for column in integer_columns.intersection(row):
                if row[column] not in (None, ""):
                    row[column] = str(int(float(row[column])))
            rows.append(row)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        content = output.getvalue()
    source = io.StringIO(content)
    try:
        source.readline()
        quoted_columns = sql.SQL(", ").join(map(sql.Identifier, columns))
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "CREATE TEMP TABLE {} (LIKE public.{} INCLUDING DEFAULTS) ON COMMIT DROP"
                ).format(sql.Identifier(staging), sql.Identifier(table))
            )
        copy_statement = sql.SQL(
            "COPY {} ({}) FROM STDIN WITH (FORMAT CSV, NULL '')"
        ).format(sql.Identifier(staging), quoted_columns)
        with connection.cursor().copy(copy_statement) as copy:
            while chunk := source.read(1024 * 1024):
                copy.write(chunk)
    finally:
        source.close()

    with connection.cursor() as cursor:
        target_columns = sql.SQL(", ").join(map(sql.Identifier, columns))
        cursor.execute(
            sql.SQL(
                "INSERT INTO public.{} ({}) SELECT {} FROM {} ON CONFLICT DO NOTHING"
            ).format(
                sql.Identifier(table),
                target_columns,
                target_columns,
                sql.Identifier(staging),
            )
        )
        return cursor.rowcount


def main() -> None:
    validate_files()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("incremental", "full"),
        default="incremental",
        help="Incremental append by default; use full only for an intentional reset.",
    )
    args = parser.parse_args()
    with psycopg.connect(database_url(), autocommit=False) as connection:
        if args.mode == "full":
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    TRUNCATE campaign_attribution, returns_refunds, expenses,
                             inventory, customer_reviews, support_tickets,
                             interactions, transactions, campaigns, stores,
                             products, customers RESTART IDENTITY CASCADE
                    """
                )
        for table, path in DATASETS:
            if args.mode == "incremental":
                count = load_csv_incremental(connection, table, path)
                print(f"Inserted {table}: {count} new rows")
            else:
                count = load_csv(connection, table, path)
                print(f"Loaded {table}: {count} rows")
        connection.commit()
    print(f"Database {args.mode} load completed successfully.")


if __name__ == "__main__":
    main()
