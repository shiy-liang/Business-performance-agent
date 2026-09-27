import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.database import connect

RUN_ID = "e802bf9b-3fb8-43f0-913b-6b65b95bdb01"

with connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT event_type, message, payload
            FROM run_events
            WHERE run_id = %s
            ORDER BY created_at
            """,
            (RUN_ID,),
        )
        rows = cur.fetchall()

print(f"total events: {len(rows)}")
for event_type, message, payload in rows:
    blob = json.dumps(payload, ensure_ascii=False) if payload is not None else ""
    if "validation" in event_type or "valid" in blob or "error" in blob.lower():
        print("=" * 80)
        print("EVENT:", event_type, "| MESSAGE:", message)
        if payload:
            print(blob[:4000])
