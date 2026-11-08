import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:adminpassword@db:5432/taskdb")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
SECRET_KEY = "super_secret_key_cambiar_en_produccion" # Para los JWT
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30