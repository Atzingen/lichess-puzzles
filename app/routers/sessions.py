from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from app.config import settings
from app.db import connect
from app.models import (
    AppendAttemptRequest,
    CreateSessionRequest,
    CreateSessionResponse,
    EndSessionRequest,
    EndSessionResponse,
)
from app.sessions import (
    SessionEnded,
    SessionNotFound,
    append_attempt,
    create_session,
    end_session,
)

router = APIRouter(prefix="/api/sessions")


def _conn():
    conn = connect(settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


@router.post("", response_model=CreateSessionResponse, status_code=201)
def post_session(req: CreateSessionRequest, conn=Depends(_conn)) -> CreateSessionResponse:
    return create_session(conn, req)


@router.post("/{session_id}/attempts", status_code=204)
def post_attempt(
    session_id: str, req: AppendAttemptRequest, conn=Depends(_conn)
) -> Response:
    try:
        append_attempt(conn, session_id, req)
    except SessionNotFound:
        raise HTTPException(404, "session not found")
    except SessionEnded:
        raise HTTPException(409, "session has ended")
    return Response(status_code=204)


@router.post("/{session_id}/end", response_model=EndSessionResponse)
def post_end(
    session_id: str, req: EndSessionRequest, conn=Depends(_conn)
) -> EndSessionResponse:
    try:
        return end_session(conn, session_id, req)
    except SessionNotFound:
        raise HTTPException(404, "session not found")
    except SessionEnded:
        raise HTTPException(409, "session already ended")
