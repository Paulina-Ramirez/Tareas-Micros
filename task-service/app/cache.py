"""Patrón Cache-Aside sobre Redis.

Regla de oro: Redis es una optimización, no una dependencia. Si Redis falla,
se registra el error y el servicio sigue funcionando contra PostgreSQL.
"""
import json
import logging
from typing import Any, Optional

from fastapi.encoders import jsonable_encoder

from app.redis_client import get_redis

logger = logging.getLogger(__name__)

TTL_SEGUNDOS = 60

# ── Claves ──
K_PROYECTOS_TODOS = "projects:all"


def k_proyectos_usuario(id_usuario: int) -> str:
    return f"projects:user:{id_usuario}"


def k_tareas_usuario(id_usuario: int) -> str:
    return f"tasks:user:{id_usuario}"


def k_tareas_proyecto(id_proyecto: int) -> str:
    return f"tasks:project:{id_proyecto}"


# ── Operaciones ──
def cache_get(key: str) -> Optional[Any]:
    """Devuelve el dato cacheado o None (miss o Redis caído)."""
    try:
        raw = get_redis().get(key)
        return json.loads(raw) if raw is not None else None
    except Exception:
        logger.exception("Redis: no se pudo leer la clave %s", key)
        return None


def cache_set(key: str, data: Any, ttl: int = TTL_SEGUNDOS) -> None:
    try:
        get_redis().set(key, json.dumps(jsonable_encoder(data)), ex=ttl)
    except Exception:
        logger.exception("Redis: no se pudo guardar la clave %s", key)


def cache_delete(*keys: str) -> None:
    """Invalida claves. Se llama DESPUÉS del commit en la BD."""
    if not keys:
        return
    try:
        get_redis().delete(*keys)
    except Exception:
        logger.exception("Redis: no se pudieron invalidar las claves %s", keys)
