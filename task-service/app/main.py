from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from app.database import engine, Base, get_db
from app import models  # importar los modelos ANTES de create_all para que se creen sus tablas
from app.routers import projects, tasks, notifications

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Task Service")

app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(notifications.router)

@app.get("/")
def health_check(db: Session = Depends(get_db)):
    return {"status": "ok", "service": "Task Service conectado a PostgreSQL"}
