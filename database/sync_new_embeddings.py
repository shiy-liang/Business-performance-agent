"""Fill embeddings for newly imported structured records only."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.database import connect
from rag.utils.structured_vector_store import sync_support_ticket_embeddings


async def main() -> None:
    with connect() as connection:
        result = await sync_support_ticket_embeddings(connection)
        connection.commit()
        print(
            f"support_tickets synced={result.synced_count} "
            f"dimensions={result.embedding_dimensions} "
            f"model={result.embedding_model}"
        )


if __name__ == "__main__":
    asyncio.run(main())
