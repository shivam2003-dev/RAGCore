from services.jira_service import JiraBoard, JiraIssue, _issue_metadata, _render_issue_markdown


def test_jira_issue_rendering_indexes_assignment_and_status_fields() -> None:
    board = JiraBoard(id=154, name="DevOps Dashboard", type="kanban", url="https://example.test/board")
    issue = JiraIssue(
        id="10555",
        key="DEVO-10555",
        title="Broker installation",
        url="https://example.test/browse/DEVO-10555",
        issue_type="Task",
        status="To Do",
        status_category="To Do",
        status_category_key="new",
        priority="Medium",
        assignee="Shivam Kumar",
        assignee_email="s.kumar@kimbal.io",
        assignee_account_id="abc-123",
        reporter="Platform",
        reporter_email="platform@kimbal.io",
        reporter_account_id="reporter-123",
        created_at="2026-07-04T00:00:00.000+0000",
        updated_at="2026-07-04T01:00:00.000+0000",
        description="Install the broker service.",
        project_key="DEVO",
        project_name="DevOps",
    )

    rendered = _render_issue_markdown(board=board, issue=issue)
    metadata = _issue_metadata(board=board, issue=issue)

    assert "Assignee email:** s.kumar@kimbal.io" in rendered
    assert "Status category:** To Do" in rendered
    assert metadata["jira_assignee_email"] == "s.kumar@kimbal.io"
    assert metadata["jira_issue_status_category_key"] == "new"
