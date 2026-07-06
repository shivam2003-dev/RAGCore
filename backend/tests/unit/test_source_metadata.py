from knowledgebase.source_metadata import normalize_source_metadata


def test_upload_metadata_gets_enterprise_source_contract() -> None:
    metadata = normalize_source_metadata(
        None,
        source_type="upload",
        title="Architecture Notes.pdf",
        source_sha256="abc123",
        filename="Architecture Notes.pdf",
        file_type="pdf",
    )

    assert metadata["source"] == "upload"
    assert metadata["source_type"] == "upload"
    assert metadata["source_id"] == "abc123"
    assert metadata["source_title"] == "Architecture Notes.pdf"
    assert metadata["source_space"] == "uploads"
    assert metadata["connector"] == "upload"
    assert metadata["connector_scope"] == "uploads"
    assert metadata["acl"] == "user-upload"
    assert metadata["file_type"] == "pdf"
    assert metadata["source_inventory_key"] == "upload:uploads:abc123"


def test_connector_metadata_preserves_specific_fields_and_adds_inventory_key() -> None:
    metadata = normalize_source_metadata(
        {
            "jira_issue_key": "CVIR-100",
            "jira_project_key": "CVIR",
            "jira_issue_status": "In Progress",
            "custom_field": "kept",
        },
        source_type="jira",
        title="CVIR-100: Broker alarm",
        source_url="https://example.test/browse/CVIR-100",
        updated_at="2026-07-01T00:00:00+00:00",
        labels=["sre"],
        connector="jira",
    )

    assert metadata["source"] == "jira"
    assert metadata["source_id"] == "CVIR-100"
    assert metadata["source_space"] == "CVIR"
    assert metadata["project"] == "CVIR"
    assert metadata["status"] == "In Progress"
    assert metadata["labels"] == ["sre"]
    assert metadata["custom_field"] == "kept"
    assert metadata["source_inventory_key"] == "jira:CVIR:CVIR-100"
