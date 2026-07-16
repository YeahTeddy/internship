"""
对话记忆管理 — 基于 Redis 的对话历史存储
"""

import json
import time
from typing import Optional

from app.core.logger import get_logger
from app.storage.redis_client import redis_client

logger = get_logger(__name__)

MAX_HISTORY_MESSAGES = 20
SESSION_TTL = 3600
SESSION_INDEX_TTL = 86400


class ConversationMemory:

    def __init__(self, max_messages: int = MAX_HISTORY_MESSAGES, ttl: int = SESSION_TTL):
        self.max_messages = max_messages
        self.ttl = ttl
        self.redis = redis_client

    def _session_key(self, user_id: int, session_id: str) -> str:
        return f"chat:session:{user_id}:{session_id}"

    def _index_key(self, user_id: int) -> str:
        return f"chat:sessions:{user_id}"

    def save_message(self, user_id: int, session_id: str, role: str, content: str):
        key = self._session_key(user_id, session_id)
        message = {"role": role, "content": content, "timestamp": time.time()}
        self.redis.lpush(key, json.dumps(message, ensure_ascii=False))
        self.redis.set(f"{key}:ttl_flag", "1", expire=self.ttl)

        index_key = self._index_key(user_id)
        existing = self.redis.get(f"chat:exists:{user_id}:{session_id}")
        if not existing:
            self.redis.lpush(index_key, session_id)
            self.redis.set(f"chat:exists:{user_id}:{session_id}", "1", expire=SESSION_INDEX_TTL)

    def load_history(self, user_id: int, session_id: str) -> list[dict]:
        key = self._session_key(user_id, session_id)
        raw_messages = self._get_list(key)
        if not raw_messages:
            return []

        messages = []
        for raw in raw_messages[-self.max_messages:]:
            try:
                msg = json.loads(raw) if isinstance(raw, str) else raw
                messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
            except (json.JSONDecodeError, AttributeError):
                continue
        return messages

    def clear_session(self, user_id: int, session_id: str):
        key = self._session_key(user_id, session_id)
        self.redis.delete(key)
        logger.info("清空会话: user=%d, session=%s", user_id, session_id)

    def _get_list(self, key: str) -> list:
        try:
            client = getattr(self.redis, '_client', None)
            if client is not None:
                result = client.lrange(key, 0, -1)
                if result is not None:
                    return result
        except Exception:
            pass
        try:
            cache = getattr(self.redis, '_memory_cache', None)
            if cache is not None:
                return list(cache.get(key, []))
        except Exception:
            pass
        return []


conversation_memory = ConversationMemory()
