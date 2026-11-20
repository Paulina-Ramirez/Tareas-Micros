from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class TareaBase(BaseModel):
    titulo: str
    descripcion: Optional[str] = None
    id_proyecto: int
    id_asignado: int
    estado: str = "Pendiente"
    fecha_vencimiento: Optional[datetime] = None

class TareaCreate(TareaBase):
    pass

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