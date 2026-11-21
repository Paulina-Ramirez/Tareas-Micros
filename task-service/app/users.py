"""Consultas de solo lectura a la tabla `usuarios` (propiedad del auth-service)."""
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import ROL_LIDER, ROL_MIEMBRO, normalizar_rol
from app.models import usuarios


def _obtener_con_rol(db: Session, id_usuario: int, rol_esperado: str):
    fila = db.execute(
        select(usuarios.c.id, usuarios.c.nombre, usuarios.c.rol).where(
            usuarios.c.id == id_usuario
        )
    ).first()
    if fila is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El usuario {id_usuario} no existe",
        )
    if normalizar_rol(fila.rol) != rol_esperado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El usuario {id_usuario} no tiene el rol {rol_esperado}",
        )
    return fila


def validar_miembro(db: Session, id_usuario: int):
    """El usuario debe existir y tener rol Miembro."""
    return _obtener_con_rol(db, id_usuario, ROL_MIEMBRO)


def validar_lider(db: Session, id_usuario: int):
    """El usuario debe existir y tener rol Lider."""
    return _obtener_con_rol(db, id_usuario, ROL_LIDER)
