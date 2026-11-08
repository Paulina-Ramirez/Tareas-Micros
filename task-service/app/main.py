from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from app.database import engine, Base, get_db
# Aquí importarás los modelos de tareas después

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Task Service")

@app.get("/")
def health_check(db: Session = Depends(get_db)):
    return {"status": "ok", "service": "Task Service conectado a PostgreSQL"}