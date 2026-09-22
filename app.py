"""FastAPI entry point for the Business Performance Agent."""

from pathlib import Path
from hashlib import sha256

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.database import connect
from backend.middleware import register_logging_middleware
from backend.routers.action_center import router as action_center_router
from backend.routers.chat import router as chat_router
from backend.routers.finance import router as finance_router
from backend.routers.knowledge_files import router as knowledge_files_router
from backend.routers.knowledge_reviews import router as knowledge_reviews_router
from backend.routers.marketing import router as marketing_router
from backend.routers.products import router as products_router
from backend.routers.runs import router as runs_router
from backend.routers.sessions import router as sessions_router


app = FastAPI(
    title="Business Performance Agent API",
    version="0.1.0",
)
register_logging_middleware(app)

frontend_directory = Path(__file__).resolve().parent / "frontend"
app.mount("/static", StaticFiles(directory=frontend_directory), name="static")


@app.middleware("http")
async def frontend_cache_policy(request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response

app.include_router(finance_router)
app.include_router(action_center_router)
app.include_router(products_router)
app.include_router(marketing_router)
app.include_router(chat_router)
app.include_router(runs_router)
app.include_router(sessions_router)
app.include_router(knowledge_files_router)
app.include_router(knowledge_reviews_router)


@app.get("/", include_in_schema=False)
def dashboard() -> HTMLResponse:
    """Serve the dashboard from the same FastAPI application as the API."""

    assets = sorted(frontend_directory.glob("*.js")) + sorted(frontend_directory.glob("*.css"))
    assets += sorted((frontend_directory / "vendor").glob("chat-renderer.*"))
    version = sha256(b"".join(path.read_bytes() for path in assets)).hexdigest()[:16]
    html = (frontend_directory / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html.replace("__ASSET_VERSION__", version))


@app.get("/api/health")
def health() -> dict[str, object]:
    """Verify that FastAPI can reach the configured Supabase database."""

    try:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM transactions")
                transaction_count = int(cursor.fetchone()[0])
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed",
        ) from exc

    return {
        "status": "ok",
        "api": "running",
        "database": "connected",
        "transaction_count": transaction_count,
    }
