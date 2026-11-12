from pydantic import BaseModel, EmailStr

class UsuarioRegistro(BaseModel):
    nombre: str
    email: EmailStr
    password: str
    rol: str = "Miembro"  # Por defecto, pero puede ser Admin o Lider

class UsuarioLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    rol: str