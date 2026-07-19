import uuid

from scripts.run_mcp_server import handle_message, tool_definitions
from services.evidence_contract import EvidenceToolName


class FakeRestClient:
    def __init__(self, *, reject: bool = False) -> None:
        self.reject = reject
        self.calls = []

    def call_tool(self, *, name, request):  # type: ignore[no-untyped-def]
        if self.reject:
            raise RuntimeError("Kimbal authorization rejected the tool call (404)")
        self.calls.append((name, request))
        return {"tool": name.value, "project_id": str(request.project_id), "evidence": []}


def test_mcp_lists_only_read_only_primitives():
    definitions = tool_definitions()
    assert {item["name"] for item in definitions} == {item.value for item in EvidenceToolName}
    assert all(item["annotations"]["readOnlyHint"] is True for item in definitions)
    assert all(item["annotations"]["destructiveHint"] is False for item in definitions)


def test_mcp_validates_project_and_forwards_only_bounded_tool_input():
    project_id = uuid.uuid4()
    client = FakeRestClient()
    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "search_jira",
                "arguments": {"query": "CVIR-42", "project_id": str(project_id), "limit": 4},
            },
        },
        client,  # type: ignore[arg-type]
    )
    assert response and response["result"]["isError"] is False
    assert client.calls[0][0] is EvidenceToolName.SEARCH_JIRA
    assert client.calls[0][1].project_id == project_id

    bypass = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "search_knowledge",
                "arguments": {
                    "query": "secret",
                    "project_id": str(project_id),
                    "user_id": str(uuid.uuid4()),
                    "knowledge_base_ids": [str(uuid.uuid4())],
                },
            },
        },
        client,  # type: ignore[arg-type]
    )
    assert bypass and bypass["error"]["code"] == -32602
    assert len(client.calls) == 1


def test_mcp_surfaces_acl_rejection_as_error_instead_of_empty_evidence():
    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "search_slack",
                "arguments": {"query": "private incident", "project_id": str(uuid.uuid4())},
            },
        },
        FakeRestClient(reject=True),  # type: ignore[arg-type]
    )
    assert response and response["error"]["code"] == -32001
    assert "authorization rejected" in response["error"]["message"]
