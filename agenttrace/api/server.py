import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from agenttrace.config import settings
from agenttrace.db import init_db
from agenttrace.api.routes_traces import router as traces_router
from agenttrace.api.routes_incidents import router as incidents_router
from agenttrace.api.routes_regression import router as regression_router
from agenttrace.api.routes_stats import router as stats_router
from agenttrace.api.routes_auth import router as auth_router

def create_app() -> FastAPI:
    # Initialize DB tables
    init_db()

    # Pre-register demo agent runners if available
    try:
        import examples.customer_support_agent
    except ImportError:
        pass

    app = FastAPI(
        title="AgentTrace API",
        description="Deterministic Replay & Root-Cause Failure Investigator for AI Agents",
        version=settings.VERSION
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API Routers
    app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
    app.include_router(traces_router, prefix=settings.API_V1_PREFIX)
    app.include_router(incidents_router, prefix=settings.API_V1_PREFIX)
    app.include_router(regression_router, prefix=settings.API_V1_PREFIX)
    app.include_router(stats_router, prefix=settings.API_V1_PREFIX)

    # Mount static directory for Dashboard
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static")
    if not os.path.exists(static_dir):
        static_dir = os.path.join(os.getcwd(), "static")

    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @app.get("/", include_in_schema=False)
        def serve_landing_page():
            landing_path = os.path.join(static_dir, "landing.html")
            if os.path.exists(landing_path):
                return FileResponse(landing_path)
            index_path = os.path.join(static_dir, "index.html")
            if os.path.exists(index_path):
                return FileResponse(index_path)
            return {"message": "AgentTrace API is active. Landing page not found."}

        @app.get("/landing", include_in_schema=False)
        def serve_landing():
            landing_path = os.path.join(static_dir, "landing.html")
            if os.path.exists(landing_path):
                return FileResponse(landing_path)
            return {"message": "Landing page not found."}

        @app.get("/console", include_in_schema=False)
        @app.get("/app", include_in_schema=False)
        def serve_console():
            index_path = os.path.join(static_dir, "index.html")
            if os.path.exists(index_path):
                return FileResponse(index_path)
            return {"message": "AgentTrace Console index.html not found."}

    return app

app = create_app()
