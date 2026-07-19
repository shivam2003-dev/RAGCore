import uuid

from api.routes.chat import _message_out
from database.base import utcnow
from models import Citation, Message


def test_message_content_is_redacted_when_a_cited_source_is_no_longer_authorized():
    message_id = uuid.uuid4()
    message = Message(
        id=message_id,
        conversation_id=uuid.uuid4(),
        role="assistant",
        content="Restricted operational evidence",
        timings={},
        evaluation={},
        created_at=utcnow(),
    )
    message.citations = [
        Citation(
            id=uuid.uuid4(),
            message_id=message_id,
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            marker=1,
            score=0.9,
            snippet="Restricted evidence",
        )
    ]

    output = _message_out(message, {})

    assert output.content == "This answer is unavailable because its source permissions changed."
    assert output.citations == []
