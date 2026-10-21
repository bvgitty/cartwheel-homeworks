"""Homework 2, Part D: authentication tests for the cartwheel endpoint

These run offline: no Langfuse, Docker, or model key. They call the endpoint function 
directly, so they check the server's identity rules, not HTTP plumbing
"""

import pytest
from fastapi import HTTPException

from server import app as server_app


def test_create_session_rejects_role_mismatch(world: dict) -> None:
    # Arrange: Start with no sessions.
    server_app._SESSIONS.clear()

    # Act + Assert: user 1 is a shopper in the database, but claims "support".
    with pytest.raises(HTTPException) as exc:
        server_app.create_session(server_app.SessionCreate(user_id=1, role ="support"))

    assert exc.value.status_code == 403
    assert server_app._SESSIONS == {} # no session was created

def test_token_cannot_authorize_another_session(world: dict) -> None:
    # Arrange: two separate sessions for the same shopper.
    server_app._SESSIONS.clear()
    a = server_app.create_session(server_app.SessionCreate(user_id=1, role="shopper"))
    b = server_app.create_session(server_app.SessionCreate(user_id=1, role="shopper"))  

    # Act + Assert: session B, presented with session A's token.
    with pytest.raises(HTTPException) as exc:
        server_app._authorize(b["session_id"], "Bearer " + a["token"])

    assert exc.value.status_code == 403


class FakeSpan:
    """A stand-in for an OpenTelemetry span that records every attribute set on it."""

    def __init__(self) -> None:
        self.attributes: dict = {}

    def set_attribute(self, key, value) -> None:
        self.attributes[key] = value


def test_permission_denied_span_records_reason() -> None:
    from observability.instrument import _set_permission_denied_attributes

    span = FakeSpan()
    _set_permission_denied_attributes(
        span,
        {"ok": False, "error": "permission_denied", "reason": "role 'merchant' may not view order #4127"},
    )

    assert span.attributes["cartwheel.permission_denied"] is True
    assert span.attributes["cartwheel.permission_denied.reason"] == "role 'merchant' may not view order #4127"


def test_allowed_or_other_errors_are_not_permission_denied() -> None:
    from observability.instrument import _set_permission_denied_attributes

    for result in ({"ok": True, "order": {}}, {"ok": False, "error": "not_found", "reason": "no order"}):
        span = FakeSpan()
        _set_permission_denied_attributes(span, result)
        assert span.attributes["cartwheel.permission_denied"] is False
        assert "cartwheel.permission_denied.reason" not in span.attributes
