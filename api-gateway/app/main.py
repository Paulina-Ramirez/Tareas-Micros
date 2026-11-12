from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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

# Función para validar el Token JWT
def validar_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload # Retorna el email y el rol
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
@app.api_route("/tasks/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def tasks_proxy(request: Request, path: str):
    """Redirige peticiones al task-service validando el token primero"""
    
    # 1. Obtener el token del Header Authorization
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Falta el token de autenticación")

    token = auth_header.split(" ")[1]
    
    # 2. Validar el token (Si falla, lanza error 401 automáticamente)
    usuario_data = validar_token(token)

    # 3. Si el token es válido, redirigir al task-service
    url = f"{TASK_SERVICE_URL}/{path}"
    body = await request.body()
    
    # Pasar el token original al microservicio (por si lo necesita)
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=request.method,
            url=url,
            content=body,
            headers=headers,
            params=request.query_params
        )
    
    return JSONResponse(status_code=response.status_code, content=response.json())