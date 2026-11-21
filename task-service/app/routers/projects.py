from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cache import (
    K_PROYECTOS_TODOS, cache_delete, cache_get, cache_set, k_proyectos_usuario,
)
from app.database import get_db
from app.dependencies import (
    ROL_ADMIN, ROL_LIDER, ROL_MIEMBRO, UsuarioActual, get_current_user, require_roles,
)
from app.events import CANAL_PROYECTO_CREADO, crear_notificacion, publish_event
from app.models import Proyecto, Tarea
from app.schemas import ProyectoCreate, ProyectoResponse
from app.users import validar_lider

router = APIRouter(prefix="/projects", tags=["Proyectos"])


@router.post("/", response_model=ProyectoResponse, status_code=status.HTTP_201_CREATED)
def crear_proyecto(
    datos: ProyectoCreate,
    db: Session = Depends(get_db),
    user: UsuarioActual = Depends(require_roles(ROL_ADMIN, ROL_LIDER)),
):
    # 1) Autorización + determinar quién será el líder
    if user.rol == ROL_LIDER:
        if datos.id_lider is not None and datos.id_lider != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Un Líder solo puede crear proyectos a su propio nombre",
            )
        id_lider = user.id
    else:  # Admin
        if datos.id_lider is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El Admin debe indicar id_lider",
            )
        validar_lider(db, datos.id_lider)
        id_lider = datos.id_lider

    # 2) BD: proyecto (+ notificación si un Admin se lo asigna a un Líder),
    #    todo en una sola transacción
    proyecto = Proyecto(nombre=datos.nombre.strip(), id_lider=id_lider)
    db.add(proyecto)
    db.flush()  # para obtener proyecto.id

    notificacion = None
    if id_lider != user.id:
        notificacion = crear_notificacion(
            db, id_lider, f"Se te asignó como líder del proyecto '{proyecto.nombre}'"
        )
    id_proyecto, nombre, id_notificacion = (
        proyecto.id, proyecto.nombre, notificacion.id if notificacion else None,
    )
    db.commit()
    db.refresh(proyecto)

    # 3) Caché: invalidar las listas afectadas
    cache_delete(k_proyectos_usuario(id_lider), K_PROYECTOS_TODOS)

    # 4) Evento (solo si hay a quién avisar)
    if notificacion is not None:
        publish_event(CANAL_PROYECTO_CREADO, {
            "id_proyecto": id_proyecto,
            "nombre": nombre,
            "id_destinatario": id_lider,
            "id_actor": user.id,
            "id_notificacion": id_notificacion,
            "mensaje": f"Se te asignó como líder del proyecto '{nombre}'",
        })

    return proyecto


@router.get("/", response_model=List[ProyectoResponse])
def listar_proyectos(
    db: Session = Depends(get_db),
    user: UsuarioActual = Depends(get_current_user),
):
    """Admin: todos. Líder: los suyos. Miembro: aquellos donde tiene tareas."""
    key = K_PROYECTOS_TODOS if user.rol == ROL_ADMIN else k_proyectos_usuario(user.id)

    en_cache = cache_get(key)  # Cache Hit
    if en_cache is not None:
        return en_cache

    # Cache Miss → PostgreSQL
    stmt = select(Proyecto).order_by(Proyecto.id)
    if user.rol == ROL_LIDER:
        stmt = stmt.where(Proyecto.id_lider == user.id)
    elif user.rol == ROL_MIEMBRO:
        stmt = (
            select(Proyecto)
            .join(Tarea, Tarea.id_proyecto == Proyecto.id)
            .where(Tarea.id_asignado == user.id)
            .distinct()
            .order_by(Proyecto.id)
        )
    proyectos = db.execute(stmt).scalars().all()

    resultado = [ProyectoResponse.model_validate(p).model_dump(mode="json") for p in proyectos]
    cache_set(key, resultado)
    return resultado
