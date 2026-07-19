import uuid

from fastapi import APIRouter

from api.deps import AuthServiceDep, CurrentUser, DbDep, SettingsDep, require_role
from api.schemas import AuditLogOut, RoleUpdate, UserCreateRequest, UserOut
from core.exceptions import NotFoundError, ValidationError
from models import Role
from repositories.audit import AuditLogRepository
from repositories.conversations import FeedbackRepository
from repositories.users import UserRepository

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[require_role(Role.ADMIN)])


@router.get("/runtime-config")
async def runtime_config(_admin: CurrentUser, settings: SettingsDep) -> dict[str, object]:
    """Expose effective non-secret controls so the admin UI never shows placeholder values."""

    council_models = [item.strip() for item in settings.llm_council_models.split(",") if item.strip()]
    return {
        "app_env": settings.app_env,
        "auth_disabled": settings.auth_disabled,
        "retrieval": {
            "top_k": settings.retrieval_top_k,
            "candidate_k": settings.retrieval_candidate_k,
            "dense_weight": settings.retrieval_dense_weight,
            "sparse_weight": settings.retrieval_sparse_weight,
            "fusion_mode": settings.retrieval_fusion_mode,
            "rrf_smoothing_k": settings.retrieval_rrf_smoothing_k,
            "exact_identifier_enabled": settings.retrieval_exact_identifier_enabled,
            "rare_token_enabled": settings.retrieval_rare_token_enabled,
            "recency_decay_enabled": settings.retrieval_recency_decay_enabled,
            "model_reranker_enabled": settings.retrieval_model_reranker_enabled,
            "neighbor_expansion_enabled": settings.retrieval_neighbor_expansion_enabled,
        },
        "chunking": {
            "uploads": {
                "profile": "default-v1",
                "size_tokens": settings.chunk_size_tokens,
                "overlap_tokens": settings.chunk_overlap_tokens,
            },
            "jira": {
                "profile": "jira-relationship-comments-attachments-v5",
                "size_tokens": settings.jira_chunk_size_tokens,
                "overlap_tokens": settings.jira_chunk_overlap_tokens,
                "excluded_issue_types": [
                    item.strip() for item in settings.jira_exclude_issue_types.split(",") if item.strip()
                ],
                "comments_indexed": settings.jira_include_comments,
                "attachments_extracted": settings.jira_extract_attachments,
            },
            "confluence": {
                "profile": "confluence-heading-context-v2",
                "size_tokens": settings.confluence_chunk_size_tokens,
                "overlap_tokens": settings.confluence_chunk_overlap_tokens,
            },
        },
        "web": {
            "provider": settings.web_search_provider,
            "top_k": settings.web_search_top_k,
            "configured": bool(
                settings.web_search_provider not in {"", "disabled"}
                and (settings.web_search_provider not in {"brave", "tavily"} or settings.web_search_api_key)
            ),
        },
        "council": {
            "enabled": settings.llm_council_enabled,
            "models": council_models,
            "chair_model": settings.llm_council_chair_model or None,
        },
    }


@router.get("/users", response_model=list[UserOut])
async def list_users(user: CurrentUser, db: DbDep, limit: int = 100, offset: int = 0) -> list[UserOut]:
    users = await UserRepository(db).list_by_org(user.organization_id, limit=limit, offset=offset)
    return [UserOut.model_validate(u) for u in users]


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreateRequest,
    admin: CurrentUser,
    auth: AuthServiceDep,
) -> UserOut:
    user = await auth.create_user(
        actor=admin,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        role=Role(body.role),
    )
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}/role", response_model=UserOut)
async def update_role(
    user_id: uuid.UUID, body: RoleUpdate, admin: CurrentUser, db: DbDep, settings: SettingsDep
) -> UserOut:
    repo = UserRepository(db)
    target = await repo.get(user_id)
    if target is None or target.organization_id != admin.organization_id:
        raise NotFoundError("User not found")
    if target.email == settings.auth_super_admin_email.strip().lower() and body.role != Role.ADMIN.value:
        raise ValidationError("Super admin cannot be demoted")
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
async def list_audit_logs(admin: CurrentUser, db: DbDep, limit: int = 100, offset: int = 0) -> list[AuditLogOut]:
    logs = await AuditLogRepository(db).list_for_org(admin.organization_id, limit=min(limit, 500), offset=offset)
    return [AuditLogOut.model_validate(entry) for entry in logs]


@router.get("/feedback/stats")
async def feedback_stats(admin: CurrentUser, db: DbDep) -> dict[str, int]:
    return await FeedbackRepository(db).stats_for_org(admin.organization_id)
