from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.db import connect
from app.models import CreateSessionRequest, CreateSessionResponse
from app.sessions import create_session

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
