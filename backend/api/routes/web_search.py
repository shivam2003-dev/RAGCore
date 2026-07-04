from fastapi import APIRouter

from api.deps import CurrentUser, WebSearchDep
from api.schemas import WebSearchStatusOut

router = APIRouter(prefix="/web-search", tags=["web-search"])


@router.get("/status", response_model=WebSearchStatusOut)
async def web_search_status(_user: CurrentUser, web_search: WebSearchDep) -> WebSearchStatusOut:
    status = web_search.status()
    return WebSearchStatusOut(
        configured=status.configured,
        provider=status.provider,
        default_kb_name=status.default_kb_name,
        top_k=status.top_k,
        reason=status.reason,
    )
