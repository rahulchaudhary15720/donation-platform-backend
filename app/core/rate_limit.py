from fastapi import HTTPException, Request
from app.core.config import settings
import time
import threading

try:
    import redis
    from redis.exceptions import RedisError
except Exception:
    redis = None
    class RedisError(Exception):
        pass

_redis_client = None
_mem_lock = threading.Lock()
_mem_store: dict[str, tuple[int, float]] = {}

def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"

def _get_redis():
    global _redis_client
    if redis is None:
        return None
    if _redis_client is None:
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client

def _mem_rate_limit(key: str, max_requests: int, window: int):
    now = time.time()
    with _mem_lock:
        count, expires_at = _mem_store.get(key, (0, now + window))
        if now > expires_at:
            count, expires_at = 0, now + window
        count += 1
        _mem_store[key] = (count, expires_at)
        if count > max_requests:
            raise HTTPException(status_code=429, detail="Too many requests")

def rate_limit(key_prefix: str, limit: int | None = None, window_seconds: int | None = None):
    def dependency(request: Request):
        if not settings.RATE_LIMIT_ENABLED:
            return
        max_requests = limit or settings.RATE_LIMIT_MAX_REQUESTS
        window = window_seconds or settings.RATE_LIMIT_WINDOW_SECONDS
        key = f"rl:{key_prefix}:{_get_client_ip(request)}"
        try:
            client = _get_redis()
            if client is None:
                _mem_rate_limit(key, max_requests, window)
                return
            count = client.incr(key)
            if count == 1:
                client.expire(key, window)
            if count > max_requests:
                raise HTTPException(status_code=429, detail="Too many requests")
        except RedisError:
            raise HTTPException(status_code=503, detail="Rate limiter unavailable")
    return dependency
