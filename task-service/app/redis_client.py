import os

import redis

_client = None


def get_redis() -> redis.Redis:
    """Cliente Redis único (se crea la primera vez que se usa).
    REDIS_URL viene del .env: redis://redis:6379/0"""
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            os.getenv("REDIS_URL", "redis://redis:6379/0"),
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _client
