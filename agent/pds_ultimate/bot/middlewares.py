"""
PDS-Ultimate Bot Middlewares
==============================
Middleware для Aiogram:
- AuthMiddleware: Пропускает ТОЛЬКО владельца (TG_OWNER_ID)
- LoggingMiddleware: Логирование всех входящих сообщений
- DatabaseMiddleware: Инъекция сессии БД в хэндлеры
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from sqlalchemy.orm import Session, sessionmaker

from pds_ultimate.config import config, logger


class AuthMiddleware(BaseMiddleware):
    """
    Фильтрация по владельцу.
    Пропускает сообщения ТОЛЬКО от TG_OWNER_ID.
    Все остальные — игнорируются (безопасность).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Извлекаем сообщение из события
        message: Message | None = None

        if isinstance(event, Message):
            message = event
        elif hasattr(event, "message") and isinstance(event.message, Message):
            message = event.message

        if message and message.from_user:
            if message.from_user.id != config.telegram.owner_id:
                logger.debug(
                    f"Отклонено сообщение от user_id={message.from_user.id} "
                    f"(owner_id={config.telegram.owner_id})"
                )
                return  # Игнорируем — не владелец

        return await handler(event, data)


class LoggingMiddleware(BaseMiddleware):
    """
    Логирование всех входящих сообщений.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.from_user:
            content_type = event.content_type
            text_preview = ""
            if event.text:
                text_preview = event.text[:80] + \
                    ("..." if len(event.text) > 80 else "")
            elif event.caption:
                text_preview = f"[caption] {event.caption[:60]}"

            logger.info(
                f"📩 Входящее [{content_type}] от {event.from_user.id}: {text_preview}"
            )

        return await handler(event, data)


class DatabaseMiddleware(BaseMiddleware):
    """
    Инъекция сессии БД в каждый хэндлер.
    Хэндлер получает data["db_session"] — готовую SQLAlchemy сессию.
    Сессия автоматически закрывается после обработки.
    """

    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        session: Session = self._session_factory()
        data["db_session"] = session
        try:
            result = await handler(event, data)
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
