import os
import unicodedata

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from jose import jwt, JWTError

app = FastAPI(title="API Gateway - Sistema de Tareas")

# Permitir CORS para que el Frontend (Miriam) pueda conectarse
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción se pondría la URL del frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Debe ser la misma que en auth-service
SECRET_KEY = os.getenv("SECRET_KEY") or "super_secret_key_para_el_proyecto_buap"
ALGORITHM = "HS256"

# URLs de los microservicios (Docker resuelve estos nombres internamente)
AUTH_SERVICE_URL = "http://auth-service:8000"
TASK_SERVICE_URL = "http://task-service:8000"

# ==========================================
# CONTROL DE ACCESO POR ROL (RBAC)
# ==========================================
# Roles permitidos por método HTTP sobre /tasks (en minúsculas y sin acentos)
PERMISOS_TASKS = {
    "GET":    {"admin", "lider", "miembro"},  # Todos ven el tablero
    "POST":   {"admin", "lider"},             # Solo Admin y Líder crean/asignan tareas
    "PUT":    {"admin", "lider", "miembro"},  # Miembro: solo cambia estado (lo valida task-service)
    "DELETE": {"admin", "lider"},             # Miembro nunca borra
}


def normalizar_rol(rol) -> str:
    """'Líder', 'LIDER ' y 'lider' -> 'lider'."""
    texto = unicodedata.normalize("NFD", str(rol or ""))
    sin_acentos = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return sin_acentos.strip().lower()


def validar_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")


def obtener_usuario(request: Request):
    """Extrae y valida el Bearer token. Devuelve (token, payload)."""
    auth_header = request.headers.get("Authorization", "")
    esquema, _, token = auth_header.partition(" ")
    if esquema.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Falta el token de autenticación")
    return token, validar_token(token)


async def reenviar(method: str, url: str, **kwargs):
    """Llama a un microservicio y traduce sus fallos a 503/504 controlados."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(method, url, **kwargs)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="El servicio tardó demasiado en responder")
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Servicio no disponible")

    if response.status_code == 204:
        return Response(status_code=204)
    try:
        contenido = response.json()
    except ValueError:
        contenido = {"detail": response.text}
    return JSONResponse(status_code=response.status_code, content=contenido)


@app.get("/")
def health_check():
    return {"status": "ok", "service": "API Gateway funcionando correctamente"}

# ==========================================
# RUTAS PÚBLICAS (No requieren Token)
# ==========================================
@app.post("/auth/login")
async def login_proxy(request: Request):
    """Redirige el login al auth-service"""
    body = await request.json()
    return await reenviar("POST", f"{AUTH_SERVICE_URL}/login", json=body)


@app.post("/auth/register")
async def register_proxy(request: Request):
    """Redirige el registro al auth-service"""
    body = await request.json()
    return await reenviar("POST", f"{AUTH_SERVICE_URL}/register", json=body)

# ==========================================
# RUTAS PROTEGIDAS (Token JWT + permiso por rol)
# ==========================================
@app.api_route("/tasks/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def tasks_proxy(request: Request, path: str):
    # 1. Autenticación: ¿quién eres? (401 si falla)
    token, usuario = obtener_usuario(request)

    # 2. Autorización: ¿puedes hacer esto? (403 si no; rol desconocido = denegado)
    rol = normalizar_rol(usuario.get("rol"))
    if rol not in PERMISOS_TASKS.get(request.method, set()):
        raise HTTPException(
            status_code=403,
            detail=f"El rol '{usuario.get('rol')}' no tiene permiso para {request.method} en /tasks",
        )

    # 3. Reenviar con la identidad ya verificada.
    #    Los headers se construyen desde cero: lo que mande el cliente en
    #    X-User-* nunca llega al task-service.
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": request.headers.get("content-type", "application/json"),
        "X-User-Email": str(usuario.get("sub", "")),
        "X-User-Role": rol,  # admin | lider | miembro
    }
    return await reenviar(
        request.method,
        f"{TASK_SERVICE_URL}/{path}",
        content=await request.body(),
        headers=headers,
        params=request.query_params,
    )