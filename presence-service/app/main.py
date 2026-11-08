from fastapi import FastAPI
import redis.asyncio as redis
import os

app = FastAPI(title="Presence Service")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Cliente de Redis
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

@app.get("/")
def health_check():
    return {"status": "ok", "service": "Presence Service listo"}

@app.post("/online/{user_id}")
async def set_user_online(user_id: int):
    # Guarda al usuario con un TTL de 60 segundos
    await redis_client.setex(f"user_online:{user_id}", 60, "true")
    return {"message": f"Usuario {user_id} marcado en línea"}

@app.get("/online/{user_id}")
async def check_user_status(user_id: int):
    status = await redis_client.get(f"user_online:{user_id}")
    return {"user_id": user_id, "online": status is not None}