# @AI_GENERATED: Kiro v1.0
"""
缓存服务 — Redis 优先，降级为内存缓存
"""
import json
import time
import logging
from typing import Optional, Any, Dict

logger = logging.getLogger(__name__)

# 默认缓存过期时间（秒）
DEFAULT_TTL = 3600  # 1 小时

# Redis 连接（可选）
_redis_client = None
_redis_available = False


def _init_redis() -> bool:
    """尝试初始化 Redis 连接"""
    global _redis_client, _redis_available
    try:
        import redis
        import os
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        _redis_client = redis.from_url(redis_url, decode_responses=True, socket_timeout=2)
        _redis_client.ping()
        _redis_available = True
        logger.info(f"Redis 缓存已连接: {redis_url}")
        return True
    except Exception as e:
        _redis_available = False
        _redis_client = None
        logger.info(f"Redis 不可用，降级为内存缓存: {e}")
        return False


# 内存缓存降级方案
_memory_cache: Dict[str, Dict[str, Any]] = {}


class CacheService:
    """统一缓存服务：Redis 优先，降级内存"""

    def __init__(self, prefix: str = "wf_agent", ttl: int = DEFAULT_TTL):
        self.prefix = prefix
        self.ttl = ttl
        # 延迟初始化 Redis
        if not _redis_available and _redis_client is None:
            _init_redis()

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        full_key = self._key(key)
        # 尝试 Redis
        if _redis_available and _redis_client:
            try:
                val = _redis_client.get(full_key)
                if val is not None:
                    return json.loads(val)
                return None
            except Exception as e:
                logger.debug(f"Redis get 失败: {e}")
        # 降级内存缓存
        entry = _memory_cache.get(full_key)
        if entry is None:
            return None
        if time.time() > entry["expires"]:
            del _memory_cache[full_key]
            return None
        return entry["value"]

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值"""
        full_key = self._key(key)
        ttl = ttl or self.ttl
        # 尝试 Redis
        if _redis_available and _redis_client:
            try:
                _redis_client.setex(full_key, ttl, json.dumps(value, ensure_ascii=False, default=str))
                return True
            except Exception as e:
                logger.debug(f"Redis set 失败: {e}")
        # 降级内存缓存
        _memory_cache[full_key] = {
            "value": value,
            "expires": time.time() + ttl,
        }
        return True

    def delete(self, key: str) -> bool:
        """删除缓存"""
        full_key = self._key(key)
        if _redis_available and _redis_client:
            try:
                _redis_client.delete(full_key)
            except Exception:
                pass
        _memory_cache.pop(full_key, None)
        return True

    def clear_prefix(self, sub_prefix: str = "") -> int:
        """清除指定前缀的所有缓存"""
        pattern = self._key(sub_prefix)
        count = 0
        # 内存缓存
        keys_to_del = [k for k in _memory_cache if k.startswith(pattern)]
        for k in keys_to_del:
            del _memory_cache[k]
            count += 1
        # Redis
        if _redis_available and _redis_client:
            try:
                for k in _redis_client.scan_iter(f"{pattern}*"):
                    _redis_client.delete(k)
                    count += 1
            except Exception:
                pass
        return count


# 全局缓存实例
scenario_cache = CacheService(prefix="wf_agent:scenarios")
constraint_cache = CacheService(prefix="wf_agent:constraints")
# @AI_GENERATED: end
