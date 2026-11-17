from pydantic import BaseModel, EmailStr, Field
from typing import Literal

class UsuarioRegistro(BaseModel):
    nombre: str
    email: EmailStr
    password: str = Field(min_length=6, max_length=72)
    rol: Literal["Admin", "Lider", "Miembro"] = "Miembro"

class UsuarioLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    rol: Literal["Admin", "Lider", "Miembro"] = "Miembro"