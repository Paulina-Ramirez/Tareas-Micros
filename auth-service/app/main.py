from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from app.database import engine, Base, get_db
from app import models

# Crear las tablas en PostgreSQL
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Auth Service - Proyecto Tareas")

@app.get("/")
def health_check(db: Session = Depends(get_db)):
    return {"status": "ok", "service": "Auth Service conectado a la BD"}