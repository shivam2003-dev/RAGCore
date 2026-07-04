from services.confluence_service import _sync_limit as confluence_sync_limit
from services.jira_service import _sync_limit as jira_sync_limit


def test_atlassian_sync_defaults_to_unbounded_when_config_is_zero() -> None:
    assert confluence_sync_limit(None, 0) is None
    assert jira_sync_limit(None, 0) is None


def test_atlassian_sync_honors_explicit_and_configured_limits() -> None:
    assert confluence_sync_limit(250, 0) == 250
    assert jira_sync_limit(125, 0) == 125
    assert confluence_sync_limit(None, 5000) == 5000
    assert jira_sync_limit(None, 3000) == 3000
