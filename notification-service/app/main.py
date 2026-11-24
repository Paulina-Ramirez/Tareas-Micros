"""Notification Service

Recibe los eventos que el task-service publica en Redis (Pub/Sub, RF6) y los
entrega en tiempo real, por WebSocket, al usuario afectado (RF7).

Piezas:
  1. Autenticación al conectar: el JWT viaja en la URL (?token=...).
  2. GestorConexiones: registro {id_usuario: {websockets}} (varias pestañas).
  3. Un único suscriptor global a "tareas:*" (tarea de fondo con reconexión).
  4. Limpieza: el socket se quita del registro al desconectarse o fallar.
"""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager, suppress
from typing import Dict, Optional, Set

import redis.asyncio as redis
from fastapi import FastAPI, Query, WebSocket
from jose import JWTError, jwt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("notification-service")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Debe ser la misma clave con la que el auth-service firma los tokens
SECRET_KEY = os.getenv("SECRET_KEY", "super_secret_key_para_el_proyecto_buap")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

PATRON_CANALES = "tareas:*"

# Espera entre reintentos de conexión a Redis (crece al doble hasta el máximo)
ESPERA_INICIAL = 1.0
ESPERA_MAXIMA = 30.0


# ───────────────────────── Registro de conexiones ─────────────────────────
class GestorConexiones:
    """Guarda qué WebSockets pertenecen a cada usuario.

    Es un set por usuario porque una misma persona puede tener varias
    pestañas abiertas y todas deben recibir el aviso.
    """

    def __init__(self) -> None:
        self._conexiones: Dict[int, Set[WebSocket]] = {}

    def registrar(self, id_usuario: int, websocket: WebSocket) -> None:
        self._conexiones.setdefault(id_usuario, set()).add(websocket)

    def quitar(self, id_usuario: int, websocket: WebSocket) -> None:
        sockets = self._conexiones.get(id_usuario)
        if sockets is None:
            return
        sockets.discard(websocket)
        if not sockets:
            del self._conexiones[id_usuario]

    def total(self) -> int:
        return sum(len(s) for s in self._conexiones.values())

    async def enviar_a_usuario(self, id_usuario: int, mensaje: dict) -> int:
        """Envía el mensaje a todas las conexiones del usuario.
        Devuelve a cuántas se entregó. Si un socket está muerto, lo quita."""
        enviados = 0
        for websocket in list(self._conexiones.get(id_usuario, ())):
            try:
                await websocket.send_json(mensaje)
                enviados += 1
            except Exception:
                logger.info("Conexión muerta del usuario %s: se elimina", id_usuario)
                self.quitar(id_usuario, websocket)
        return enviados


gestor = GestorConexiones()


# ───────────────────────── Suscriptor global a Redis ─────────────────────────
def crear_cliente_redis() -> redis.Redis:
    # health_check_interval detecta conexiones caídas "en silencio"
    return redis.from_url(REDIS_URL, decode_responses=True, health_check_interval=30)


async def _cerrar(recurso) -> None:
    """Cierra un cliente o pubsub de redis sin que un error aquí estorbe."""
    try:
        cerrar = getattr(recurso, "aclose", None) or recurso.close
        await cerrar()
    except Exception:
        pass


async def procesar_evento(datos: str) -> None:
    """Un evento publicado por el task-service → WebSocket del destinatario."""
    try:
        evento = json.loads(datos)
    except (TypeError, ValueError):
        logger.warning("Evento ignorado: no es JSON válido")
        return
    if not isinstance(evento, dict):
        return

    id_destinatario = evento.get("id_destinatario")
    if id_destinatario is None:
        # Ej.: alguien cambió el estado de su propia tarea → no hay a quién avisar
        return
    try:
        id_destinatario = int(id_destinatario)
    except (TypeError, ValueError):
        logger.warning("Evento ignorado: id_destinatario inválido (%r)", id_destinatario)
        return

    entregados = await gestor.enviar_a_usuario(id_destinatario, evento)
    logger.info(
        "Evento %s para usuario %s: %s conexión(es)",
        evento.get("evento"), id_destinatario, entregados,
    )


async def escuchar_redis() -> None:
    """Tarea de fondo: se suscribe a tareas:* y reintenta si Redis se cae."""
    espera = ESPERA_INICIAL
    while True:
        cliente = pubsub = None
        try:
            cliente = crear_cliente_redis()
            pubsub = cliente.pubsub()
            await pubsub.psubscribe(PATRON_CANALES)
            logger.info("Suscrito a %s en Redis", PATRON_CANALES)
            espera = ESPERA_INICIAL  # conexión lograda: se reinicia la espera

            async for mensaje in pubsub.listen():
                if mensaje["type"] != "pmessage":
                    continue
                try:
                    await procesar_evento(mensaje["data"])
                except Exception:
                    # Un evento malo no debe tumbar al suscriptor
                    logger.exception("Error procesando un evento")
            # listen() terminó sin error: se vuelve a suscribir
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
    tarea = asyncio.create_task(escuchar_redis())
    yield
    tarea.cancel()
    with suppress(asyncio.CancelledError):
        await tarea


app = FastAPI(title="Notification Service", lifespan=lifespan)


@app.get("/")
def health_check():
    return {
        "status": "ok",
        "service": "Notification Service listo",
        "conexiones_activas": gestor.total(),
    }


# ───────────────────────── Autenticación del WebSocket ─────────────────────────
def identificar_usuario(token: Optional[str], user_id: int) -> int:
    """Valida el JWT y comprueba que pertenezca al {user_id} de la ruta.
    Lanza ValueError con el motivo si algo no cuadra."""
    if not token:
        raise ValueError("Falta el token (usa ?token=<jwt>)")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise ValueError("Token inválido o expirado")

    try:
        id_token = int(payload.get("id"))
    except (TypeError, ValueError):
        raise ValueError("El token no trae id. Vuelve a iniciar sesión")

    if id_token != user_id:
        raise ValueError("El token no pertenece a este usuario")
    return id_token


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: int,
    token: Optional[str] = Query(default=None),
):
    # Se acepta primero para poder cerrar con un código y un motivo que el
    # frontend sí puede leer (si se rechaza antes, el navegador solo ve 1006).
    await websocket.accept()

    try:
        id_usuario = identificar_usuario(token, user_id)
    except ValueError as e:
        await websocket.close(code=1008, reason=str(e))  # 1008 = violación de política
        return

    gestor.registrar(id_usuario, websocket)
    try:
        await websocket.send_json({"evento": "conectado", "id_usuario": id_usuario})
        # Se espera al cliente: así se detecta cuando se desconecta.
        # Si manda "ping" (keep-alive) se responde "pong".
        while True:
            mensaje = await websocket.receive()
            if mensaje["type"] == "websocket.disconnect":
                break
            if mensaje.get("text") == "ping":
                await websocket.send_text("pong")
    except Exception:
        logger.info("WebSocket del usuario %s terminó con error", id_usuario)
    finally:
        gestor.quitar(id_usuario, websocket)
