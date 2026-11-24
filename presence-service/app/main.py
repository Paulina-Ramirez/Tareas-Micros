"""Presence Service: el "vigilante del estado".

Guarda en Redis quién está en línea usando claves con TTL, sin consultar la
base de datos principal:

    presence:user:{id_usuario}  ->  {"rol": ..., "ultima_actividad": ...}   (TTL 60 s)

La presencia se mantiene viva por dos vías:
  1. Latido HTTP: el frontend llama POST /presence/heartbeat cada ~30 s.
     Cada latido reescribe la clave con TTL nuevo. Si el usuario deja de
     interactuar, la clave expira sola y queda como inactivo.
  2. Eventos Pub/Sub del notification-service (presencia:conectado /
     presencia:desconectado): marcan al usuario en línea al abrir su primer
     WebSocket y fuera de línea al cerrar el último, sin esperar al TTL.

La identidad (X-User-Id / X-User-Role) la pone el API Gateway después de
validar el JWT; este servicio confía en esos headers igual que el task-service.
"""
import asyncio
import json
import logging
import os
import unicodedata
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import redis.asyncio as redis
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from redis.exceptions import RedisError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("presence-service")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Debe ser ~2 veces el intervalo del latido del frontend (30 s), para que un
# latido perdido no marque al usuario como desconectado.
TTL_SEGUNDOS = int(os.getenv("PRESENCE_TTL", "60"))

PREFIJO_CLAVE = "presence:user:"
PATRON_EVENTOS = "presencia:*"
CANAL_CONECTADO = "presencia:conectado"
CANAL_DESCONECTADO = "presencia:desconectado"

# Espera entre reintentos de conexión a Redis (crece al doble hasta el máximo)
ESPERA_INICIAL = 1.0
ESPERA_MAXIMA = 30.0


# ───────────────────────── Redis ─────────────────────────
def crear_cliente_redis() -> redis.Redis:
    """Cliente para las peticiones HTTP. Con timeouts: si Redis se cuelga, la
    petición falla rápido (503) en lugar de quedarse esperando."""
    return redis.from_url(
        REDIS_URL, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
    )


def crear_cliente_suscriptor() -> redis.Redis:
    """Cliente exclusivo del suscriptor. Sin socket_timeout (una suscripción
    pasa mucho tiempo en silencio); health_check_interval detecta caídas."""
    return redis.from_url(REDIS_URL, decode_responses=True, health_check_interval=30)


_redis: Optional[redis.Redis] = None  # se crea al arrancar (lifespan)


def get_redis() -> redis.Redis:
    if _redis is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Redis no disponible")
    return _redis


async def _cerrar(recurso) -> None:
    """Cierra un cliente o pubsub de redis sin que un error aquí estorbe."""
    try:
        cerrar = getattr(recurso, "aclose", None) or recurso.close
        await cerrar()
    except Exception:
        pass


# ───────────────────────── Identidad (la pone el gateway) ─────────────────────────
ROLES = {"admin": "Admin", "lider": "Lider", "miembro": "Miembro"}


def normalizar_rol(rol: Optional[str]) -> Optional[str]:
    """Acepta 'Lider' o 'Líder' (con o sin acento / mayúsculas)."""
    if not rol or not isinstance(rol, str):
        return None
    limpio = unicodedata.normalize("NFD", rol.strip().lower())
    limpio = "".join(c for c in limpio if unicodedata.category(c) != "Mn")
    return ROLES.get(limpio)


@dataclass
class UsuarioActual:
    id: int
    rol: str


def get_current_user(
    x_user_id: Optional[str] = Header(default=None),
    x_user_role: Optional[str] = Header(default=None),
) -> UsuarioActual:
    rol = normalizar_rol(x_user_role)
    if x_user_id is None or rol is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identidad de usuario ausente o inválida")
    try:
        return UsuarioActual(id=int(x_user_id), rol=rol)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "X-User-Id inválido")


# ───────────────────────── Lógica de presencia ─────────────────────────
def _clave(id_usuario: int) -> str:
    return f"{PREFIJO_CLAVE}{id_usuario}"


async def registrar_presencia(r: redis.Redis, id_usuario: int, rol: Optional[str]) -> None:
    """Crea o renueva la clave del usuario con TTL nuevo."""
    valor = json.dumps({
        "rol": rol,
        "ultima_actividad": datetime.now(timezone.utc).isoformat(),
    })
    await r.set(_clave(id_usuario), valor, ex=TTL_SEGUNDOS)


async def borrar_presencia(r: redis.Redis, id_usuario: int) -> None:
    await r.delete(_clave(id_usuario))


def _leer_valor(raw: Optional[str]) -> dict:
    try:
        datos = json.loads(raw)
        return datos if isinstance(datos, dict) else {}
    except (TypeError, ValueError):
        return {}


class EstadoPresencia(BaseModel):
    id_usuario: int
    online: bool
    ttl_restante: Optional[int] = None
    rol: Optional[str] = None
    ultima_actividad: Optional[str] = None


class UsuarioEnLinea(BaseModel):
    id_usuario: int
    rol: Optional[str] = None
    ultima_actividad: Optional[str] = None


# ───────────────────────── Endpoints ─────────────────────────
router = APIRouter(prefix="/presence", tags=["Presencia"])


