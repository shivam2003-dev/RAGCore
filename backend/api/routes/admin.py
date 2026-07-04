import uuid

from fastapi import APIRouter

from api.deps import CurrentUser, DbDep, require_role
from api.schemas import AuditLogOut, RoleUpdate, UserOut
from core.exceptions import NotFoundError
from models import Role
from repositories.audit import AuditLogRepository
from repositories.conversations import FeedbackRepository
from repositories.users import UserRepository

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[require_role(Role.ADMIN)])


@router.get("/users", response_model=list[UserOut])
async def list_users(user: CurrentUser, db: DbDep, limit: int = 100, offset: int = 0) -> list[UserOut]:
    users = await UserRepository(db).list_by_org(user.organization_id, limit=limit, offset=offset)
    return [UserOut.model_validate(u) for u in users]


@router.patch("/users/{user_id}/role", response_model=UserOut)
async def update_role(
    user_id: uuid.UUID, body: RoleUpdate, admin: CurrentUser, db: DbDep
) -> UserOut:
    repo = UserRepository(db)
    target = await repo.get(user_id)
    if target is None or target.organization_id != admin.organization_id:
        raise NotFoundError("User not found")
    target.role = Role(body.role)
    AuditLogRepository(db).record(
        action="user.role_change",
        resource_type="user",
        resource_id=str(user_id),
        org_id=admin.organization_id,
        actor_id=admin.id,
        detail=body.role,
    )
    await db.commit()
    return UserOut.model_validate(target)


@router.get("/audit-logs", response_model=list[AuditLogOut])
async def list_audit_logs(
    admin: CurrentUser, db: DbDep, limit: int = 100, offset: int = 0
) -> list[AuditLogOut]:
    logs = await AuditLogRepository(db).list_for_org(
        admin.organization_id, limit=min(limit, 500), offset=offset
    )
    return [AuditLogOut.model_validate(entry) for entry in logs]


@router.get("/feedback/stats")
async def feedback_stats(admin: CurrentUser, db: DbDep) -> dict[str, int]:
    return await FeedbackRepository(db).stats_for_org(admin.organization_id)
