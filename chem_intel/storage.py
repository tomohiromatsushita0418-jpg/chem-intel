"""検索履歴・レポートの永続化。

DATABASE_URL があれば Postgres 等、無ければローカル SQLite を使う。
SQLAlchemy で両対応。クラウド(Streamlit)では DATABASE_URL に Supabase 等の
Postgres を設定すると再起動後も履歴が残る。
"""
from __future__ import annotations

import datetime
import json
from dataclasses import dataclass

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    desc,
    or_,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import Settings

Base = declarative_base()


class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    query = Column(String(512))
    query_type = Column(String(32))
    display_name = Column(String(512))
    cas = Column(String(64))
    hs_code = Column(String(32))
    formula = Column(String(128))
    markdown = Column(Text)
    citations_json = Column(Text)  # list[{title,url}]


@dataclass
class HistoryItem:
    id: int
    created_at: datetime.datetime
    query: str
    display_name: str
    cas: str | None
    hs_code: str | None


_engine = None
_Session = None


def _db_url(settings: Settings) -> str:
    if settings.database_url:
        url = settings.database_url
        # Streamlit Cloud / Supabase 互換: postgres:// → postgresql://
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url
    import os

    path = os.path.join(os.path.expanduser("~"), ".chem_intel", "history.db")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return f"sqlite:///{path}"


def init(settings: Settings):
    global _engine, _Session
    if _engine is None:
        _engine = create_engine(_db_url(settings), future=True)
        Base.metadata.create_all(_engine)
        _Session = sessionmaker(bind=_engine, future=True)
    return _Session


def save_report(
    settings: Settings,
    *,
    query: str,
    query_type: str,
    display_name: str,
    cas: str | None,
    hs_code: str | None,
    formula: str | None,
    markdown: str,
    citations: list[dict],
) -> int:
    Session = init(settings)
    with Session() as s:
        rep = Report(
            query=query,
            query_type=query_type,
            display_name=display_name,
            cas=cas,
            hs_code=hs_code,
            formula=formula,
            markdown=markdown,
            citations_json=json.dumps(citations, ensure_ascii=False),
        )
        s.add(rep)
        s.commit()
        return rep.id


def list_history(settings: Settings, search: str | None = None, limit: int = 100) -> list[HistoryItem]:
    Session = init(settings)
    with Session() as s:
        q = s.query(Report)
        if search:
            like = f"%{search.strip()}%"
            q = q.filter(
                or_(
                    Report.query.ilike(like),
                    Report.display_name.ilike(like),
                    Report.cas.ilike(like),
                    Report.hs_code.ilike(like),
                )
            )
        rows = q.order_by(desc(Report.created_at)).limit(limit).all()
        return [
            HistoryItem(
                id=r.id,
                created_at=r.created_at,
                query=r.query,
                display_name=r.display_name or r.query,
                cas=r.cas,
                hs_code=r.hs_code,
            )
            for r in rows
        ]


def get_report(settings: Settings, report_id: int) -> Report | None:
    Session = init(settings)
    with Session() as s:
        return s.get(Report, report_id)


def delete_report(settings: Settings, report_id: int) -> None:
    Session = init(settings)
    with Session() as s:
        rep = s.get(Report, report_id)
        if rep:
            s.delete(rep)
            s.commit()
