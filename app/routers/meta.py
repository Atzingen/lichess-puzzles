from fastapi import APIRouter, Depends

from app.config import settings
from app.db import connect
from app.models import Stats
from app.queries import get_stats, list_themes, list_openings

router = APIRouter(prefix="/api")


def _conn():
    conn = connect(settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


@router.get("/stats", response_model=Stats)
def stats(conn=Depends(_conn)) -> Stats:
    return get_stats(conn)


@router.get("/themes", response_model=list[str])
def themes(conn=Depends(_conn)) -> list[str]:
    return list_themes(conn)


@router.get("/openings", response_model=list[str])
def openings(conn=Depends(_conn)) -> list[str]:
    return list_openings(conn)
