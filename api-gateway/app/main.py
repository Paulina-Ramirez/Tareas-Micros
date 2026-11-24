from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import unicodedata
import httpx
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

# Configuración de seguridad (Debe ser la misma que en auth-service)
SECRET_KEY = "super_secret_key_para_el_proyecto_buap"
ALGORITHM = "HS256"

# URLs de los microservicios (Docker resuelve estos nombres internamente)
AUTH_SERVICE_URL = "http://auth-service:8000"
TASK_SERVICE_URL = "http://task-service:8000"
PRESENCE_SERVICE_URL = "http://presence-service:8000"

ROLES_VALIDOS = {"admin": "Admin", "lider": "Lider", "miembro": "Miembro"}

def normalizar_rol(rol):
    """'Líder', 'lider' o 'LIDER' -> 'Lider'. Devuelve None si no es un rol válido.
    Así el header X-User-Role siempre sale en ASCII (los headers HTTP no admiten
    acentos) y un rol inventado se rechaza aquí, antes de llegar a los servicios."""
    if not rol or not isinstance(rol, str):
        return None
    limpio = unicodedata.normalize("NFD", rol.strip().lower())
    limpio = "".join(c for c in limpio if unicodedata.category(c) != "Mn")
    return ROLES_VALIDOS.get(limpio)

# Función para validar el Token JWT
def validar_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload # Retorna el id, el email y el rol
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")

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
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{AUTH_SERVICE_URL}/login", json=body)
    return JSONResponse(status_code=response.status_code, content=response.json())

@app.post("/auth/register")
async def register_proxy(request: Request):
    """Redirige el registro al auth-service"""
    body = await request.json()
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{AUTH_SERVICE_URL}/register", json=body)
    return JSONResponse(status_code=response.status_code, content=response.json())

# ==========================================
# RUTAS PROTEGIDAS (Requieren Token JWT)
# ==========================================
async def proxy_servicio(request: Request, base_url: str, nombre: str, prefijo: str, path: str):
    """Valida el token y redirige la petición al microservicio indicado.

    Conserva el prefijo (/tasks, /projects, /notifications, /presence) porque
    así están definidas las rutas dentro de cada microservicio.
    """

    # 1. Obtener el token del Header Authorization
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Falta el token de autenticación")

    token = auth_header.split(" ")[1]

    # 2. Validar el token (Si falla, lanza error 401 automáticamente)
    usuario_data = validar_token(token)

    # El token debe traer el id y el rol del usuario
    id_usuario = usuario_data.get("id")
    rol = normalizar_rol(usuario_data.get("rol"))
    if id_usuario is None or not usuario_data.get("rol"):
        raise HTTPException(
            status_code=401,
            detail="El token no trae id o rol. Vuelve a iniciar sesión",
        )
    if rol is None:
        raise HTTPException(status_code=401, detail="El token trae un rol no válido")

    # 3. Si el token es válido, redirigir al microservicio
    url = f"{base_url}/{prefijo}/{path}"
    body = await request.body()

    # Los headers se construyen DESDE CERO: nunca se reenvían los del cliente.
    # Así nadie puede falsificar X-User-Id / X-User-Role.
    headers = {
        "Authorization": f"Bearer {token}",
        "X-User-Id": str(id_usuario),
        "X-User-Role": str(rol),
    }
    content_type = request.headers.get("content-type")
    if content_type:
        headers["Content-Type"] = content_type

    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=request.method,
                url=url,
                content=body,
                headers=headers,
                params=request.query_params
            )
    except httpx.RequestError:
        # Aislamiento de fallos: si el microservicio no responde, error controlado
        raise HTTPException(status_code=503, detail=f"{nombre} no disponible")

    try:
        contenido = response.json()
    except ValueError:
        contenido = {"detail": response.text}

    return JSONResponse(status_code=response.status_code, content=contenido)


@app.api_route("/tasks/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def tasks_proxy(request: Request, path: str):
    """Redirige /tasks/... al task-service"""
    return await proxy_servicio(request, TASK_SERVICE_URL, "Task Service", "tasks", path)


@app.api_route("/projects/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def projects_proxy(request: Request, path: str):
    """Redirige /projects/... al task-service"""
    return await proxy_servicio(request, TASK_SERVICE_URL, "Task Service", "projects", path)


@app.api_route("/notifications/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def notifications_proxy(request: Request, path: str):
    """Redirige /notifications/... (historial) al task-service"""
    return await proxy_servicio(request, TASK_SERVICE_URL, "Task Service", "notifications", path)


@app.api_route("/presence/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def presence_proxy(request: Request, path: str):
    """Redirige /presence/... al presence-service"""
    return await proxy_servicio(request, PRESENCE_SERVICE_URL, "Presence Service", "presence", path)
