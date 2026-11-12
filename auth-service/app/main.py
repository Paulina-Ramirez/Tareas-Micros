from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import engine, Base, get_db
from app import models, schemas, security

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Auth Service")

@app.get("/")
def health_check(db: Session = Depends(get_db)):
    return {"status": "ok", "service": "Auth Service conectado a la BD"}

# 1. Endpoint de Registro
@app.post("/register", response_model=schemas.TokenResponse)
def registrar_usuario(user: schemas.UsuarioRegistro, db: Session = Depends(get_db)):
    # Verificar si el correo ya existe
    db_user = db.query(models.Usuario).filter(models.Usuario.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="El correo ya está registrado")
    
    # Crear el usuario encriptando la contraseña
    nuevo_usuario = models.Usuario(
        nombre=user.nombre,
        email=user.email,
        password_hash=security.get_password_hash(user.password),
        rol=user.rol
    )
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)
    
    # Generar token automáticamente al registrarse
    token = security.create_access_token(data={"sub": nuevo_usuario.email, "rol": nuevo_usuario.rol})
    return {"access_token": token, "token_type": "bearer", "rol": nuevo_usuario.rol}

# 2. Endpoint de Login
@app.post("/login", response_model=schemas.TokenResponse)
def login(user: schemas.UsuarioLogin, db: Session = Depends(get_db)):
    # Buscar al usuario
    db_user = db.query(models.Usuario).filter(models.Usuario.email == user.email).first()
    if not db_user:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    
    # Verificar contraseña
    if not security.verify_password(user.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    
    # Generar token
    token = security.create_access_token(data={"sub": db_user.email, "rol": db_user.rol})
    return {"access_token": token, "token_type": "bearer", "rol": db_user.rol}