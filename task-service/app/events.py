"""Publicación de eventos en Redis Pub/Sub (RF6) y helpers de notificación."""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.models import Notificacion
from app.redis_client import get_redis

logger = logging.getLogger(__name__)

CANAL_TAREA_ASIGNADA = "tareas:asignada"
CANAL_ESTADO_CAMBIADO = "tareas:estado_cambiado"
CANAL_PROYECTO_CREADO = "tareas:proyecto_creado"


def publish_event(canal: str, payload: Dict[str, Any]) -> None:
    """Publica un evento JSON en un canal de Redis.

    Se llama DESPUÉS del commit. Si Redis falla no se revierte nada: la tarea
    y su notificación ya quedaron guardadas en la BD (aislamiento de fallos).
    """
    mensaje = {
        "evento": canal.split(":", 1)[1],
        **payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        get_redis().publish(canal, json.dumps(mensaje))
    except Exception:
        logger.exception("Redis: no se pudo publicar el evento en %s", canal)


def crear_notificacion(db: Session, id_usuario: int, mensaje: str) -> Notificacion:
    """Inserta la notificación en la sesión actual (misma transacción que el
    cambio de la tarea). Hace flush para obtener su id; el commit lo hace
    quien llama."""
    notificacion = Notificacion(id_usuario=id_usuario, mensaje=mensaje, leida=False)
    db.add(notificacion)
    db.flush()
    return notificacion
