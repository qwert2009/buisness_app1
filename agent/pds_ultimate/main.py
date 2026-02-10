"""
PDS-Ultimate — Точка входа
============================
Запуск всей системы: инициализация БД, LLM, модулей, интеграций, Scheduler, Telegram Bot.

Wiring-архитектура (Part 4 + Part 5):
- main.py создаёт SessionFactory
- Передаёт его во все модули и бот
- Запускает интеграции (Telethon, WhatsApp, Gmail)
- Подключает модули к планировщику
- Связывает Bot → Scheduler для отправки напоминаний

Использование:
    python -m pds_ultimate.main
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from pds_ultimate.config import config, logger

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def main():
    """Главная точка входа."""

    logger.info("=" * 60)
    logger.info("  PDS-ULTIMATE v1.0 — Запуск системы")
    logger.info("=" * 60)

    # ─── 1. Валидация конфигурации ───────────────────────────────────────
    logger.info("[1/7] Валидация конфигурации...")
    try:
        warnings = config.validate()
        for w in warnings:
            logger.warning(f"  ⚠ {w}")
        logger.info("  ✅ Конфигурация валидна")
    except ValueError as e:
        logger.critical(f"  ❌ Критическая ошибка конфигурации: {e}")
        logger.critical("  Проверьте файл .env (скопируйте из .env.example)")
        sys.exit(1)

    # ─── 2. Инициализация базы данных ────────────────────────────────────
    logger.info("[2/7] Инициализация базы данных...")
    from pds_ultimate.core.database import init_database
    engine, session_factory = init_database()
    logger.info("  ✅ БД готова")

    # ─── 3. Запуск LLM Engine ────────────────────────────────────────────
    logger.info("[3/7] Запуск LLM Engine (DeepSeek API)...")
    from pds_ultimate.core.llm_engine import llm_engine
    await llm_engine.start()
    logger.info("  ✅ LLM Engine запущен")

    # ─── 3.5. Инициализация AI Agent System ─────────────────────────────
    logger.info("[3.5/7] Инициализация AI Agent (ReAct + Tools + Memory)...")
    from pds_ultimate.core.advanced_memory_manager import advanced_memory_manager
    from pds_ultimate.core.business_tools import register_all_tools
    from pds_ultimate.core.cognitive_engine import cognitive_engine
    from pds_ultimate.core.memory import memory_manager

    # Регистрируем бизнес-инструменты
    tools_count = register_all_tools()
    logger.info(f"  🔧 Зарегистрировано {tools_count} инструментов")

    # Загружаем долгосрочную память из БД (оба менеджера)
    with session_factory() as mem_session:
        mem_count = memory_manager.load_from_db(mem_session)
        logger.info(f"  🧠 Загружено {mem_count} записей памяти (basic)")
        adv_count = advanced_memory_manager.load_from_db(mem_session)
        logger.info(f"  🧠 Загружено {adv_count} записей памяти (advanced)")

    # Инициализация multi-user системы
    logger.info("  👥 User Manager: готов к работе")

    # Memory stats
    stats = advanced_memory_manager.get_stats()
    logger.info(
        f"  📊 Advanced Memory: {stats['total']} записей, "
        f"types={stats['by_type']}, failures={stats['failures_stored']}"
    )

    # Cognitive engine stats
    cog_stats = cognitive_engine.get_stats()
    logger.info(
        f"  🧠 Cognitive Engine: role={cog_stats['active_role']}, "
        f"plans={cog_stats['active_plans']}, "
        f"tasks={cog_stats['tasks']['total']}"
    )

    logger.info("  ✅ AI Agent System инициализирована")

    # ─── 4. Запуск интеграций ────────────────────────────────────────────
    logger.info("[4/7] Запуск внешних интеграций...")

    from pds_ultimate.integrations.gmail import gmail_client
    from pds_ultimate.integrations.telethon_client import telethon_client
    from pds_ultimate.integrations.whatsapp import wa_client

    # Telethon (userbot для стиля)
    try:
        await telethon_client.start()
    except Exception as e:
        logger.warning(f"  ⚠ Telethon: {e}")

    # WhatsApp (browser для стиля)
    try:
        await wa_client.start()
    except Exception as e:
        logger.warning(f"  ⚠ WhatsApp: {e}")

    # Gmail (API для отчётов)
    try:
        await gmail_client.start()
    except Exception as e:
        logger.warning(f"  ⚠ Gmail: {e}")

    logger.info("  ✅ Интеграции запущены")

    # ─── 5. Инициализация модулей ────────────────────────────────────────
    logger.info("[5/7] Инициализация бизнес-модулей...")

    # Secretary
    from pds_ultimate.modules.secretary.auto_responder import AutoResponder
    from pds_ultimate.modules.secretary.calendar_mgr import CalendarManager
    from pds_ultimate.modules.secretary.style_analyzer import StyleAnalyzer
    from pds_ultimate.modules.secretary.vip_hub import VIPHub

    calendar_mgr = CalendarManager(session_factory)
    auto_responder = AutoResponder(session_factory)
    vip_hub = VIPHub(session_factory)
    style_analyzer = StyleAnalyzer(session_factory)

    # Загружаем существующий профиль стиля или сканируем
    style_loaded = await style_analyzer.load_existing_profile()
    if not style_loaded and style_analyzer.needs_rescan():
        logger.info("  📝 Запуск первого сканирования стиля...")
        try:
            await style_analyzer.full_scan()
        except Exception as e:
            logger.warning(f"  ⚠ Сканирование стиля отложено: {e}")

    # Logistics
    from pds_ultimate.modules.logistics.archive import ArchiveManager
    from pds_ultimate.modules.logistics.delivery_calc import DeliveryCalculator
    from pds_ultimate.modules.logistics.item_tracker import ItemTracker
    from pds_ultimate.modules.logistics.order_manager import OrderManager

    order_manager = OrderManager(session_factory)
    item_tracker = ItemTracker(session_factory)
    delivery_calc = DeliveryCalculator(session_factory)
    archive_mgr = ArchiveManager(session_factory)

    # Finance
    from pds_ultimate.modules.finance.currency import CurrencyManager
    from pds_ultimate.modules.finance.master_finance import MasterFinance
    from pds_ultimate.modules.finance.profit_calc import ProfitCalculator
    from pds_ultimate.modules.finance.sync_engine import SyncEngine

    master_finance = MasterFinance(session_factory)
    currency_mgr = CurrencyManager(session_factory)
    profit_calc = ProfitCalculator(session_factory)
    sync_engine = SyncEngine(session_factory)

    # Executive
    from pds_ultimate.modules.executive.backup_security import (
        BackupManager,
        SecurityManager,
    )
    from pds_ultimate.modules.executive.morning_brief import MorningBrief

    morning_brief = MorningBrief(session_factory)
    backup_mgr = BackupManager(session_factory)
    security_mgr = SecurityManager(session_factory)

    # Files
    from pds_ultimate.modules.files.file_manager import FileManager

    file_manager = FileManager(session_factory)

    logger.info("  ✅ Все модули инициализированы")

    # ─── 6. Запуск Telegram Bot ──────────────────────────────────────────
    logger.info("[6/7] Запуск Telegram Bot...")
    from pds_ultimate.bot.setup import create_bot, start_polling

    bot, dp = await create_bot(session_factory=session_factory)
    logger.info("  ✅ Telegram Bot создан")

    # ─── 7. Запуск планировщика с реальными обработчиками ────────────────
    logger.info("[7/7] Запуск планировщика задач...")
    from pds_ultimate.core.scheduler import scheduler

    # Передаём зависимости планировщику
    scheduler.set_dependencies(
        session_factory=session_factory,
        bot=bot,
        morning_brief=morning_brief,
        calendar_mgr=calendar_mgr,
        item_tracker=item_tracker,
        backup_mgr=backup_mgr,
    )
    await scheduler.start()
    logger.info("  ✅ Планировщик запущен с реальными модулями")

    logger.info("=" * 60)
    logger.info("  PDS-ULTIMATE — Система запущена и готова к работе")
    logger.info("=" * 60)

    # ─── Запуск polling (блокирующий) ────────────────────────────────────
    try:
        await start_polling(bot, dp)
    finally:
        # ─── Cleanup ─────────────────────────────────────────────────────
        logger.info("Остановка системы...")

        # Сохраняем память агента (оба менеджера)
        try:
            with session_factory() as save_session:
                saved = memory_manager.save_to_db(save_session)
                if saved:
                    logger.info(
                        f"  💾 Сохранено {saved} записей памяти (basic)")
                adv_saved = advanced_memory_manager.save_to_db(save_session)
                if adv_saved:
                    logger.info(
                        f"  💾 Сохранено {adv_saved} записей памяти (advanced)")
                # Pruning before shutdown
                pruned = advanced_memory_manager.prune()
                if pruned:
                    logger.info(
                        f"  🗑️ Pruned {pruned} устаревших записей памяти")
        except Exception as e:
            logger.warning(f"  ⚠ Ошибка сохранения памяти: {e}")

        await scheduler.stop()
        await telethon_client.stop()
        await wa_client.stop()
        await gmail_client.stop()
        await llm_engine.stop()
        logger.info("PDS-ULTIMATE остановлен. До встречи!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
