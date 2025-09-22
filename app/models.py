from __future__ import annotations

import enum
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    support = "support"
    technician = "technician"


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)

    technicians = relationship("User", back_populates="team")
    orders = relationship("ServiceOrder", back_populates="team")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    is_active = Column(Boolean, default=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)

    team = relationship("Team", back_populates="technicians")
    observations = relationship("OrderObservation", back_populates="author")
    orders = relationship("ServiceOrder", back_populates="technician")


class Period(Base):
    __tablename__ = "periods"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_period_dates"),
    )

    orders = relationship("ServiceOrder", back_populates="period")


class ServiceOrderStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class ServiceOrder(Base):
    __tablename__ = "service_orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String(150), nullable=False)
    address = Column(String(255), nullable=False)
    installation_id = Column(String(100), nullable=False, index=True)
    plan = Column(String(100), nullable=False)
    scheduled_date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(Enum(ServiceOrderStatus), default=ServiceOrderStatus.pending, nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    technician_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    period_id = Column(Integer, ForeignKey("periods.id"), nullable=True)

    team = relationship("Team", back_populates="orders")
    technician = relationship("User", back_populates="orders")
    period = relationship("Period", back_populates="orders")
    observations = relationship(
        "OrderObservation", back_populates="order", cascade="all, delete-orphan"
    )
    photos = relationship("OrderPhoto", back_populates="order", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("installation_id", name="uq_installation_id"),
    )


class OrderObservation(Base):
    __tablename__ = "order_observations"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("service_orders.id"), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    note = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    order = relationship("ServiceOrder", back_populates="observations")
    author = relationship("User", back_populates="observations")


class OrderPhoto(Base):
    __tablename__ = "order_photos"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("service_orders.id"), nullable=False)
    file_path = Column(String(255), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    order = relationship("ServiceOrder", back_populates="photos")

    @property
    def filename(self) -> str:
        return Path(self.file_path).name


def ensure_default_teams(session) -> None:
    existing = {team.name for team in session.query(Team).all()}
    for idx in range(1, 5):
        name = f"Equipe {idx}"
        if name not in existing:
            session.add(Team(name=name))


def ensure_admin_user(session, username: str, password_hash: str) -> None:
    user = session.query(User).filter(User.username == username).one_or_none()
    if user is None:
        session.add(
            User(username=username, hashed_password=password_hash, role=UserRole.admin)
        )
