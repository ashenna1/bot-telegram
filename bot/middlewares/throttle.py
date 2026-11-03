"""
Simple throttling middleware (per-user 0.8s anti-flood)
"""
import time
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

class ThrottleMiddleware(BaseMiddleware):
    def __init__(self, rate: float = 0.8):
        self.rate = rate
        self._last: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user and isinstance(event, (Message, CallbackQuery)):
            now = time.monotonic()
            last = self._last.get(user.id, 0)
            if now - last < self.rate:
                return  # drop flood
            self._last[user.id] = now
        return await handler(event, data)
