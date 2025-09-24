from __future__ import annotations

import os
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from . import models, schemas
from .auth import (
    create_access_token,
    get_current_user,
    get_password_hash,
    require_roles,
    verify_password,
)
from .database import Base, engine, get_session, session_scope
from .models import ServiceOrder, ServiceOrderStatus, Team, User, UserRole
from .schemas import (
    ObservationCreate,
    ObservationRead,
    PeriodCreate,
    PeriodRead,
    ServiceOrderCreate,
    ServiceOrderRead,
    ServiceOrderUpdate,
    TeamCreate,
    TeamRead,
    Token,
    UserCreate,
    UserRead,
)
from .utils import parse_orders_csv

app = FastAPI(title="Sistema de Ordens de Serviço Telecom")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", Path(__file__).resolve().parent / "storage"))
MAX_PHOTO_SIZE = int(os.getenv("MAX_PHOTO_SIZE", 5 * 1024 * 1024))
MAX_IMPORT_SIZE = int(os.getenv("MAX_IMPORT_SIZE", 2 * 1024 * 1024))
ALLOWED_PHOTO_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _sanitize_filename(filename: str) -> str:
    """Return a filesystem-safe filename."""

    name = Path(filename).name
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode()
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    return name or "upload"


def _read_limited(upload_file: UploadFile, max_bytes: int) -> bytes:
    upload_file.file.seek(0)
    data = bytearray()
    for chunk in iter(lambda: upload_file.file.read(1024 * 1024), b""):
        data.extend(chunk)
        if len(data) > max_bytes:
            raise HTTPException(
                status_code=400,
                detail="Arquivo excede o tamanho máximo permitido",
            )
    return bytes(data)


def _save_upload_file(upload_file: UploadFile, destination: Path, max_bytes: int) -> None:
    upload_file.file.seek(0)
    total = 0
    with destination.open("wb") as buffer:
        while True:
            chunk = upload_file.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                destination.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=400,
                    detail="Arquivo excede o tamanho máximo permitido",
                )
            buffer.write(chunk)


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    with session_scope() as session:
        models.ensure_default_teams(session)
        models.ensure_admin_user(session, "admin", get_password_hash("admin"))


@app.post("/auth/token", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)
):
    user = session.query(User).filter(User.username == form_data.username).one_or_none()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Usuário ou senha inválidos")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Usuário desativado")

    access_token = create_access_token(data={"sub": user.username})
    return Token(access_token=access_token)


@app.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    session: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.admin.value)),
):
    if session.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Usuário já existe")

    if payload.role == UserRole.technician and payload.team_id is None:
        raise HTTPException(
            status_code=400, detail="Técnicos precisam estar associados a uma equipe"
        )

    user = User(
        username=payload.username,
        hashed_password=get_password_hash(payload.password),
        role=payload.role,
        team_id=payload.team_id,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@app.get("/users", response_model=List[UserRead])
def list_users(
    session: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.admin.value, UserRole.support.value)),
):
    return session.query(User).all()


@app.post("/teams", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
def create_team(
    payload: TeamCreate,
    session: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.admin.value)),
):
    team = Team(name=payload.name)
    session.add(team)
    session.commit()
    session.refresh(team)
    return team


@app.get("/teams", response_model=List[TeamRead])
def list_teams(
    session: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.admin.value, UserRole.support.value)),
):
    return session.query(Team).all()


@app.post("/periods", response_model=PeriodRead, status_code=status.HTTP_201_CREATED)
def create_period(
    payload: PeriodCreate,
    session: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.admin.value, UserRole.support.value)),
):
    period = models.Period(**payload.model_dump())
    session.add(period)
    session.commit()
    session.refresh(period)
    return period


@app.get("/periods", response_model=List[PeriodRead])
def list_periods(
    session: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.admin.value, UserRole.support.value)),
):
    return session.query(models.Period).order_by(models.Period.start_date).all()


@app.post("/orders", response_model=ServiceOrderRead, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: ServiceOrderCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(
        require_roles(UserRole.admin.value, UserRole.support.value)
    ),
):
    if (
        session.query(ServiceOrder)
        .filter(ServiceOrder.installation_id == payload.installation_id)
        .first()
    ):
        raise HTTPException(status_code=400, detail="ID de instalação já cadastrado")

    order = ServiceOrder(**payload.model_dump())
    if order.technician_id:
        technician = session.get(User, order.technician_id)
        if not technician or technician.role != UserRole.technician:
            raise HTTPException(status_code=400, detail="Técnico inválido")
    if order.team_id:
        team = session.get(Team, order.team_id)
        if not team:
            raise HTTPException(status_code=400, detail="Equipe inválida")

    session.add(order)
    session.commit()
    session.refresh(order)
    return order


