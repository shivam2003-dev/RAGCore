from fastapi import APIRouter, Query

from api.deps import CurrentUser, DiscoverDep
from api.schemas import (
    DiscoverArticleOut,
    DiscoverBoardItemOut,
    DiscoverBoardPulseOut,
    DiscoverDepartmentOut,
    DiscoverFeedOut,
)
from services.discover_service import DiscoverArticle

router = APIRouter(prefix="/discover", tags=["discover"])


@router.get("/feed", response_model=DiscoverFeedOut)
async def discover_feed(
    user: CurrentUser,
    service: DiscoverDep,
    department: str = Query(default="for-you", min_length=1, max_length=80),
) -> DiscoverFeedOut:
    feed = await service.feed(user=user, department_id=department)
    return DiscoverFeedOut(
        generated_at=feed.generated_at,
        provider=feed.provider,
        configured=feed.configured,
        department=feed.department,
        departments=[
            DiscoverDepartmentOut(
                id=item.id,
                label=item.label,
                description=item.description,
                query=item.query,
            )
            for item in feed.departments
        ],
        lead=_article(feed.lead) if feed.lead is not None else None,
        articles=[_article(item) for item in feed.articles],
        alerts=[_article(item) for item in feed.alerts],
        research=[_article(item) for item in feed.research],
        board_pulse=DiscoverBoardPulseOut(
            jira_documents=feed.board_pulse.jira_documents,
            confluence_documents=feed.board_pulse.confluence_documents,
            upload_documents=feed.board_pulse.upload_documents,
            web_documents=feed.board_pulse.web_documents,
            latest_items=[
                DiscoverBoardItemOut(
                    title=item.title,
                    url=item.url,
                    source_type=item.source_type,
                    status=item.status,
                    updated_at=item.updated_at,
                )
                for item in feed.board_pulse.latest_items
            ],
        ),
        warnings=feed.warnings,
    )


def _article(item: DiscoverArticle) -> DiscoverArticleOut:
    return DiscoverArticleOut(
        id=item.id,
        title=item.title,
        url=item.url,
        source=item.source,
        summary=item.summary,
        section=item.section,
        department=item.department,
        published_at=item.published_at,
        score=item.score,
    )
