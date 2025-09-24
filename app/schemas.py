from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import ServiceOrderStatus, UserRole


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: str | None = None


class UserBase(BaseModel):
    username: str
    role: UserRole
    team_id: Optional[int] = None


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    role: UserRole
    team_id: Optional[int] = None


class UserRead(UserBase):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class PeriodBase(BaseModel):
    name: str
    start_date: date
    end_date: date


class PeriodCreate(PeriodBase):
    pass


class PeriodRead(PeriodBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class ObservationRead(BaseModel):
    id: int
    author_id: int
    note: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PhotoRead(BaseModel):
    id: int
    file_path: str
    filename: str
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ServiceOrderBase(BaseModel):
    customer_name: str
    address: str
    installation_id: str
    plan: str
    scheduled_date: date
    team_id: Optional[int] = None
    technician_id: Optional[int] = None
    period_id: Optional[int] = None


class ServiceOrderCreate(ServiceOrderBase):
    pass


class ServiceOrderUpdate(BaseModel):
    status: Optional[ServiceOrderStatus] = None
    technician_id: Optional[int] = None
    team_id: Optional[int] = None
    scheduled_date: Optional[date] = None
    period_id: Optional[int] = None


class ServiceOrderRead(ServiceOrderBase):
    id: int
    status: ServiceOrderStatus
    created_at: datetime
    observations: List[ObservationRead] = Field(default_factory=list)
    photos: List[PhotoRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ObservationCreate(BaseModel):
    note: str = Field(..., min_length=1)


class TeamBase(BaseModel):
    name: str


class TeamCreate(TeamBase):
    pass


class TeamRead(TeamBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
