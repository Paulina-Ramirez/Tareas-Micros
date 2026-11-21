from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cache import (
    cache_delete, cache_get, cache_set, k_proyectos_usuario,
    k_tareas_proyecto, k_tareas_usuario,
)
from app.database import get_db
from app.dependencies import (
    ROL_ADMIN, ROL_LIDER, ROL_MIEMBRO, UsuarioActual, get_current_user, require_roles,
)
from app.events import (
    CANAL_ESTADO_CAMBIADO, CANAL_TAREA_ASIGNADA, crear_notificacion, publish_event,
)
from app.models import Proyecto, Tarea
from app.schemas import EstadoUpdate, TareaCreate, TareaResponse
from app.users import validar_miembro

router = APIRouter(prefix="/tasks", tags=["Tareas"])


def _proyecto_o_404(db: Session, id_proyecto: int) -> Proyecto:
    proyecto = db.get(Proyecto, id_proyecto)
    if proyecto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"El proyecto {id_proyecto} no existe")
    return proyecto


# ─────────────────────────── ASIGNAR TAREA ───────────────────────────
@router.post("/", response_model=TareaResponse, status_code=status.HTTP_201_CREATED)
def crear_y_asignar_tarea(
    datos: TareaCreate,
    db: Session = Depends(get_db),
    user: UsuarioActual = Depends(require_roles(ROL_ADMIN, ROL_LIDER)),
):
    # 1) Autorización: Admin, o Líder del proyecto
    proyecto = _proyecto_o_404(db, datos.id_proyecto)
    if user.rol == ROL_LIDER and proyecto.id_lider != user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Solo el líder del proyecto puede asignar tareas en él"
        )

    # 2) Validar que el miembro exista y tenga rol Miembro
    validar_miembro(db, datos.id_asignado)

    # 3) BD: tarea + notificación en la MISMA transacción
    tarea = Tarea(
        titulo=datos.titulo.strip(),
        descripcion=datos.descripcion,
        id_proyecto=datos.id_proyecto,
        id_asignado=datos.id_asignado,
        fecha_vencimiento=datos.fecha_vencimiento,
        estado="Pendiente",
    )
    db.add(tarea)
    db.flush()  # para obtener tarea.id

    mensaje = f"Se te asignó la tarea '{tarea.titulo}' en el proyecto '{proyecto.nombre}'"
    notificacion = crear_notificacion(db, datos.id_asignado, mensaje)
    id_tarea, titulo, id_notificacion = tarea.id, tarea.titulo, notificacion.id
    db.commit()
    db.refresh(tarea)

    # 4) Caché: invalidar (la próxima lectura la repuebla vía Cache-Aside)
    cache_delete(
        k_tareas_usuario(datos.id_asignado),
        k_tareas_proyecto(datos.id_proyecto),
        k_proyectos_usuario(datos.id_asignado),  # ahora el miembro "ve" este proyecto
    )

    # 5) Evento Pub/Sub (RF6) → el notification-service lo envía por WebSocket (RF7)
    publish_event(CANAL_TAREA_ASIGNADA, {
        "id_tarea": id_tarea,
        "id_proyecto": datos.id_proyecto,
        "titulo": titulo,
        "id_destinatario": datos.id_asignado,
        "id_actor": user.id,
        "id_notificacion": id_notificacion,
        "mensaje": mensaje,
    })

    return tarea


