from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, Literal


# ───────────────────────── TAREAS (lo que ya tenían) ─────────────────────────

class TareaBase(BaseModel):
    titulo: str
    descripcion: Optional[str] = None
    id_proyecto: int
    id_asignado: int
    estado: str = "Pendiente"
    fecha_vencimiento: Optional[datetime] = None


# CAMBIO: ya no recibe "estado". Una tarea nueva siempre nace "Pendiente"
# y lo fija el servidor, no el cliente.
class TareaCreate(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    descripcion: Optional[str] = None
    id_proyecto: int
    id_asignado: int
    fecha_vencimiento: Optional[datetime] = None


class TareaUpdate(BaseModel):
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    estado: Optional[str] = None
    id_asignado: Optional[int] = None
    fecha_vencimiento: Optional[datetime] = None


class TareaResponse(TareaBase):
    id: int
    fecha_creacion: datetime

    class Config:
        from_attributes = True


# NUEVO: cuerpo de PUT /tasks/{id}/estado
class EstadoUpdate(BaseModel):
    estado: Literal["Pendiente", "En Progreso", "Completada"]


# ───────────────────────── PROYECTOS (nuevo) ─────────────────────────

class ProyectoCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    # Solo lo usa el Admin (indica a qué Líder le asigna el proyecto).
    # Si quien crea es un Líder, se ignora: el líder es él mismo.
    id_lider: Optional[int] = None


class ProyectoResponse(BaseModel):
    id: int
    nombre: str
    id_lider: int

    class Config:
        from_attributes = True


# ───────────────────────── NOTIFICACIONES (historial) ─────────────────────────

class NotificacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_usuario: int
    mensaje: str
    leida: bool
    fecha_creacion: datetime
