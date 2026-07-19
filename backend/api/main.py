from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from api.deps import get_redis
from api.routes import (
    admin,
    auth,
    chat,
    confluence,
    discover,
    documents,
    evals,
    health,
    jira,
    knowledge_bases,
    projects,
    search,
    slack,
    web_search,
)
from api.routes import (
    metrics as product_metrics,
)
from core.config import get_settings
from core.exceptions import AppError
from core.logging import configure_logging, get_logger
from middleware.observability import ObservabilityMiddleware
from middleware.rate_limit import RateLimitMiddleware
from services.cache import RateLimiter

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    configure_logging()
    settings = get_settings()
    _init_otel(app, settings.otel_exporter_otlp_endpoint)
    log.info("startup", env=settings.app_env, llm=settings.llm_provider, embeddings=settings.embedding_provider)
    yield
    from database.session import engine

    await engine.dispose()
    await get_redis().aclose()


def _init_otel(app: FastAPI, endpoint: str) -> None:
    if not endpoint:
        return
    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider

    provider = TracerProvider(resource=Resource.create({"service.name": "kimbal-backend"}))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Kimbal Knowledge Hub API",
        version="0.1.0",
        description="Enterprise RAG platform: hybrid retrieval, grounded answers, citations.",
        lifespan=lifespan,
        docs_url="/docs",
    )

    app.add_middleware(ObservabilityMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        limiter=RateLimiter(get_redis(), settings.rate_limit_per_minute),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:3100"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    api = "/api/v1"
    app.include_router(health.router)
    app.include_router(auth.router, prefix=api)
    app.include_router(knowledge_bases.router, prefix=api)
    app.include_router(projects.router, prefix=api)
    app.include_router(documents.router, prefix=api)
    app.include_router(confluence.router, prefix=api)
    app.include_router(discover.router, prefix=api)
    app.include_router(evals.router, prefix=api)
    app.include_router(jira.router, prefix=api)
    app.include_router(slack.router, prefix=api)
    app.include_router(product_metrics.router, prefix=api)
    app.include_router(web_search.router, prefix=api)
    app.include_router(search.router, prefix=api)
    app.include_router(chat.router, prefix=api)
    app.include_router(admin.router, prefix=api)
    return app


app = create_app()
