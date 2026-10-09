"""Explicit tables, JSON only for settings and pending operation payloads."""
import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, Integer, DateTime, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def uid():
    return uuid.uuid4().hex


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Business(Base):
    __tablename__ = 'businesses'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    settings: Mapped[dict] = mapped_column(JSON)


class Admin(Base):
    __tablename__ = 'admins'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    business_id: Mapped[str] = mapped_column(ForeignKey('businesses.id'), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)


class LoginSession(Base):
    __tablename__ = 'login_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    admin_id: Mapped[str] = mapped_column(ForeignKey('admins.id'))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Call(Base):
    __tablename__ = 'calls'
    __table_args__ = (UniqueConstraint('business_id', 'external_id'),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    business_id: Mapped[str] = mapped_column(ForeignKey('businesses.id'), index=True)
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    caller_phone: Mapped[str] = mapped_column(String(50), default='')
    direction: Mapped[str] = mapped_column(String(20), default='incoming')
    transport: Mapped[str] = mapped_column(String(30), default='text')
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default='active')
    outcome: Mapped[str] = mapped_column(String(40), default='inquiry')
    failure_reason: Mapped[str] = mapped_column(String(100), default='')
    summary: Mapped[str] = mapped_column(Text, default='')
    summary_status: Mapped[str] = mapped_column(String(30), default='pending')
    state: Mapped[dict] = mapped_column(JSON, default=dict)


class TranscriptTurn(Base):
    __tablename__ = 'transcript_turns'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    business_id: Mapped[str] = mapped_column(ForeignKey('businesses.id'), index=True)
    call_id: Mapped[str] = mapped_column(ForeignKey('calls.id'), index=True)
    role: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    delivery: Mapped[str] = mapped_column(String(30), default='text')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Appointment(Base):
    __tablename__ = 'appointments'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    business_id: Mapped[str] = mapped_column(ForeignKey('businesses.id'), index=True)
    call_id: Mapped[str | None] = mapped_column(ForeignKey('calls.id'), nullable=True)
    caller_name: Mapped[str] = mapped_column(String(120))
    caller_phone: Mapped[str] = mapped_column(String(50))
    caller_email: Mapped[str] = mapped_column(String(254), default='')
    service_id: Mapped[str] = mapped_column(String(40))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default='booked')
    calendar_event_id: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

class VapiAssistant(Base):
    __tablename__ = 'vapi_assistants'
    assistant_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    business_id: Mapped[str] = mapped_column(ForeignKey('businesses.id'), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    
class Operation(Base):
    __tablename__ = 'operations'
    __table_args__ = (UniqueConstraint('business_id', 'key'),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    business_id: Mapped[str] = mapped_column(ForeignKey('businesses.id'), index=True)
    key: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default='pending')
    result_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Message(Base):
    __tablename__ = 'messages'
    __table_args__ = (UniqueConstraint('business_id', 'key'),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    business_id: Mapped[str] = mapped_column(ForeignKey('businesses.id'), index=True)
    call_id: Mapped[str | None] = mapped_column(ForeignKey('calls.id'), nullable=True)
    key: Mapped[str] = mapped_column(String(100))
    caller_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    urgency: Mapped[str] = mapped_column(String(20), default='normal')
    escalated: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default='new')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CalendarConnection(Base):
    __tablename__ = 'calendar_connections'
    business_id: Mapped[str] = mapped_column(ForeignKey('businesses.id'), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), default='google')
    # unique: two businesses must never share one calendar by accident
    calendar_id: Mapped[str] = mapped_column(String(254), unique=True)
    status: Mapped[str] = mapped_column(String(20), default='unchecked')
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

def database(url=None):
    url = url or os.environ.get('DATABASE_URL')
    kwargs = {} if url.startswith('sqlite') else {'pool_size': 5, 'max_overflow': 5, 'pool_recycle': 300}
    engine = create_engine(url, pool_pre_ping=True, **kwargs,
        connect_args={'check_same_thread': False} if url.startswith('sqlite') else {})
    if not url:
        raise RuntimeError('Set DATABASE_URL and run migrations before starting Ava.')
    engine = create_engine(url, pool_pre_ping=True,
        connect_args={'check_same_thread': False} if url.startswith('sqlite') else {})
    return engine, sessionmaker(engine, expire_on_commit=False)



def record(row):
    result={column.name: getattr(row, column.name) for column in row.__table__.columns}
    # SQLite strips timezone metadata in offline tests. Our persisted timestamps
    # represent UTC; make the offset explicit in API output in either database.
    for key,value in result.items():
        if isinstance(value,datetime) and value.tzinfo is None:
            result[key]=value.replace(tzinfo=timezone.utc)
    return result
