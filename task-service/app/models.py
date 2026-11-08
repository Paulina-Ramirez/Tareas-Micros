from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from app.database import Base

class Proyecto(Base):
    __tablename__ = "proyectos"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    id_lider = Column(Integer, nullable=False) # Relación lógica con Usuarios

class Tarea(Base):
    __tablename__ = "tareas"
    id = Column(Integer, primary_key=True, index=True)
    id_proyecto = Column(Integer, ForeignKey("proyectos.id"), nullable=False)
    id_asignado = Column(Integer, nullable=False) # Relación lógica con Usuarios
    titulo = Column(String(200), nullable=False)
    estado = Column(String(20), default="Pendiente")
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())