@router.post("/heartbeat", response_model=EstadoPresencia)
async def heartbeat(
    user: UsuarioActual = Depends(get_current_user),
    r: redis.Redis = Depends(get_redis),
):
    """Latido: renueva la presencia del usuario autenticado."""
    await registrar_presencia(r, user.id, user.rol)
    return EstadoPresencia(id_usuario=user.id, online=True, ttl_restante=TTL_SEGUNDOS, rol=user.rol)


@router.delete("/", response_model=EstadoPresencia)
async def marcar_offline(
    user: UsuarioActual = Depends(get_current_user),
    r: redis.Redis = Depends(get_redis),
):
    """Marca offline de inmediato (el frontend lo llama al cerrar sesión)."""
    await borrar_presencia(r, user.id)
    return EstadoPresencia(id_usuario=user.id, online=False)


# OJO: /online debe declararse ANTES que /{id_usuario}
@router.get("/online", response_model=List[UsuarioEnLinea])
async def usuarios_en_linea(
    user: UsuarioActual = Depends(get_current_user),  # cualquier rol autenticado
    r: redis.Redis = Depends(get_redis),
):
    """Todos los usuarios en línea. SCAN (no KEYS) para no bloquear Redis."""
    claves = list({k async for k in r.scan_iter(match=f"{PREFIJO_CLAVE}*", count=200)})
    if not claves:
        return []
    valores = await r.mget(claves)

    en_linea = {}
    for clave, raw in zip(claves, valores):
        if raw is None:  # expiró entre el SCAN y el MGET
            continue
        sufijo = clave[len(PREFIJO_CLAVE):]
        if not sufijo.isdigit():
            continue
        datos = _leer_valor(raw)
        en_linea[int(sufijo)] = UsuarioEnLinea(
            id_usuario=int(sufijo),
            rol=datos.get("rol"),
            ultima_actividad=datos.get("ultima_actividad"),
        )
    return [en_linea[i] for i in sorted(en_linea)]


@router.get("/{id_usuario}", response_model=EstadoPresencia)
async def estado_de_usuario(
    id_usuario: int,
    user: UsuarioActual = Depends(get_current_user),
    r: redis.Redis = Depends(get_redis),
):
    clave = _clave(id_usuario)
    raw = await r.get(clave)
    if raw is None:
        return EstadoPresencia(id_usuario=id_usuario, online=False)
    ttl = await r.ttl(clave)
    datos = _leer_valor(raw)
    return EstadoPresencia(
        id_usuario=id_usuario,
        online=True,
        ttl_restante=ttl if ttl >= 0 else None,
        rol=datos.get("rol"),
        ultima_actividad=datos.get("ultima_actividad"),
    )


# ───────────────────────── Suscriptor a eventos de presencia ─────────────────────────
async def procesar_evento(r: redis.Redis, canal: str, datos: str) -> None:
    try:
        evento = json.loads(datos)
    except (TypeError, ValueError):
        logger.warning("Evento de presencia ignorado: no es JSON válido")
        return
    if not isinstance(evento, dict):
        return
    try:
        id_usuario = int(evento.get("id_usuario"))
    except (TypeError, ValueError):
        logger.warning("Evento de presencia ignorado: id_usuario inválido")
        return

    if canal == CANAL_CONECTADO:
        await registrar_presencia(r, id_usuario, normalizar_rol(evento.get("rol")))
        logger.info("Usuario %s en línea (WebSocket abierto)", id_usuario)
    elif canal == CANAL_DESCONECTADO:
        await borrar_presencia(r, id_usuario)
        logger.info("Usuario %s fuera de línea (cerró su último WebSocket)", id_usuario)


async def escuchar_eventos() -> None:
    """Tarea de fondo: se suscribe a presencia:* y reintenta si Redis se cae."""
    espera = ESPERA_INICIAL
    while True:
        cliente = pubsub = None
        try:
            cliente = crear_cliente_suscriptor()
            pubsub = cliente.pubsub()
            await pubsub.psubscribe(PATRON_EVENTOS)
            logger.info("Suscrito a %s en Redis", PATRON_EVENTOS)
            espera = ESPERA_INICIAL

            async for mensaje in pubsub.listen():
                if mensaje["type"] != "pmessage":
                    continue
                try:
                    await procesar_evento(get_redis(), mensaje["channel"], mensaje["data"])
                except Exception:
                    # Un evento malo no debe tumbar al suscriptor
                    logger.exception("Error procesando un evento de presencia")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Redis no disponible (%s). Reintentando en %.1fs", e, espera)
        finally:
            if pubsub is not None:
                await _cerrar(pubsub)
            if cliente is not None:
                await _cerrar(cliente)

        await asyncio.sleep(espera)
        espera = min(espera * 2, ESPERA_MAXIMA)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis
    _redis = crear_cliente_redis()
    tarea = asyncio.create_task(escuchar_eventos())
    yield
    tarea.cancel()
    with suppress(asyncio.CancelledError):
        await tarea
    await _cerrar(_redis)
    _redis = None


app = FastAPI(title="Presence Service", lifespan=lifespan)
app.include_router(router)


@app.exception_handler(RedisError)
async def redis_no_disponible(request, exc):
    """Si Redis falla, el servicio responde 503 controlado (no 500)."""
    logger.error("Error de Redis: %s", exc)
    return JSONResponse(status_code=503, content={"detail": "Redis no disponible"})


@app.get("/")
async def health_check():
    try:
        await get_redis().ping()
        estado_redis = "ok"
    except Exception:
        estado_redis = "no disponible"
    return {"status": "ok", "service": "Presence Service listo", "redis": estado_redis}
