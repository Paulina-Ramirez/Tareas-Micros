from sqlalchemy import (
    Column, Integer, String, ForeignKey, DateTime, Text, Boolean, Table, MetaData
)
from sqlalchemy.sql import func
from app.database import Base


class Proyecto(Base):
    __tablename__ = "proyectos"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    id_lider = Column(Integer, nullable=False)


class Tarea(Base):
    __tablename__ = "tareas"
    id = Column(Integer, primary_key=True, index=True)
    id_proyecto = Column(Integer, ForeignKey("proyectos.id"), nullable=False)
    id_asignado = Column(Integer, nullable=False)
    titulo = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    fecha_vencimiento = Column(DateTime, nullable=True)
    estado = Column(String(20), default="Pendiente")
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())


# NUEVO: historial de alertas. El task-service inserta aquí dentro de la misma
# transacción que crea/actualiza la tarea. Es una tabla nueva, así que
# create_all() la crea sin necesidad de borrar el volumen otra vez.
class Notificacion(Base):
    __tablename__ = "notificaciones"
    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, nullable=False, index=True)
    mensaje = Column(Text, nullable=False)
    leida = Column(Boolean, nullable=False, default=False)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())


# NUEVO: vista de SOLO LECTURA de la tabla "usuarios" (la crea y es dueña
# el auth-service). Va en un MetaData aparte a propósito: así
# Base.metadata.create_all() del task-service nunca intenta crearla ni
# modificarla.
_usuarios_meta = MetaData()
usuarios = Table(
    "usuarios",
    _usuarios_meta,
    Column("id", Integer, primary_key=True),
    Column("nombre", String),
    Column("rol", String),
)
