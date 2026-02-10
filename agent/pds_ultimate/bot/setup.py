"""
PDS-Ultimate Bot Setup
=========================
Фабричная функция создания бота.
Единая точка сборки: Bot + Dispatcher + роутеры + мидлвари.

Архитектура:
- Bot — экземпляр aiogram.Bot
- Dispatcher — обработка апдейтов
- Роутеры: universal (текст), voice (голос), files (документы/фото)
- Мидлвари: Auth → Logging → Database (в порядке применения)
"""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy.orm import sessionmaker

from pds_ultimate.bot.handlers import files, universal, voice
from pds_ultimate.bot.middlewares import (
    AuthMiddleware,
    DatabaseMiddleware,
    LoggingMiddleware,
)
from pds_ultimate.config import config, logger


async def create_bot(
    session_factory: sessionmaker,
) -> tuple[Bot, Dispatcher]:
    """
    Создать и настроить бота.

    Args:
        session_factory: SQLAlchemy sessionmaker (из init_database)

    Returns:
        (Bot, Dispatcher) — готовые к polling.
    """
    logger.info("🤖 Создание Telegram бота...")

    # ─── 1. Bot instance ─────────────────────────────────────────────
    bot = Bot(
        token=config.telegram.token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )

    # ─── 2. Dispatcher ───────────────────────────────────────────────
    dp = Dispatcher()

    # ─── 3. Регистрация мидлварей (порядок важен!) ───────────────────
    # Database → инжектирует db_session (нужна для Auth проверки регистрации)
    dp.message.middleware(DatabaseMiddleware(session_factory))

    # Auth → проверяет регистрацию пользователя (использует db_session)
    dp.message.outer_middleware(AuthMiddleware())

    # Logging → логируем все входящие
    dp.message.outer_middleware(LoggingMiddleware())

    logger.info("  ✓ Мидлвари зарегистрированы (DB → Auth → Log)")

    # ─── 4. Регистрация роутеров (порядок важен!) ────────────────────
    # voice и files — ПЕРЕД universal, т.к. universal ловит F.text
    dp.include_router(voice.router)     # F.voice, F.video_note
    dp.include_router(files.router)     # F.document, F.photo
    dp.include_router(universal.router)  # CommandStart + F.text

    logger.info("  ✓ Роутеры зарегистрированы (voice → files → universal)")

    # ─── 5. Startup/shutdown хуки ────────────────────────────────────
    dp.startup.register(_on_startup)
    dp.shutdown.register(_on_shutdown)

    logger.info("🤖 Бот создан и готов к работе")
    return bot, dp


async def _on_startup(bot: Bot) -> None:
    """Действия при запуске бота."""
    me = await bot.get_me()
    logger.info(
        f"🚀 Бот запущен: @{me.username} (id: {me.id})"
    )

    # Уведомляем владельца
    try:
        await bot.send_message(
            config.telegram.owner_id,
            "🟢 PDS-Ultimate запущен и готов к работе!\n"
            "Пиши мне что угодно — я пойму.",
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление владельцу: {e}")


async def _on_shutdown(bot: Bot) -> None:
    """Действия при остановке бота."""
    logger.info("🔴 Бот останавливается...")

    try:
        await bot.send_message(
            config.telegram.owner_id,
            "🔴 PDS-Ultimate остановлен.",
        )
    except Exception:
        pass

    # Закрываем сессию бота
    await bot.session.close()
    logger.info("🔴 Бот остановлен")


async def start_polling(bot: Bot, dp: Dispatcher) -> None:
    """
    Запустить long polling.
    Вынесено отдельно для удобства управления из main.py.
    """
    logger.info("📡 Запуск polling...")

    await dp.start_polling(
        bot,
        allowed_updates=[
            "message",
            "callback_query",  # на будущее, если понадобится
        ],
        drop_pending_updates=True,  # Не обрабатываем старые сообщения
    )
