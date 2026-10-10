"""SQLite persistence: users, agents, chat threads, grant verdicts."""

from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120), default="")
    language: Mapped[str] = mapped_column(String(5), default="uk")
    profile_name: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    agents: Mapped[list["Agent"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    preset: Mapped[str] = mapped_column(String(64), default="")  # preset slug it was created from
    kind: Mapped[str] = mapped_column(String(16), default="research")  # research | grants
    name: Mapped[dict[str, Any]] = mapped_column(default=dict)  # {"uk": ..., "en": ..., "de": ...}
    description: Mapped[dict[str, Any]] = mapped_column(default=dict)
    instructions: Mapped[str] = mapped_column(Text, default="")
    tools: Mapped[list[Any]] = mapped_column(default=list)
    skills: Mapped[list[Any]] = mapped_column(default=list)
    sources: Mapped[list[Any]] = mapped_column(default=list)
    org_profile: Mapped[str] = mapped_column(Text, default="")
    default_model: Mapped[str] = mapped_column(String(160), default="")
    answer_language: Mapped[str] = mapped_column(String(5), default="ui")  # ui | uk | en | de
    position: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    owner: Mapped[User] = relationship(back_populates="agents")


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    acp_session_id: Mapped[str] = mapped_column(String(80), default="")
    model_id: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan", order_by="Message.id")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[list[Any]] = mapped_column(default=list)  # tool-call timeline
    status: Mapped[str] = mapped_column(String(16), default="done")  # done | error | cancelled
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    thread: Mapped[Thread] = relationship(back_populates="messages")


class GrantResult(Base):
    __tablename__ = "grant_results"
    __table_args__ = (UniqueConstraint("user_id", "agent_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    thread_id: Mapped[int | None] = mapped_column(ForeignKey("threads.id", ondelete="SET NULL"), nullable=True)
    key: Mapped[str] = mapped_column(String(64))  # stable hash of url/title for upserts
    title: Mapped[str] = mapped_column(String(400))
    funder: Mapped[str] = mapped_column(String(200), default="")
    amount: Mapped[str] = mapped_column(String(120), default="")
    deadline: Mapped[str] = mapped_column(String(60), default="")
    eligibility: Mapped[str] = mapped_column(Text, default="")
    verdict: Mapped[str] = mapped_column(String(16))  # fits | next_year | not_for_us
    reasoning: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Artifact(Base):
    """Something an agent produced for the user in a chat: a dashboard, a document or an image."""
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), nullable=True,
                                                   index=True)
    kind: Mapped[str] = mapped_column(String(16))  # dashboard | document | image
    title: Mapped[str] = mapped_column(String(200), default="")
    filename: Mapped[str] = mapped_column(String(120), default="")
    mime: Mapped[str] = mapped_column(String(120), default="")
    size: Mapped[int] = mapped_column(default=0)
    file: Mapped[str] = mapped_column(String(40), default="")  # name inside the chat's artifact folder
    caption: Mapped[str] = mapped_column(String(500), default="")
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)  # dashboard spec / image source
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


_engine = None
_SessionLocal: sessionmaker | None = None


def init_db() -> None:
    global _engine, _SessionLocal
    settings = get_settings()
    _engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})

    @event.listens_for(_engine, "connect")
    def _pragmas(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(_engine, expire_on_commit=False)


def session_factory() -> sessionmaker:
    if _SessionLocal is None:
        init_db()
    return _SessionLocal  # type: ignore[return-value]


def get_db() -> Iterator[Session]:
    with session_factory()() as db:
        yield db
