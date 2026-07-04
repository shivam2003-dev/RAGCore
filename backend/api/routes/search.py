from fastapi import APIRouter

from api.deps import CurrentUser, DbDep, RedisDep, RetrievalDep, SettingsDep
from api.schemas import SearchHitOut, SearchRequest, SearchResponse
from core.exceptions import NotFoundError
from repositories.knowledge import KnowledgeBaseRepository
from retrieval.context import RetrievalContext
from services.cache import ResponseCache

router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    user: CurrentUser,
    db: DbDep,
    retrieval: RetrievalDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> SearchResponse:
    kb = await KnowledgeBaseRepository(db).get(body.knowledge_base_id, user.organization_id)
    if kb is None:
        raise NotFoundError("Knowledge base not found")

    cache = ResponseCache(redis, settings.response_cache_ttl_seconds)
    cache_key = cache.key_for(
        "search", str(body.knowledge_base_id), str(body.collection_id), body.query, str(body.top_k)
    )
    if cached := await cache.get(cache_key):
        return SearchResponse.model_validate(cached)

    ctx = RetrievalContext(
        kb_id=body.knowledge_base_id,
        query=body.query,
        top_k=body.top_k,
        collection_id=body.collection_id,
    )
    ctx = await retrieval.run(ctx)
    response = SearchResponse(
        hits=[
            SearchHitOut(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                document_title=c.document_title,
                content=c.content,
                score=round(c.score, 4),
                dense_score=round(c.dense_score, 4),
                sparse_score=round(c.sparse_score, 4),
            )
            for c in ctx.chunks
        ],
        confidence=ctx.confidence,
        timings_ms=ctx.timings_ms,
    )
    await cache.set(cache_key, response.model_dump(mode="json"))
    return response
