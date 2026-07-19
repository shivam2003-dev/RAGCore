from services.slack_normalizer import (
    SlackMessage,
    SlackSummary,
    SlackThread,
    SlackThreadNormalizer,
)


def _thread() -> SlackThread:
    return SlackThread(
        workspace_id="T123",
        channel_id="C123",
        channel_name="sre-help",
        thread_ts="1750000000.000001",
        thread_url="https://example.slack.com/archives/C123/p1750000000000001",
        messages=[
            SlackMessage(
                ts="1750000000.000001",
                user_id="U1",
                display_name="Asha",
                text="Why is api.prod.example.com returning ERR5029?",
            ),
            SlackMessage(
                ts="1750000010.000002",
                user_id="U2",
                display_name="Ben",
                text="Run `kubectl logs deploy/gateway` with --previous on 10.20.30.40.",
                reactions=3,
            ),
            SlackMessage(
                ts="1750000020.000003",
                user_id="U2",
                display_name="Ben",
                text="The gateway config was stale; rollout restart resolved ERR5029.",
            ),
        ],
    )


async def test_thread_normalization_schema_and_high_signal_bursts():
    async def summary_provider(_messages):
        return SlackSummary(
            summary="Gateway returned ERR5029 because its configuration was stale.",
            resolution="Roll out a gateway restart and validate the logs.",
        )

    normalized = await SlackThreadNormalizer(
        summary_provider=summary_provider,
        burst_min_messages=2,
        burst_rare_token_threshold=2,
        burst_reaction_threshold=2,
    ).normalize(_thread())

    assert normalized.searchable_question.startswith("Why is")
    assert normalized.resolution.startswith("Roll out")
    assert normalized.participants == [
        {"id": "U1", "display_name": "Asha"},
        {"id": "U2", "display_name": "Ben"},
    ]
    assert "api.prod.example.com" in normalized.systems
    assert "--previous" in normalized.code_references
    assert normalized.bursts
    assert "reaction boost" in normalized.bursts[0].reason
    assert "Raw thread" not in normalized.embedding_text()
    assert "## Raw thread" in normalized.render_markdown()
    assert normalized.thread_url in normalized.render_markdown()


async def test_summary_provider_failure_uses_deterministic_fallback():
    async def failing_provider(_messages):
        raise TimeoutError("summary timed out")

    normalized = await SlackThreadNormalizer(summary_provider=failing_provider).normalize(_thread())

    assert normalized.summary_fallback is True
    assert "ERR5029" in normalized.summary
    assert "resolved ERR5029" in normalized.resolution
