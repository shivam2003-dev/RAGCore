from fastapi import APIRouter, Response
from sqlalchemy import text

from api.deps import DbDep, RedisDep

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness(db: DbDep, redis: RedisDep, response: Response) -> dict[str, str]:
    checks = {"postgres": "ok", "redis": "ok"}
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        checks["postgres"] = "down"
    try:
        await redis.ping()
    except Exception:
        checks["redis"] = "down"
    if "down" in checks.values():
        response.status_code = 503
    return checks
