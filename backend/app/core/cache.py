import json
import logging
import os
from typing import Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self):
        self.redis_client = None
        self.in_memory_db = {}
        self.redis_url = settings.REDIS_URL
        self._init_redis()

    def _init_redis(self):
        try:
            import redis
            
            # Upstash requires TLS connection. Auto-upgrade connection scheme to 'rediss://' if needed.
            connection_url = self.redis_url
            if connection_url and connection_url.startswith("redis://") and "upstash.io" in connection_url:
                connection_url = connection_url.replace("redis://", "rediss://")
                
            # Connect to Redis
            self.redis_client = redis.from_url(
                connection_url, 
                socket_connect_timeout=2.0, 
                decode_responses=True
            )
            # Test connection
            self.redis_client.ping()
            logger.info("Connected to Redis server", extra={"redis_url": connection_url})
        except Exception as e:
            self.redis_client = None
            logger.warning(f"[CACHE] Redis connection unavailable: {e}. Using In-Memory Cache fallback.")

    def get(self, key: str) -> Optional[Any]:
        if self.redis_client:
            try:
                val = self.redis_client.get(key)
                if val:
                    return json.loads(val)
            except Exception as e:
                logger.error(f"Redis get error: {e}")
        
        # In-memory fallback
        import time
        if key in self.in_memory_db:
            data, expires_at = self.in_memory_db[key]
            if expires_at is None or expires_at > time.time():
                return data
            else:
                del self.in_memory_db[key] # Expired
        return None

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        serialized = json.dumps(value)
        
        if self.redis_client:
            try:
                self.redis_client.set(key, serialized, ex=ttl)
                return
            except Exception as e:
                logger.error(f"Redis set error: {e}")
        
        # In-memory fallback
        import time
        expires_at = time.time() + ttl if ttl else None
        self.in_memory_db[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        if self.redis_client:
            try:
                self.redis_client.delete(key)
            except Exception as e:
                logger.error(f"Redis delete error: {e}")
        
        # In-memory fallback
        if key in self.in_memory_db:
            del self.in_memory_db[key]

    def invalidate_user_cache(self, user_id: str) -> None:
        """
        Invalidates all cache keys for a given user.
        """
        prefix = f"user_cache:{user_id}:"
        
        if self.redis_client:
            try:
                # Scan and delete keys matching prefix
                keys = self.redis_client.keys(f"{prefix}*")
                if keys:
                    self.redis_client.delete(*keys)
                logger.info(f"[CACHE] Invalidated Redis cache keys for user {user_id}")
            except Exception as e:
                logger.error(f"Redis invalidate keys error: {e}")
        
        # In-memory fallback
        keys_to_del = [k for k in self.in_memory_db.keys() if k.startswith(prefix)]
        for k in keys_to_del:
            del self.in_memory_db[k]
        if keys_to_del:
            logger.info(f"[CACHE] Invalidated In-Memory cache keys for user {user_id}")

cache_manager = CacheManager()
