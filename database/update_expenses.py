"""Safely update existing synthetic expense rows without reloading other tables."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import connect  # noqa: E402


EXPENSES_CSV = PROJECT_ROOT / "data" / "synthetic" / "expenses.csv"


def main() -> None:
    if not EXPENSES_CSV.exists():
        raise FileNotFoundError("Run generate_synthetic_data.py first")

    with EXPENSES_CSV.open("r", encoding="utf-8", newline="") as source:
        expected_rows = sum(1 for _ in csv.reader(source)) - 1

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TEMP TABLE staged_expenses
                (LIKE expenses INCLUDING DEFAULTS)
                ON COMMIT DROP
                """
            )

            with EXPENSES_CSV.open("r", encoding="utf-8", newline="") as source:
                header = source.readline()
                if not header:
                    raise ValueError("expenses.csv is empty")
                with cursor.copy(
                    """
                    COPY staged_expenses (
                        expense_id, expense_date, store_id,
                        expense_category, amount, is_synthetic
                    ) FROM STDIN WITH (FORMAT CSV, NULL '')
                    """
                ) as copy:
                    while chunk := source.read(1024 * 1024):
                        copy.write(chunk)

            cursor.execute("SELECT COUNT(*) FROM staged_expenses")
            staged_rows = int(cursor.fetchone()[0])
            if staged_rows != expected_rows:
                raise RuntimeError(
                    f"Staged {staged_rows} rows, expected {expected_rows}; no update applied"
                )

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM staged_expenses staged
                JOIN expenses current USING (expense_id)
                """
            )
            matched_rows = int(cursor.fetchone()[0])
            if matched_rows != staged_rows:
                raise RuntimeError(
                    f"Only {matched_rows} of {staged_rows} expense IDs exist; no update applied"
                )

            cursor.execute(
                """
                UPDATE expenses current
                SET expense_date = staged.expense_date,
                    store_id = staged.store_id,
                    expense_category = staged.expense_category,
                    amount = staged.amount,
                    is_synthetic = staged.is_synthetic
                FROM staged_expenses staged
                WHERE current.expense_id = staged.expense_id
                """
            )
            updated_rows = cursor.rowcount

        connection.commit()

    print(f"Updated expenses safely: {updated_rows} rows")


if __name__ == "__main__":
    main()