# ─────────────────────────── LISTAR TAREAS ───────────────────────────
@router.get("/", response_model=List[TareaResponse])
def listar_tareas(
    id_proyecto: Optional[int] = None,
    id_asignado: Optional[int] = None,
    db: Session = Depends(get_db),
    user: UsuarioActual = Depends(get_current_user),
):
    """Miembro: solo las suyas. Líder: las de sus proyectos. Admin: todas."""
    stmt = select(Tarea).order_by(Tarea.id)
    key = None  # solo se cachean las dos vistas más frecuentes

    if user.rol == ROL_MIEMBRO:
        if id_asignado is not None and id_asignado != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puedes consultar tus propias tareas")
        stmt = stmt.where(Tarea.id_asignado == user.id)
        if id_proyecto is not None:
            stmt = stmt.where(Tarea.id_proyecto == id_proyecto)
        else:
            key = k_tareas_usuario(user.id)
    else:
        if id_proyecto is not None:
            proyecto = _proyecto_o_404(db, id_proyecto)
            if user.rol == ROL_LIDER and proyecto.id_lider != user.id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Ese proyecto no es tuyo")
            stmt = stmt.where(Tarea.id_proyecto == id_proyecto)
            if id_asignado is None:
                key = k_tareas_proyecto(id_proyecto)
        elif user.rol == ROL_LIDER:
            stmt = stmt.where(
                Tarea.id_proyecto.in_(select(Proyecto.id).where(Proyecto.id_lider == user.id))
            )
        if id_asignado is not None:
            stmt = stmt.where(Tarea.id_asignado == id_asignado)

    if key is not None:
        en_cache = cache_get(key)  # Cache Hit
        if en_cache is not None:
            return en_cache

    # Cache Miss → PostgreSQL
    tareas = db.execute(stmt).scalars().all()
    resultado = [TareaResponse.model_validate(t).model_dump(mode="json") for t in tareas]
    if key is not None:
        cache_set(key, resultado)
    return resultado


# ─────────────────────── ACTUALIZAR ESTADO DE TAREA ───────────────────────
@router.put("/{id_tarea}/estado", response_model=TareaResponse)
def actualizar_estado(
    id_tarea: int,
    datos: EstadoUpdate,
    db: Session = Depends(get_db),
    user: UsuarioActual = Depends(get_current_user),
):
    # 1) Buscar la tarea
    tarea = db.get(Tarea, id_tarea)
    if tarea is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"La tarea {id_tarea} no existe")
    proyecto = _proyecto_o_404(db, tarea.id_proyecto)

    # 2) Autorización: Admin, Líder del proyecto, o el Miembro asignado
    es_miembro_asignado = user.rol == ROL_MIEMBRO and tarea.id_asignado == user.id
    es_lider_del_proyecto = user.rol == ROL_LIDER and proyecto.id_lider == user.id
    if not (user.rol == ROL_ADMIN or es_lider_del_proyecto or es_miembro_asignado):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso sobre esta tarea")

    # Sin cambio real → no se toca BD, caché ni se notifica a nadie
    if datos.estado == tarea.estado:
        return tarea

    # 3) BD: nuevo estado + notificación en la misma transacción
    anterior = tarea.estado
    tarea.estado = datos.estado

    # Nunca se notifica al actor: si lo cambia el Miembro avisa al Líder;
    # si lo cambia el Líder/Admin avisa al Miembro asignado.
    destinatario = proyecto.id_lider if user.rol == ROL_MIEMBRO else tarea.id_asignado
    mensaje = f"La tarea '{tarea.titulo}' cambió de '{anterior}' a '{datos.estado}'"
    id_notificacion = None
    if destinatario != user.id:
        id_notificacion = crear_notificacion(db, destinatario, mensaje).id
    else:
        destinatario = None

    id_proyecto, id_asignado, titulo = tarea.id_proyecto, tarea.id_asignado, tarea.titulo
    db.commit()
    db.refresh(tarea)

    # 4) Caché
    cache_delete(k_tareas_usuario(id_asignado), k_tareas_proyecto(id_proyecto))

    # 5) Evento (RF6): siempre que cambia el estado
    publish_event(CANAL_ESTADO_CAMBIADO, {
        "id_tarea": id_tarea,
        "id_proyecto": id_proyecto,
        "titulo": titulo,
        "estado_anterior": anterior,
        "estado_nuevo": datos.estado,
        "id_destinatario": destinatario,
        "id_actor": user.id,
        "id_notificacion": id_notificacion,
        "mensaje": mensaje,
    })

    return tarea