@app.post("/orders/import", response_model=List[ServiceOrderRead])
def import_orders(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.admin.value, UserRole.support.value)),
):
    if file.content_type not in {"text/csv", "application/vnd.ms-excel"}:
        raise HTTPException(status_code=400, detail="Envie um arquivo CSV")

    orders_data = parse_orders_csv(_read_limited(file, MAX_IMPORT_SIZE))
    created_orders: List[ServiceOrder] = []
    for order_payload in orders_data:
        if (
            session.query(ServiceOrder)
            .filter(ServiceOrder.installation_id == order_payload.installation_id)
            .first()
        ):
            continue
        order = ServiceOrder(**order_payload.model_dump())
        session.add(order)
        created_orders.append(order)
    session.commit()
    for order in created_orders:
        session.refresh(order)
    return created_orders


def _apply_order_filters(
    query,
    start_date: Optional[date],
    end_date: Optional[date],
    period_id: Optional[int],
    team_id: Optional[int],
    technician_id: Optional[int],
):
    if start_date:
        query = query.filter(ServiceOrder.scheduled_date >= start_date)
    if end_date:
        query = query.filter(ServiceOrder.scheduled_date <= end_date)
    if period_id:
        query = query.filter(ServiceOrder.period_id == period_id)
    if team_id:
        query = query.filter(ServiceOrder.team_id == team_id)
    if technician_id:
        query = query.filter(ServiceOrder.technician_id == technician_id)
    return query


@app.get("/orders", response_model=List[ServiceOrderRead])
def list_orders(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    period_id: Optional[int] = None,
    team_id: Optional[int] = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    query = session.query(ServiceOrder)
    if current_user.role == UserRole.technician:
        query = _apply_order_filters(
            query.filter(ServiceOrder.technician_id == current_user.id),
            start_date,
            end_date,
            period_id,
            None,
            current_user.id,
        )
    else:
        query = _apply_order_filters(query, start_date, end_date, period_id, team_id, None)
    return query.order_by(ServiceOrder.scheduled_date.desc()).all()


@app.get("/orders/{order_id}", response_model=ServiceOrderRead)
def get_order(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    order = session.get(ServiceOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Ordem não encontrada")

    if current_user.role == UserRole.technician and order.technician_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para visualizar esta ordem")
    return order


@app.patch("/orders/{order_id}", response_model=ServiceOrderRead)
def update_order(
    order_id: int,
    payload: ServiceOrderUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    order = session.get(ServiceOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Ordem não encontrada")

    if current_user.role == UserRole.technician:
        allowed_status = {ServiceOrderStatus.in_progress, ServiceOrderStatus.completed}
        if payload.status and payload.status not in allowed_status:
            raise HTTPException(status_code=403, detail="Status inválido para técnico")
        if order.technician_id != current_user.id:
            raise HTTPException(status_code=403, detail="Sem permissão para alterar esta ordem")
    elif current_user.role in {UserRole.support, UserRole.admin}:
        pass
    else:
        raise HTTPException(status_code=403, detail="Operação não permitida")

    update_data = payload.model_dump(exclude_unset=True)

    if "technician_id" in update_data and update_data["technician_id"] is not None:
        tech = session.get(User, update_data["technician_id"])
        if not tech or tech.role != UserRole.technician:
            raise HTTPException(status_code=400, detail="Técnico inválido")
    if "team_id" in update_data and update_data["team_id"] is not None:
        team = session.get(Team, update_data["team_id"])
        if not team:
            raise HTTPException(status_code=400, detail="Equipe inválida")

    for key, value in update_data.items():
        setattr(order, key, value)

    session.add(order)
    session.commit()
    session.refresh(order)
    return order


@app.post("/orders/{order_id}/observations", response_model=ObservationRead)
def add_observation(
    order_id: int,
    payload: ObservationCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    order = session.get(ServiceOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Ordem não encontrada")

    if current_user.role == UserRole.technician and order.technician_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para adicionar observações")

    observation = models.OrderObservation(
        order_id=order.id, author_id=current_user.id, note=payload.note
    )
    session.add(observation)
    session.commit()
    session.refresh(observation)
    return observation


@app.post("/orders/{order_id}/photos", response_model=schemas.PhotoRead)
def upload_photo(
    order_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    order = session.get(ServiceOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Ordem não encontrada")

    if current_user.role == UserRole.technician and order.technician_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sem permissão para adicionar fotos")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Arquivo inválido")

    if file.content_type not in ALLOWED_PHOTO_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Tipo de arquivo não suportado")

    order_dir = UPLOAD_DIR / f"order_{order_id}"
    order_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = f"{timestamp}_{_sanitize_filename(file.filename)}"
    file_path = order_dir / filename

    _save_upload_file(file, file_path, MAX_PHOTO_SIZE)

    photo = models.OrderPhoto(order_id=order.id, file_path=str(file_path))
    session.add(photo)
    session.commit()
    session.refresh(photo)
    return photo


@app.delete("/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(
    order_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(require_roles(UserRole.admin.value, UserRole.support.value)),
):
    order = session.get(ServiceOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Ordem não encontrada")
    session.delete(order)
    session.commit()
    return None
