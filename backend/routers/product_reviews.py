"""Company-wide customer reviews linked to catalog products."""

from __future__ import annotations

from datetime import date

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row

from backend.database import connect


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


REVIEW_PRODUCTS_SQL = """
SELECT
    p.product_id,
    p.product_name,
    p.product_category,
    COUNT(r.review_id)::bigint AS review_count,
    COUNT(r.review_id) FILTER (WHERE r.rating <= 2)::bigint AS low_rating_count,
    COUNT(r.review_id) FILTER (WHERE r.rating >= 4)::bigint AS high_rating_count,
    ROUND(AVG(r.rating)::numeric, 2) AS average_rating
FROM products p
LEFT JOIN customer_reviews r
  ON r.product_name = p.product_name
 AND r.product_category = p.product_category
 AND r.review_date >= %(period_start)s::date
 AND r.review_date < %(period_end)s::date
GROUP BY p.product_id, p.product_name, p.product_category
ORDER BY low_rating_count DESC, review_count DESC, p.product_name, p.product_id
"""


PRODUCT_REVIEWS_SQL = """
SELECT review_id, rating, review_title, review_text, review_date
FROM customer_reviews
WHERE product_name = %(product_name)s
  AND product_category = %(product_category)s
  AND review_date >= %(period_start)s::date
  AND review_date < %(period_end)s::date
  AND (%(low_only)s::boolean IS FALSE OR rating <= 2)
ORDER BY review_date DESC, review_id DESC
LIMIT 30
"""


def _period_bounds(month: str | None, start_date: date | None, end_date: date | None) -> tuple[date, date]:
    if start_date or end_date:
        if not start_date or not end_date or end_date <= start_date:
            raise HTTPException(status_code=422, detail="start_date and end_date must define a valid range")
        return start_date, end_date
    if not month:
        raise HTTPException(status_code=422, detail="month or start_date/end_date is required")
    try:
        start = date.fromisoformat(f"{month}-01")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="month must be a valid calendar month") from exc
    end = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
    return start, end


@router.get("/product-reviews")
def review_products(
    month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    """Summarize selected-month reviews for every catalog product."""

    start, end = _period_bounds(month, start_date, end_date)
    try:
        with connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(REVIEW_PRODUCTS_SQL, {"period_start": start, "period_end": end})
            rows = cursor.fetchall()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Database query failed") from exc

    return {
        "month": month,
        "start_date": start.isoformat(),
        "end_date": (end - date.resolution).isoformat(),
        "scope": "Company-wide; reviews have no store field",
        "products": [
            {
                "product_id": row["product_id"],
                "product_name": row["product_name"],
                "product_category": row["product_category"],
                "review_count": row["review_count"],
                "low_rating_count": row["low_rating_count"],
                "high_rating_count": row["high_rating_count"],
                "average_rating": float(row["average_rating"]) if row["average_rating"] is not None else None,
            }
            for row in rows
        ],
    }


@router.get("/products/{product_id}/reviews")
def product_reviews(
    product_id: str,
    month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    start_date: date | None = None,
    end_date: date | None = None,
    low_only: bool = False,
) -> dict[str, object]:
    """Return the latest selected-month review comments without customer identifiers."""

    start, end = _period_bounds(month, start_date, end_date)
    try:
        with connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT product_id, product_name, product_category FROM products WHERE product_id = %s",
                (product_id,),
            )
            product = cursor.fetchone()
            if product is None:
                raise HTTPException(status_code=404, detail="Product not found")
            cursor.execute(
                PRODUCT_REVIEWS_SQL,
                {
                    "product_name": product["product_name"],
                    "product_category": product["product_category"],
                    "period_start": start,
                    "period_end": end,
                    "low_only": low_only,
                },
            )
            rows = cursor.fetchall()
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Database query failed") from exc

    return {
        "product": dict(product),
        "month": month,
        "start_date": start.isoformat(),
        "end_date": (end - date.resolution).isoformat(),
        "low_only": low_only,
        "limit": 30,
        "reviews": [
            {
                "review_id": row["review_id"],
                "rating": row["rating"],
                "review_title": row["review_title"],
                "review_text": row["review_text"],
                "review_date": row["review_date"].isoformat(),
            }
            for row in rows
        ],
    }
