"""Historial de notificaciones.

Complementa al WebSocket: si el usuario estaba desconectado cuando ocurrió el
evento, la notificación igual quedó guardada en la BD y la recupera aquí.
El frontend carga este historial al entrar y después abre el WebSocket;
usa el campo `id` (= id_notificacion de los eventos) para no duplicar.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import UsuarioActual, get_current_user
from app.models import Notificacion
from app.schemas import NotificacionResponse

router = APIRouter(prefix="/notifications", tags=["Notificaciones"])


@router.get("/", response_model=List[NotificacionResponse])
def listar_notificaciones(
    incluir_leidas: bool = False,
    limite: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: UsuarioActual = Depends(get_current_user),
):
    """Notificaciones del usuario autenticado, las más nuevas primero.
    Por defecto solo las no leídas (?incluir_leidas=true para ver todas)."""
    stmt = select(Notificacion).where(Notificacion.id_usuario == user.id)
    if not incluir_leidas:
        stmt = stmt.where(Notificacion.leida.is_(False))
    stmt = stmt.order_by(Notificacion.id.desc()).limit(limite)
    return db.execute(stmt).scalars().all()


@router.put("/{id_notificacion}/leida", response_model=NotificacionResponse)
def marcar_como_leida(
    id_notificacion: int,
    db: Session = Depends(get_db),
    user: UsuarioActual = Depends(get_current_user),
):
    notificacion = db.get(Notificacion, id_notificacion)
    # Una notificación ajena se trata como inexistente (404): no se revela
    # que existe.
    if notificacion is None or notificacion.id_usuario != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La notificación no existe")

    if not notificacion.leida:  # idempotente: marcar dos veces no falla
        notificacion.leida = True
        db.commit()
        db.refresh(notificacion)
    return notificacion
