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

