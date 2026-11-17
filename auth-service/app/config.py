import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:adminpassword@db:5432/taskdb")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Única fuente de verdad para los JWT (debe ser igual en el Gateway)
SECRET_KEY = os.getenv("SECRET_KEY") or "super_secret_key_para_el_proyecto_buap"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60