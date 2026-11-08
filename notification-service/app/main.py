from fastapi import FastAPI, WebSocket
import redis.asyncio as redis
import asyncio
import os

app = FastAPI(title="Notification Service")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

@app.get("/")
def health_check():
    return {"status": "ok", "service": "Notification Service listo"}

# Endpoint básico de prueba para WebSockets
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    await websocket.send_text(f"Conectado al servicio de notificaciones para el usuario {user_id}")
    try:
        while True:
            # Aquí Miriam programará la lógica de escuchar Redis y enviar el mensaje
            await asyncio.sleep(1)
    except Exception:
        await websocket.close()