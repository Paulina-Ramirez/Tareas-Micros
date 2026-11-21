import unicodedata
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException, status, Depends

ROL_ADMIN = "Admin"
ROL_LIDER = "Lider"
ROL_MIEMBRO = "Miembro"


def normalizar_rol(rol: Optional[str]) -> Optional[str]:
    """Acepta 'Lider' o 'Líder' (con o sin acento / mayúsculas) y devuelve
    el valor canónico, o None si no es un rol válido."""
    if not rol:
        return None
    limpio = unicodedata.normalize("NFD", rol.strip().lower())
    limpio = "".join(c for c in limpio if unicodedata.category(c) != "Mn")
    return {
        "admin": ROL_ADMIN,
        "lider": ROL_LIDER,
        "miembro": ROL_MIEMBRO,
    }.get(limpio)


@dataclass
class UsuarioActual:
    id: int
    rol: str


def get_current_user(
    x_user_id: Optional[str] = Header(default=None),
    x_user_role: Optional[str] = Header(default=None),
) -> UsuarioActual:
    """Lee la identidad que el API Gateway ya validó con el JWT.

    El task-service NO valida el token: confía en los headers X-User-Id y
    X-User-Role que pone el gateway (y que el gateway debe sobrescribir
    siempre, nunca reenviar los que mande el cliente).
    """
    rol = normalizar_rol(x_user_role)
    if x_user_id is None or rol is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identidad de usuario ausente o inválida",
        )
    try:
        id_usuario = int(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-Id inválido",
        )
    return UsuarioActual(id=id_usuario, rol=rol)


def require_roles(*roles_permitidos: str):
    """Dependencia que exige que el usuario tenga alguno de los roles dados."""

    def _verificar(user: UsuarioActual = Depends(get_current_user)) -> UsuarioActual:
        if user.rol not in roles_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tu rol no tiene permiso para esta acción",
            )
        return user

    return _verificar
