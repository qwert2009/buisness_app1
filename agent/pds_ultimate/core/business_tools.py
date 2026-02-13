"""
PDS-Ultimate Business Tools
==============================
Регистрация бизнес-инструментов для AI-агента.

Каждый модуль системы (заказы, финансы, логистика, секретарь)
экспортирует свои возможности как формальные Tool-ы.

Агент (ReAct loop) вызывает их через ToolRegistry.
Это обеспечивает:
- Формальный контракт (параметры, описание)
- Единую точку входа для LLM
- Логирование и обработку ошибок
- Масштабируемость (новые tools = новые возможности)
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from pds_ultimate.config import config, logger
from pds_ultimate.core.tools import Tool, ToolParameter, ToolResult, tool_registry

# ═══════════════════════════════════════════════════════════════════════════════
# ЛОГИСТИКА / ЗАКАЗЫ
# ═══════════════════════════════════════════════════════════════════════════════


async def tool_create_order(items_text: str, db_session=None) -> ToolResult:
    """Создать новый заказ из текстового описания позиций."""
    from pds_ultimate.core.database import (
        ItemStatus,
        Order,
        OrderItem,
        OrderStatus,
    )
    from pds_ultimate.utils.parsers import parser

    if not db_session:
        return ToolResult("create_order", False, "", error="Нет сессии БД")

    result = await parser.parse_text_smart(items_text)
    if not result.items:
        # Пробуем через LLM
        from pds_ultimate.core.llm_engine import llm_engine
        parsed = await llm_engine.parse_order(items_text)
        if not parsed:
            return ToolResult("create_order", False, "",
                              error="Не удалось распознать позиции")
        items_data = parsed
    else:
        items_data = [item.to_dict() for item in result.items]

    order_count = db_session.query(Order).count()
    order_number = f"ORD-{order_count + 1:04d}"

    order = Order(
        order_number=order_number,
        status=OrderStatus.CONFIRMED,
        order_date=date.today(),
    )
    db_session.add(order)
    db_session.flush()

    created_items = []
    for item_data in items_data:
        first_check = date.today() + timedelta(days=config.logistics.first_status_check_days)
        item = OrderItem(
            order_id=order.id,
            name=item_data.get("name", item_data.get("name", "?")),
            quantity=float(item_data.get("quantity", 1)),
            unit=item_data.get("unit", "шт"),
            unit_price=item_data.get("unit_price"),
            price_currency=item_data.get("currency", "USD"),
            weight=item_data.get("weight"),
            status=ItemStatus.PENDING,
            next_check_date=first_check,
        )
        db_session.add(item)
        created_items.append(item_data)

    db_session.commit()

    items_text_lines = "\n".join(
        f"  {i + 1}. {it.get('name', '?')} — {it.get('quantity', '?')} {it.get('unit', 'шт')}"
        for i, it in enumerate(created_items)
    )

    return ToolResult(
        "create_order",
        True,
        f"✅ Заказ {order_number} создан ({len(created_items)} позиций):\n{items_text_lines}",
        data={"order_id": order.id, "order_number": order_number,
              "items_count": len(created_items)},
    )


async def tool_get_orders_status(order_number: str = None, db_session=None) -> ToolResult:
    """Получить статус заказов."""
    from pds_ultimate.core.database import (
        ItemStatus,
        Order,
        OrderItem,
        OrderStatus,
    )

    if not db_session:
        return ToolResult("get_orders_status", False, "", error="Нет сессии БД")

    if order_number:
        order = db_session.query(Order).filter_by(
            order_number=order_number).first()
        if not order:
            return ToolResult("get_orders_status", False, "",
                              error=f"Заказ {order_number} не найден")

        items = db_session.query(OrderItem).filter_by(order_id=order.id).all()
        items_info = []
        for item in items:
            emoji = "✅" if item.status == ItemStatus.ARRIVED else "⏳"
            track = f" | Трек: {item.tracking_number}" if item.tracking_number else ""
            items_info.append(
                f"  {emoji} {item.name} — {item.quantity} {item.unit}{track}")

        text = (
            f"📦 Заказ {order.order_number}\n"
            f"Статус: {order.status.value}\n"
            f"Дата: {order.order_date}\n"
            f"Позиции:\n" + "\n".join(items_info)
        )
        if order.income:
            text += f"\n💰 Доход: {order.income} {order.income_currency}"
        if order.net_profit is not None:
            text += f"\n📊 Чистая прибыль: ${order.net_profit:.2f}"

        return ToolResult("get_orders_status", True, text,
                          data={"order": order.order_number, "status": order.status.value})

    # Все активные
    active = db_session.query(Order).filter(
        Order.status.notin_([OrderStatus.ARCHIVED, OrderStatus.COMPLETED])
    ).all()

    if not active:
        return ToolResult("get_orders_status", True, "Нет активных заказов.")

    lines = ["📋 Активные заказы:\n"]
    for o in active:
        item_count = db_session.query(
            OrderItem).filter_by(order_id=o.id).count()
        pending = db_session.query(OrderItem).filter_by(
            order_id=o.id, status=ItemStatus.PENDING).count()
        lines.append(
            f"• {o.order_number} | {o.status.value} | Позиций: {item_count} (ждём: {pending})")

    return ToolResult("get_orders_status", True, "\n".join(lines),
                      data={"active_count": len(active)})


async def tool_set_income(order_number: str, amount: float,
                          currency: str = "USD", db_session=None) -> ToolResult:
    """Установить доход за заказ."""
    from pds_ultimate.core.database import Order, Transaction, TransactionType

    if not db_session:
        return ToolResult("set_income", False, "", error="Нет сессии БД")

    order = db_session.query(Order).filter_by(
        order_number=order_number).first()
    if not order:
        return ToolResult("set_income", False, "",
                          error=f"Заказ {order_number} не найден")

    order.income = amount
    order.income_currency = currency

    amount_usd = _convert_to_usd(amount, currency)
    db_session.add(Transaction(
        order_id=order.id,
        transaction_type=TransactionType.INCOME,
        amount=amount,
        currency=currency,
        amount_usd=amount_usd,
        description=f"Оплата за заказ {order.order_number}",
        transaction_date=date.today(),
    ))
    db_session.commit()

    return ToolResult("set_income", True,
                      f"✅ Доход за {order_number}: {amount} {currency} (${amount_usd:.2f})",
                      data={"order": order_number, "amount_usd": amount_usd})


async def tool_set_expense(order_number: str, amount: float,
                           currency: str = "USD", db_session=None) -> ToolResult:
    """Установить расход на товар."""
    from pds_ultimate.core.database import (
        Order,
        OrderStatus,
        Transaction,
        TransactionType,
    )

    if not db_session:
        return ToolResult("set_expense", False, "", error="Нет сессии БД")

    order = db_session.query(Order).filter_by(
        order_number=order_number).first()
    if not order:
        return ToolResult("set_expense", False, "",
                          error=f"Заказ {order_number} не найден")

    order.expense_goods = amount
    order.expense_goods_currency = currency

    amount_usd = _convert_to_usd(amount, currency)
    db_session.add(Transaction(
        order_id=order.id,
        transaction_type=TransactionType.EXPENSE_GOODS,
        amount=amount,
        currency=currency,
        amount_usd=amount_usd,
        description=f"Оплата поставщику за {order.order_number}",
        transaction_date=date.today(),
    ))

    income_usd = _convert_to_usd(
        order.income or 0, order.income_currency or "USD")
    remainder = income_usd - amount_usd

    order.status = OrderStatus.TRACKING
    db_session.commit()

    return ToolResult("set_expense", True,
                      f"✅ Расход на товар: {amount} {currency}\n📊 Остаток: ${remainder:.2f}",
                      data={"order": order_number, "remainder_usd": remainder})


# ═══════════════════════════════════════════════════════════════════════════════
# ФИНАНСЫ
# ═══════════════════════════════════════════════════════════════════════════════

async def tool_get_financial_summary(db_session=None) -> ToolResult:
    """Получить финансовую сводку."""
    from sqlalchemy import func

    from pds_ultimate.core.database import (
        Order,
        OrderStatus,
        Transaction,
        TransactionType,
    )

    if not db_session:
        return ToolResult("get_financial_summary", False, "", error="Нет сессии БД")

    total_income = db_session.query(
        func.sum(Transaction.amount_usd)
    ).filter_by(transaction_type=TransactionType.INCOME).scalar() or 0

    total_goods = db_session.query(
        func.sum(Transaction.amount_usd)
    ).filter_by(transaction_type=TransactionType.EXPENSE_GOODS).scalar() or 0

    total_delivery = db_session.query(
        func.sum(Transaction.amount_usd)
    ).filter_by(transaction_type=TransactionType.EXPENSE_DELIVERY).scalar() or 0

    total_savings = db_session.query(
        func.sum(Transaction.amount_usd)
    ).filter_by(transaction_type=TransactionType.PROFIT_SAVINGS).scalar() or 0

    total_profit_exp = db_session.query(
        func.sum(Transaction.amount_usd)
    ).filter_by(transaction_type=TransactionType.PROFIT_EXPENSES).scalar() or 0

    completed = db_session.query(Order).filter(
        Order.status.in_([OrderStatus.COMPLETED, OrderStatus.ARCHIVED])
    ).count()

    active = db_session.query(Order).filter(
        Order.status.notin_([OrderStatus.ARCHIVED, OrderStatus.COMPLETED])
    ).count()

    net = total_income - total_goods - total_delivery

    text = (
        f"💰 ФИНАНСОВАЯ СВОДКА (USD)\n\n"
        f"Общий доход: ${total_income:.2f}\n"
        f"Расходы на товар: ${total_goods:.2f}\n"
        f"Расходы на доставку: ${total_delivery:.2f}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"Чистая прибыль: ${net:.2f}\n\n"
        f"На расходы: ${total_profit_exp:.2f}\n"
        f"Отложено: ${total_savings:.2f}\n\n"
        f"Активных заказов: {active}\n"
        f"Закрытых: {completed}"
    )

    return ToolResult("get_financial_summary", True, text, data={
        "income": total_income, "goods": total_goods,
        "delivery": total_delivery, "net_profit": net,
        "savings": total_savings, "active_orders": active,
    })


async def tool_convert_currency(amount: float, from_currency: str,
                                to_currency: str = "USD", **kwargs) -> ToolResult:
    """Конвертировать валюту."""
    rates = {"TMT": 19.5, "CNY": 7.1}

    # from → USD
    if from_currency == "USD":
        usd = amount
    elif from_currency in rates:
        usd = amount / rates[from_currency]
    else:
        return ToolResult("convert_currency", False, "",
                          error=f"Неизвестная валюта: {from_currency}")

    # USD → to
    if to_currency == "USD":
        result_amount = usd
    elif to_currency in rates:
        result_amount = usd * rates[to_currency]
    else:
        return ToolResult("convert_currency", False, "",
                          error=f"Неизвестная валюта: {to_currency}")

    return ToolResult("convert_currency", True,
                      f"{amount} {from_currency} = {result_amount:.2f} {to_currency}",
                      data={"result": result_amount, "currency": to_currency})


# ═══════════════════════════════════════════════════════════════════════════════
# КОНТАКТЫ
# ═══════════════════════════════════════════════════════════════════════════════

async def tool_save_contact_note(name: str, note: str, is_warning: bool = False,
                                 db_session=None) -> ToolResult:
    """Сохранить заметку о контакте."""
    from pds_ultimate.core.database import Contact, ContactType

    if not db_session:
        return ToolResult("save_contact_note", False, "", error="Нет сессии БД")

    contact = db_session.query(Contact).filter(
        Contact.name.ilike(f"%{name}%")
    ).first()

    if not contact:
        contact = Contact(name=name, contact_type=ContactType.OTHER)
        db_session.add(contact)
        db_session.flush()

    today = date.today()
    if is_warning:
        existing = contact.warnings or ""
        contact.warnings = f"{existing}\n[{today}] {note}".strip()
    else:
        existing = contact.notes or ""
        contact.notes = f"{existing}\n[{today}] {note}".strip()

    db_session.commit()

    emoji = "⚠️" if is_warning else "📝"
    return ToolResult("save_contact_note", True,
                      f"{emoji} Записал о «{contact.name}»: {note}")


async def tool_find_contact(query: str, db_session=None) -> ToolResult:
    """Найти контакт по имени."""
    from pds_ultimate.core.database import Contact

    if not db_session:
        return ToolResult("find_contact", False, "", error="Нет сессии БД")

    contacts = db_session.query(Contact).filter(
        Contact.name.ilike(f"%{query}%")
    ).limit(10).all()

    if not contacts:
        return ToolResult("find_contact", True, f"Контакт «{query}» не найден.")

    lines = [f"🔍 Найдено ({len(contacts)}):"]
    for c in contacts:
        info = f"• {c.name} ({c.contact_type.value})"
        if c.phone:
            info += f" | {c.phone}"
        if c.warnings:
            info += " ⚠️"
        if c.notes:
            last_note = c.notes.strip().split("\n")[-1]
            info += f"\n  📝 {last_note[:80]}"
        lines.append(info)

    return ToolResult("find_contact", True, "\n".join(lines),
                      data={"count": len(contacts)})


# ═══════════════════════════════════════════════════════════════════════════════
# КАЛЕНДАРЬ & НАПОМИНАНИЯ
# ═══════════════════════════════════════════════════════════════════════════════

async def tool_create_reminder(message: str, scheduled_at: str,
                               db_session=None) -> ToolResult:
    """Создать напоминание."""
    from datetime import datetime

    from pds_ultimate.core.database import Reminder, ReminderStatus

    if not db_session:
        return ToolResult("create_reminder", False, "", error="Нет сессии БД")

    try:
        # Пробуем разные форматы даты
        dt = None
        for fmt in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%Y-%m-%dT%H:%M", "%d.%m.%Y"):
            try:
                dt = datetime.strptime(scheduled_at, fmt)
                break
            except ValueError:
                continue

        if not dt:
            return ToolResult("create_reminder", False, "",
                              error=f"Не распознан формат даты: {scheduled_at}")

        reminder = Reminder(
            message=message,
            scheduled_at=dt,
            status=ReminderStatus.PENDING,
            reminder_minutes=30,
        )
        db_session.add(reminder)
        db_session.commit()

        return ToolResult("create_reminder", True,
                          f"⏰ Напоминание создано: «{message}» на {dt.strftime('%d.%m.%Y %H:%M')}",
                          data={"reminder_id": reminder.id})

    except Exception as e:
        return ToolResult("create_reminder", False, "", error=str(e))


async def tool_create_calendar_event(title: str, event_date: str,
                                     description: str = "",
                                     db_session=None) -> ToolResult:
    """Создать событие в календаре."""
    from datetime import datetime

    from pds_ultimate.core.database import CalendarEvent

    if not db_session:
        return ToolResult("create_calendar_event", False, "", error="Нет сессии БД")

    try:
        dt = None
        for fmt in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%Y-%m-%dT%H:%M", "%d.%m.%Y"):
            try:
                dt = datetime.strptime(event_date, fmt)
                break
            except ValueError:
                continue

        if not dt:
            return ToolResult("create_calendar_event", False, "",
                              error=f"Не распознан формат даты: {event_date}")

        event = CalendarEvent(
            title=title,
            event_date=dt,
            description=description,
            reminder_minutes=30,
        )
        db_session.add(event)
        db_session.commit()

        return ToolResult("create_calendar_event", True,
                          f"📅 Событие создано: «{title}» на {dt.strftime('%d.%m.%Y %H:%M')}",
                          data={"event_id": event.id})

    except Exception as e:
        return ToolResult("create_calendar_event", False, "", error=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# УТРЕННИЙ БРИФИНГ & ОТЧЁТЫ
# ═══════════════════════════════════════════════════════════════════════════════

async def tool_morning_brief(db_session=None) -> ToolResult:
    """Сформировать утренний брифинг."""
    from sqlalchemy import func

    from pds_ultimate.core.database import (
        ItemStatus,
        Order,
        OrderItem,
        OrderStatus,
        Transaction,
        TransactionType,
    )

    if not db_session:
        return ToolResult("morning_brief", False, "", error="Нет сессии БД")

    active_orders = db_session.query(Order).filter(
        Order.status.notin_([OrderStatus.ARCHIVED, OrderStatus.COMPLETED])
    ).count()

    pending_items = db_session.query(OrderItem).filter_by(
        status=ItemStatus.PENDING
    ).count()

    total_income = db_session.query(
        func.sum(Transaction.amount_usd)
    ).filter_by(transaction_type=TransactionType.INCOME).scalar() or 0

    total_expenses = db_session.query(
        func.sum(Transaction.amount_usd)
    ).filter(Transaction.transaction_type.in_([
        TransactionType.EXPENSE_GOODS,
        TransactionType.EXPENSE_DELIVERY,
    ])).scalar() or 0

    total_savings = db_session.query(
        func.sum(Transaction.amount_usd)
    ).filter_by(transaction_type=TransactionType.PROFIT_SAVINGS).scalar() or 0

    balance = total_income - total_expenses
    today = date.today().strftime("%d.%m.%Y")

    text = (
        f"☀️ БРИФИНГ НА {today}\n\n"
        f"📦 Активных заказов: {active_orders}\n"
        f"📋 Ожидаем позиций: {pending_items}\n"
        f"💰 Баланс: ${balance:.2f}\n"
        f"🏦 Отложено: ${total_savings:.2f}\n\n"
        f"Что делаем сегодня, босс?"
    )

    return ToolResult("morning_brief", True, text, data={
        "active_orders": active_orders, "pending_items": pending_items,
        "balance": balance, "savings": total_savings,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# ПЕРЕВОД & ТЕКСТ
# ═══════════════════════════════════════════════════════════════════════════════

async def tool_translate(text: str, target_lang: str = "ru",
                         source_lang: str = None, **kwargs) -> ToolResult:
    """Перевести текст."""
    from pds_ultimate.core.llm_engine import llm_engine

    result = await llm_engine.translate(text, target_lang, source_lang)
    return ToolResult("translate", True, result,
                      data={"target_lang": target_lang})


async def tool_summarize(text: str, **kwargs) -> ToolResult:
    """Создать краткое саммари текста."""
    from pds_ultimate.core.llm_engine import llm_engine

    result = await llm_engine.summarize(text)
    return ToolResult("summarize", True, result)


# ═══════════════════════════════════════════════════════════════════════════════
# БЕЗОПАСНОСТЬ
# ═══════════════════════════════════════════════════════════════════════════════

async def tool_security_emergency(db_session=None) -> ToolResult:
    """Активировать экстренный режим безопасности."""
    import os

    from pds_ultimate.config import ALL_ORDERS_ARCHIVE_PATH, MASTER_FINANCE_PATH
    from pds_ultimate.core.database import Transaction

    if not db_session:
        return ToolResult("security_emergency", False, "", error="Нет сессии БД")

    for fp in [MASTER_FINANCE_PATH, ALL_ORDERS_ARCHIVE_PATH]:
        if fp.exists():
            try:
                os.remove(fp)
            except OSError:
                pass

    db_session.query(Transaction).delete()
    db_session.commit()

    logger.critical("🚨 SECURITY MODE ACTIVATED")
    return ToolResult("security_emergency", True,
                      "🔒 Режим безопасности активирован. Финансовые данные удалены.")


# ═══════════════════════════════════════════════════════════════════════════════
# ПАМЯТЬ АГЕНТА (tools для работы с долгосрочной памятью)
# ═══════════════════════════════════════════════════════════════════════════════

async def tool_remember(fact: str, importance: float = 0.5,
                        memory_type: str = "fact", **kwargs) -> ToolResult:
    """Запомнить важный факт."""
    from pds_ultimate.core.memory import memory_manager

    entry = memory_manager.store_fact(
        content=fact,
        importance=importance,
        tags=[memory_type],
        source="agent",
    )
    return ToolResult("remember", True,
                      f"📌 Запомнил: «{fact}» (важность: {importance})")


async def tool_recall(query: str, **kwargs) -> ToolResult:
    """Вспомнить факты по запросу."""
    from pds_ultimate.core.memory import memory_manager

    entries = memory_manager.recall(query, limit=5)
    if not entries:
        return ToolResult("recall", True, "Ничего не найдено в памяти.")

    lines = ["🧠 Вспомнил:"]
    for e in entries:
        lines.append(f"  • [{e.memory_type}] {e.content}")

    return ToolResult("recall", True, "\n".join(lines),
                      data=[e.to_dict() for e in entries])


# ═══════════════════════════════════════════════════════════════════════════════
# УТИЛИТЫ
# ═══════════════════════════════════════════════════════════════════════════════

def _convert_to_usd(amount: float, currency: str) -> float:
    """Конвертировать в USD."""
    if currency == "USD":
        return amount
    rates = config.currency.fixed_rates
    if currency in rates:
        return round(amount / rates[currency], 2)
    return amount


# ═══════════════════════════════════════════════════════════════════════════════
# PART 7: NEW TOOL HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════


async def tool_exchange_rates(
    from_currency: str = "USD",
    to_currency: str = "",
    amount: float = 1.0,
    **kwargs,
) -> ToolResult:
    """Получить курс обмена валют (онлайн + кэш + фиксированные)."""
    from pds_ultimate.integrations.exchange_rates import exchange_service

    try:
        if to_currency:
            result = await exchange_service.convert(
                amount, from_currency.upper(), to_currency.upper()
            )
            if "error" in result:
                return ToolResult(
                    "exchange_rates", False, "",
                    error=result["error"],
                )
            return ToolResult(
                "exchange_rates", True,
                f"💱 {amount:.2f} {from_currency.upper()} = "
                f"{result['result']:.2f} {to_currency.upper()}\n"
                f"Курс: {result['rate']:.4f} "
                f"(источник: {result.get('source', 'unknown')})",
                data=result,
            )

        result = await exchange_service.refresh_all()
        table = exchange_service.format_rates_table()
        return ToolResult(
            "exchange_rates", True, table,
            data={"rates_count": len(result.rates)},
        )

    except Exception as e:
        return ToolResult(
            "exchange_rates", False, "",
            error=f"Ошибка получения курсов: {e}",
        )


async def tool_ocr_recognize(
    file_path: str,
    extract_amounts: bool = False,
    extract_tracking: bool = False,
    **kwargs,
) -> ToolResult:
    """Распознать текст на изображении (OCR)."""
    from pds_ultimate.modules.files.ocr_engine import ocr_engine

    try:
        result = await ocr_engine.recognize(file_path)
        lines = [f"📝 OCR ({result.engine_used})"]
        lines.append(f"Уверенность: {result.avg_confidence:.0%}")
        lines.append(f"\n{result.confident_text[:2000]}")

        data = {"text": result.confident_text,
                "confidence": result.avg_confidence}

        if extract_amounts:
            amounts = await ocr_engine.extract_amounts(file_path)
            if amounts:
                lines.append("\n💰 Суммы:")
                for a in amounts:
                    lines.append(f"  {a.original} → {a.amount} {a.currency}")
                data["amounts"] = [
                    {"amount": a.amount, "currency": a.currency}
                    for a in amounts
                ]

        if extract_tracking:
            tracking = await ocr_engine.extract_tracking_numbers(file_path)
            if tracking:
                lines.append("\n📦 Трекинг:")
                for t in tracking:
                    lines.append(f"  {t.number} ({t.carrier})")
                data["tracking"] = [
                    {"number": t.number, "carrier": t.carrier}
                    for t in tracking
                ]

        return ToolResult(
            "ocr_recognize", True, "\n".join(lines), data=data,
        )

    except Exception as e:
        return ToolResult(
            "ocr_recognize", False, "",
            error=f"Ошибка OCR: {e}",
        )


async def tool_scan_receipt(
    file_path: str,
    save_to_db: bool = True,
    db_session=None,
    **kwargs,
) -> ToolResult:
    """Сканировать чек и распознать расходы."""
    from pds_ultimate.modules.executive.receipt_scanner import receipt_scanner

    try:
        receipt = await receipt_scanner.scan_receipt(file_path)
        text = receipt_scanner.format_receipt(receipt)

        if save_to_db and db_session and receipt.amount:
            saved = await receipt_scanner.save_expense(
                receipt, db_session
            )
            if saved:
                text += "\n\n💾 Сохранено в базу расходов"

        return ToolResult(
            "scan_receipt", True, text,
            data={
                "amount": receipt.amount,
                "currency": receipt.currency,
                "category": receipt.category.value if receipt.category else None,
                "vendor": receipt.vendor,
            },
        )

    except Exception as e:
        return ToolResult(
            "scan_receipt", False, "",
            error=f"Ошибка сканирования чека: {e}",
        )


async def tool_translate_text(
    text: str,
    target_lang: str = "ru",
    source_lang: str = "",
    **kwargs,
) -> ToolResult:
    """Перевести текст через TranslatorService (с бизнес-глоссарием)."""
    from pds_ultimate.modules.executive.translator import translator

    try:
        result = await translator.translate(
            text, target_lang, source_lang or None,
        )
        formatted = translator.format_translation(result)
        return ToolResult(
            "translate_text", True, formatted,
            data={
                "source_lang": result.source_lang,
                "target_lang": result.target_lang,
                "translated": result.translated,
            },
        )

    except Exception as e:
        return ToolResult(
            "translate_text", False, "",
            error=f"Ошибка перевода: {e}",
        )


async def tool_archivist_rename(
    file_path: str,
    description: str = "",
    **kwargs,
) -> ToolResult:
    """Стандартизировать имя файла по корпоративному стандарту."""
    from pds_ultimate.modules.executive.archivist import archivist

    try:
        result = archivist.rename_file(file_path, context=description)
        text = archivist.format_rename_result(result)

        if not result.success:
            return ToolResult(
                "archivist_rename", False, text,
                data=result.to_dict(),
                error=result.error or "Не удалось переименовать",
            )

        return ToolResult(
            "archivist_rename", True, text,
            data=result.to_dict(),
        )

    except Exception as e:
        return ToolResult(
            "archivist_rename", False, "",
            error=f"Ошибка переименования: {e}",
        )


async def tool_convert_file(
    file_path: str,
    target_format: str,
    **kwargs,
) -> ToolResult:
    """Конвертировать файл в другой формат."""
    from pds_ultimate.modules.files.converter import file_converter

    try:
        result = await file_converter.convert(file_path, target_format)
        text = file_converter.format_result(result)

        if result.success:
            return ToolResult(
                "convert_file", True, text,
                data=result.to_dict(),
            )
        return ToolResult(
            "convert_file", False, "",
            error=text,
        )

    except Exception as e:
        return ToolResult(
            "convert_file", False, "",
            error=f"Ошибка конвертации: {e}",
        )


async def tool_google_calendar_events(
    action: str = "today",
    title: str = "",
    start_time: str = "",
    end_time: str = "",
    description: str = "",
    **kwargs,
) -> ToolResult:
    """Работа с Google Calendar (создать/просмотреть события)."""
    from pds_ultimate.integrations.google_calendar import google_calendar

    try:
        if action == "today":
            events = await google_calendar.get_today_events()
            text = google_calendar.format_day_summary(events)
            return ToolResult(
                "google_calendar", True, text,
                data={"events_count": len(events)},
            )

        elif action == "create":
            from datetime import datetime

            if not title or not start_time:
                return ToolResult(
                    "google_calendar", False, "",
                    error="Для создания нужны title и start_time",
                )

            # Parse dates
            from pds_ultimate.utils.validators import parse_date
            start_dt = parse_date(start_time)
            end_dt = parse_date(end_time) if end_time else None
            if not start_dt:
                return ToolResult(
                    "google_calendar", False, "",
                    error=f"Не распознан формат даты: {start_time}",
                )

            created = await google_calendar.create_event(
                summary=title,
                start=start_dt,
                end=end_dt,
                description=description,
            )
            if created:
                return ToolResult(
                    "google_calendar", True,
                    f"📅 Событие создано: «{title}»",
                    data={"event_id": created.id},
                )
            return ToolResult(
                "google_calendar", False, "",
                error="Не удалось создать событие",
            )

        elif action == "free_slots":
            from datetime import datetime

            from pds_ultimate.utils.validators import parse_date
            dt = parse_date(start_time) if start_time else datetime.now()
            ref_date = dt or datetime.now()

            # Get today's events first, then find free slots (sync method)
            events = await google_calendar.get_events(
                ref_date.replace(hour=0, minute=0, second=0, microsecond=0),
            )
            slots = google_calendar.find_free_slots(
                events, reference_date=ref_date,
            )
            if slots:
                text = google_calendar.format_free_slots(slots)
                return ToolResult(
                    "google_calendar", True, text,
                    data={"slots_count": len(slots)},
                )
            return ToolResult(
                "google_calendar", True, "Нет свободных слотов на эту дату.",
            )

        return ToolResult(
            "google_calendar", False, "",
            error=f"Неизвестное действие: {action}",
        )

    except Exception as e:
        return ToolResult(
            "google_calendar", False, "",
            error=f"Ошибка Google Calendar: {e}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# РЕГИСТРАЦИЯ ВСЕХ TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

def register_all_tools() -> int:
    """
    Зарегистрировать все бизнес-инструменты.
    Вызывается при старте системы.

    Returns:
        Количество зарегистрированных tools.
    """
    tools = [
        # ─── Логистика ───────────────────────────────────────────────
        Tool(
            name="create_order",
            description="Создать новый заказ. Принимает текстовое описание позиций товаров.",
            parameters=[
                ToolParameter("items_text", "string",
                              "Текст с позициями (название, количество, единица, цена)", True),
            ],
            handler=tool_create_order,
            category="logistics",
            needs_db=True,
        ),
        Tool(
            name="get_orders_status",
            description="Получить статус заказа или список всех активных заказов.",
            parameters=[
                ToolParameter("order_number", "string",
                              "Номер заказа (например ORD-0001). Если не указан — все активные.", False),
            ],
            handler=tool_get_orders_status,
            category="logistics",
            needs_db=True,
        ),
        Tool(
            name="set_income",
            description="Установить доход (сколько заплатили МНЕ) за заказ.",
            parameters=[
                ToolParameter("order_number", "string", "Номер заказа", True),
                ToolParameter("amount", "number", "Сумма дохода", True),
                ToolParameter("currency", "string",
                              "Валюта (USD/CNY/TMT)", False, "USD"),
            ],
            handler=tool_set_income,
            category="finance",
            needs_db=True,
        ),
        Tool(
            name="set_expense",
            description="Установить расход на товар (сколько Я заплатил поставщику).",
            parameters=[
                ToolParameter("order_number", "string", "Номер заказа", True),
                ToolParameter("amount", "number", "Сумма расхода", True),
                ToolParameter("currency", "string",
                              "Валюта (USD/CNY/TMT)", False, "USD"),
            ],
            handler=tool_set_expense,
            category="finance",
            needs_db=True,
        ),

        # ─── Финансы ─────────────────────────────────────────────────
        Tool(
            name="get_financial_summary",
            description="Получить полную финансовую сводку: доходы, расходы, прибыль, баланс.",
            parameters=[],
            handler=tool_get_financial_summary,
            category="finance",
            needs_db=True,
        ),
        Tool(
            name="convert_currency",
            description="Конвертировать валюту. Фиксированные курсы: 1 USD = 19.5 TMT, 1 USD = 7.1 CNY.",
            parameters=[
                ToolParameter("amount", "number", "Сумма", True),
                ToolParameter("from_currency", "string",
                              "Из какой валюты (USD/CNY/TMT)", True),
                ToolParameter("to_currency", "string",
                              "В какую валюту", False, "USD"),
            ],
            handler=tool_convert_currency,
            category="finance",
        ),

        # ─── Контакты ───────────────────────────────────────────────
        Tool(
            name="save_contact_note",
            description="Сохранить заметку или предупреждение о контрагенте/контакте.",
            parameters=[
                ToolParameter("name", "string", "Имя контакта", True),
                ToolParameter("note", "string", "Текст заметки", True),
                ToolParameter("is_warning", "boolean",
                              "Это предупреждение?", False, False),
            ],
            handler=tool_save_contact_note,
            category="contacts",
            needs_db=True,
        ),
        Tool(
            name="find_contact",
            description="Найти контакт по имени. Показывает заметки и предупреждения.",
            parameters=[
                ToolParameter("query", "string",
                              "Имя или часть имени контакта", True),
            ],
            handler=tool_find_contact,
            category="contacts",
            needs_db=True,
        ),

        # ─── Календарь ──────────────────────────────────────────────
        Tool(
            name="create_reminder",
            description="Создать напоминание на определённую дату и время.",
            parameters=[
                ToolParameter("message", "string", "Текст напоминания", True),
                ToolParameter("scheduled_at", "string",
                              "Дата и время (формат: YYYY-MM-DD HH:MM или DD.MM.YYYY HH:MM)", True),
            ],
            handler=tool_create_reminder,
            category="calendar",
            needs_db=True,
        ),
        Tool(
            name="create_calendar_event",
            description="Создать событие в календаре.",
            parameters=[
                ToolParameter("title", "string", "Название события", True),
                ToolParameter("event_date", "string",
                              "Дата и время (формат: YYYY-MM-DD HH:MM)", True),
                ToolParameter("description", "string",
                              "Описание события", False, ""),
            ],
            handler=tool_create_calendar_event,
            category="calendar",
            needs_db=True,
        ),

        # ─── Отчёты ─────────────────────────────────────────────────
        Tool(
            name="morning_brief",
            description="Сформировать утренний брифинг с обзором заказов, позиций и финансов.",
            parameters=[],
            handler=tool_morning_brief,
            category="reports",
            needs_db=True,
        ),

        # ─── Текст ──────────────────────────────────────────────────
        Tool(
            name="translate",
            description="Перевести текст на другой язык.",
            parameters=[
                ToolParameter("text", "string", "Текст для перевода", True),
                ToolParameter("target_lang", "string",
                              "Целевой язык (ru/en/zh/tr)", False, "ru"),
                ToolParameter("source_lang", "string", "Исходный язык", False),
            ],
            handler=tool_translate,
            category="text",
        ),
        Tool(
            name="summarize",
            description="Создать краткое саммари текста.",
            parameters=[
                ToolParameter("text", "string",
                              "Текст для суммаризации", True),
            ],
            handler=tool_summarize,
            category="text",
        ),

        # ─── Безопасность ────────────────────────────────────────────
        Tool(
            name="security_emergency",
            description="ЭКСТРЕННОЕ УДАЛЕНИЕ финансовых данных. Только по кодовому слову!",
            parameters=[],
            handler=tool_security_emergency,
            category="security",
            needs_db=True,
            visible=False,  # Не показывать в system prompt
        ),

        # ─── Память ─────────────────────────────────────────────────
        Tool(
            name="remember",
            description="Запомнить важный факт, предпочтение или правило для будущего использования.",
            parameters=[
                ToolParameter("fact", "string", "Что запомнить", True),
                ToolParameter("importance", "number",
                              "Важность от 0.0 до 1.0", False, 0.5),
                ToolParameter("memory_type", "string",
                              "Тип: fact/preference/rule/knowledge", False, "fact"),
            ],
            handler=tool_remember,
            category="memory",
        ),
        Tool(
            name="recall",
            description="Вспомнить факты из долгосрочной памяти по ключевым словам.",
            parameters=[
                ToolParameter("query", "string", "Что вспомнить", True),
            ],
            handler=tool_recall,
            category="memory",
        ),

        # ─── Браузер ────────────────────────────────────────────────
        Tool(
            name="web_search",
            description=(
                "Поиск в интернете через DuckDuckGo. Возвращает список "
                "результатов (заголовок, URL, сниппет). Используй для поиска "
                "информации, цен, поставщиков, новостей, курсов."
            ),
            parameters=[
                ToolParameter("query", "string", "Поисковый запрос", True),
                ToolParameter("max_results", "number",
                              "Максимум результатов (1-20)", False, 10),
            ],
            handler=tool_web_search,
            category="browser",
        ),
        Tool(
            name="open_page",
            description=(
                "Открыть веб-страницу и извлечь её содержимое "
                "(текст, ссылки, таблицы, мета-данные). "
                "Используй после web_search чтобы прочитать конкретную страницу."
            ),
            parameters=[
                ToolParameter("url", "string", "URL страницы", True),
            ],
            handler=tool_open_page,
            category="browser",
        ),
        Tool(
            name="browser_screenshot",
            description="Сделать скриншот текущей страницы в браузере.",
            parameters=[
                ToolParameter("full_page", "boolean",
                              "Полная страница (true) или видимая область", False),
            ],
            handler=tool_browser_screenshot,
            category="browser",
        ),
        Tool(
            name="browser_click",
            description="Кликнуть по элементу на странице (CSS-селектор).",
            parameters=[
                ToolParameter("selector", "string",
                              "CSS-селектор элемента", True),
            ],
            handler=tool_browser_click,
            category="browser",
        ),
        Tool(
            name="browser_fill",
            description="Заполнить поле на веб-странице текстом.",
            parameters=[
                ToolParameter("selector", "string", "CSS-селектор поля", True),
                ToolParameter("value", "string", "Текст для ввода", True),
            ],
            handler=tool_browser_fill,
            category="browser",
        ),

        # ─── Исследование (Internet Reasoning) ──────────────────────
        Tool(
            name="research",
            description=(
                "Исследовать вопрос с проверкой множества источников. "
                "Ищет в интернете, извлекает факты, оценивает достоверность, "
                "обнаруживает противоречия и синтезирует ответ. "
                "Используй для проверки фактов, сравнения цен, "
                "анализа рынка, поиска информации."
            ),
            parameters=[
                ToolParameter("query", "string",
                              "Вопрос для исследования", True),
                ToolParameter("max_sources", "number",
                              "Максимум источников (1-10)", False, 5),
            ],
            handler=tool_research,
            category="research",
        ),
        Tool(
            name="deep_research",
            description=(
                "Глубокое исследование с максимальным покрытием. "
                "Расширяет запросы, анализирует до 10 источников, "
                "извлекает больше фактов. Для сложных вопросов, "
                "где нужна проверка из множества независимых источников."
            ),
            parameters=[
                ToolParameter("query", "string",
                              "Вопрос для глубокого исследования", True),
                ToolParameter("max_sources", "number",
                              "Максимум источников (1-15)", False, 10),
            ],
            handler=tool_deep_research,
            category="research",
        ),
        Tool(
            name="quick_search",
            description=(
                "Быстрый поиск с анализом — без расширения запросов. "
                "Для простых вопросов, когда нужен быстрый ответ "
                "с оценкой достоверности."
            ),
            parameters=[
                ToolParameter("query", "string",
                              "Поисковый запрос", True),
            ],
            handler=tool_quick_search,
            category="research",
        ),

        # ─── Part 7: Бизнес-интеграции ──────────────────────────────
        Tool(
            name="exchange_rates",
            description=(
                "Получить актуальный курс обмена валют. "
                "Онлайн-курсы + фиксированные (TMT, CNY). "
                "Можно конвертировать сумму между валютами."
            ),
            parameters=[
                ToolParameter("from_currency", "string",
                              "Из какой валюты (USD/CNY/TMT/EUR)", False, "USD"),
                ToolParameter("to_currency", "string",
                              "В какую валюту (если пусто — все курсы)", False),
                ToolParameter("amount", "number",
                              "Сумма для конвертации", False, 1.0),
            ],
            handler=tool_exchange_rates,
            category="finance",
        ),
        Tool(
            name="google_calendar",
            description=(
                "Работа с Google Calendar: просмотр событий на сегодня, "
                "создание новых событий, поиск свободных слотов."
            ),
            parameters=[
                ToolParameter("action", "string",
                              "Действие: today/create/free_slots", False, "today"),
                ToolParameter("title", "string",
                              "Название события (для create)", False),
                ToolParameter("start_time", "string",
                              "Начало (YYYY-MM-DD HH:MM)", False),
                ToolParameter("end_time", "string",
                              "Конец (YYYY-MM-DD HH:MM)", False),
                ToolParameter("description", "string",
                              "Описание события", False),
            ],
            handler=tool_google_calendar_events,
            category="calendar",
        ),

        # ─── Part 7: Файловые движки ────────────────────────────────
        Tool(
            name="ocr_recognize",
            description=(
                "Распознать текст на изображении (OCR). "
                "Поддержка: фото чеков, накладных, документов. "
                "Языки: RU, EN, ZH. Может извлечь суммы и трекинг-номера."
            ),
            parameters=[
                ToolParameter("file_path", "string",
                              "Путь к файлу изображения", True),
                ToolParameter("extract_amounts", "boolean",
                              "Извлечь денежные суммы", False, False),
                ToolParameter("extract_tracking", "boolean",
                              "Извлечь трекинг-номера", False, False),
            ],
            handler=tool_ocr_recognize,
            category="files",
        ),
        Tool(
            name="convert_file",
            description=(
                "Конвертировать файл в другой формат. "
                "Поддержка: xlsx↔csv, docx→pdf, pdf→txt, json→csv и другие."
            ),
            parameters=[
                ToolParameter("file_path", "string",
                              "Путь к исходному файлу", True),
                ToolParameter("target_format", "string",
                              "Целевой формат (csv/pdf/xlsx/txt/json)", True),
            ],
            handler=tool_convert_file,
            category="files",
        ),

        # ─── Part 7: Исполнительные инструменты ─────────────────────
        Tool(
            name="scan_receipt",
            description=(
                "Сканировать чек/квитанцию: OCR + распознавание "
                "позиций, итога, категории расхода. "
                "Автоматически сохраняет в базу расходов."
            ),
            parameters=[
                ToolParameter("file_path", "string",
                              "Путь к фото чека", True),
                ToolParameter("save_to_db", "boolean",
                              "Сохранить в базу расходов", False, True),
            ],
            handler=tool_scan_receipt,
            category="finance",
            needs_db=True,
        ),
        Tool(
            name="translate_text",
            description=(
                "Перевести текст с бизнес-глоссарием. "
                "Автоопределение языка. "
                "Поддержка: RU, EN, ZH, TK, TR, AR, FA, DE, FR, ES, IT, PT."
            ),
            parameters=[
                ToolParameter("text", "string", "Текст для перевода", True),
                ToolParameter("target_lang", "string",
                              "Целевой язык (ru/en/zh/tk)", False, "ru"),
                ToolParameter("source_lang", "string",
                              "Исходный язык (авто если пусто)", False),
            ],
            handler=tool_translate_text,
            category="text",
        ),
        Tool(
            name="archivist_rename",
            description=(
                "Стандартизировать имя файла по корпоративному стандарту. "
                "Формат: YYYY_MM_DD_Category_Description.ext. "
                "Автоопределение категории из содержимого."
            ),
            parameters=[
                ToolParameter("file_path", "string",
                              "Путь к файлу", True),
                ToolParameter("description", "string",
                              "Описание файла (опционально)", False),
            ],
            handler=tool_archivist_rename,
            category="files",
        ),

        # ─── Part 8: Plugin System ──────────────────────────────────
        Tool(
            name="plugin_connect",
            description=(
                "Подключить внешний API как плагин. "
                "Автоматически определяет тип API по URL или ключу. "
                "Поддержка: OpenAI, Anthropic, Stripe, SendGrid, Twilio, Google, Telegram и другие."
            ),
            parameters=[
                ToolParameter("name", "string",
                              "Имя плагина (например: 'stripe', 'my_api')", True),
                ToolParameter("base_url", "string",
                              "Базовый URL API", True),
                ToolParameter("api_key", "string",
                              "API ключ (если нужен)", False),
                ToolParameter("plugin_type", "string",
                              "Тип: REST_API/LLM_API/PAYMENT_API/MESSAGING_API/CLOUD_API/WEBHOOK", False, "REST_API"),
            ],
            handler=tool_plugin_connect,
            category="plugins",
        ),
        Tool(
            name="plugin_execute",
            description=(
                "Выполнить действие через подключённый плагин. "
                "Вызывает endpoint API с указанными параметрами."
            ),
            parameters=[
                ToolParameter("plugin_name", "string",
                              "Имя плагина", True),
                ToolParameter("endpoint", "string",
                              "Путь endpoint (например '/chat/completions')", True),
                ToolParameter("method", "string",
                              "HTTP метод (GET/POST/PUT/DELETE)", False, "GET"),
                ToolParameter("body", "string",
                              "Тело запроса (JSON строка)", False),
            ],
            handler=tool_plugin_execute,
            category="plugins",
        ),
        Tool(
            name="plugin_list",
            description="Показать список подключённых плагинов и их статус.",
            parameters=[],
            handler=tool_plugin_list,
            category="plugins",
        ),

        # ─── Part 8: Autonomous Tasks ───────────────────────────────
        Tool(
            name="autonomous_task",
            description=(
                "Создать автономную задачу. Агент декомпозирует цель на шаги "
                "и выполняет их самостоятельно с самокоррекцией при ошибках. "
                "Для сложных многошаговых задач."
            ),
            parameters=[
                ToolParameter("goal", "string",
                              "Описание цели (что нужно сделать)", True),
                ToolParameter("priority", "string",
                              "Приоритет: critical/high/normal/low/background", False, "normal"),
                ToolParameter("deadline_hours", "number",
                              "Дедлайн в часах (0 = без дедлайна)", False, 0),
            ],
            handler=tool_autonomous_task,
            category="autonomy",
        ),
        Tool(
            name="task_status",
            description="Показать статус автономных задач.",
            parameters=[
                ToolParameter("task_id", "string",
                              "ID задачи (если пусто — все активные)", False),
            ],
            handler=tool_task_status,
            category="autonomy",
        ),

        # ─── Part 8: Memory & Learning ──────────────────────────────
        Tool(
            name="learn_skill",
            description=(
                "Научить агента новому навыку/стратегии. "
                "Агент запомнит паттерн и будет использовать его в будущем."
            ),
            parameters=[
                ToolParameter("name", "string", "Название навыка", True),
                ToolParameter("pattern", "string",
                              "Regex паттерн для активации (например 'курс|валют')", True),
                ToolParameter("strategy", "string",
                              "Описание стратегии (что делать)", True),
            ],
            handler=tool_learn_skill,
            category="memory",
        ),
        Tool(
            name="memory_stats",
            description="Статистика памяти: навыки, ошибки, паттерны, обучение.",
            parameters=[],
            handler=tool_memory_stats,
            category="memory",
        ),

        # ─── Part 9: Smart Triggers ─────────────────────────────────
        Tool(
            name="set_trigger",
            description=(
                "Установить умный триггер/алерт. "
                "Типы: exchange_rate (курс), balance (баланс), "
                "supplier_silence (тишина поставщика), deadline, price_change. "
                "Или пользовательский триггер на любое условие."
            ),
            parameters=[
                ToolParameter("name", "string", "Название триггера", True),
                ToolParameter("trigger_type", "string",
                              "Тип: threshold/silence/exchange_rate/balance/deadline/price_change/custom",
                              False, "threshold"),
                ToolParameter("field", "string",
                              "Поле для мониторинга (rate_usd_cny, balance, etc.)", False),
                ToolParameter("operator", "string",
                              "Оператор: >/>=/</<=/==/!=", False, ">"),
                ToolParameter("value", "string",
                              "Пороговое значение", False),
                ToolParameter("severity", "string",
                              "Серьёзность: info/warning/critical/emergency", False, "warning"),
                ToolParameter("template", "string",
                              "Шаблон: exchange_rate/balance/supplier_silence/deadline/price_change",
                              False),
            ],
            handler=tool_set_trigger,
            category="triggers",
        ),
        Tool(
            name="list_triggers",
            description="Показать список активных триггеров и историю алертов.",
            parameters=[
                ToolParameter("show_history", "boolean",
                              "Показать историю алертов", False, False),
            ],
            handler=tool_list_triggers,
            category="triggers",
        ),

        # ─── Part 9: Analytics Dashboard ────────────────────────────
        Tool(
            name="dashboard",
            description=(
                "Бизнес-дашборд: ключевые метрики, KPI, тренды. "
                "Записывает метрики и показывает аналитику."
            ),
            parameters=[
                ToolParameter("action", "string",
                              "Действие: show/record/trend/forecast", False, "show"),
                ToolParameter("metric_name", "string",
                              "Имя метрики (для record/trend/forecast)", False),
                ToolParameter("value", "number",
                              "Значение (для record)", False),
                ToolParameter("unit", "string",
                              "Единица измерения", False, ""),
            ],
            handler=tool_dashboard,
            category="analytics",
        ),
        Tool(
            name="kpi_track",
            description=(
                "Отслеживание KPI: создать цель, обновить прогресс, "
                "показать доску KPI."
            ),
            parameters=[
                ToolParameter("action", "string",
                              "Действие: create/update/board", False, "board"),
                ToolParameter("name", "string", "Название KPI", False),
                ToolParameter("target", "number", "Целевое значение", False),
                ToolParameter("value", "number",
                              "Текущее значение (для update)", False),
                ToolParameter("unit", "string",
                              "Единица измерения", False, ""),
            ],
            handler=tool_kpi_track,
            category="analytics",
        ),

        # ─── Part 9: CRM ────────────────────────────────────────────
        Tool(
            name="rate_contact",
            description=(
                "Оценить контакт/поставщика (1-5 звёзд). "
                "Можно оценить в целом или по категориям: "
                "reliability, quality, pricing, communication, delivery_speed."
            ),
            parameters=[
                ToolParameter("name", "string",
                              "Имя контакта/поставщика", True),
                ToolParameter("rating", "number",
                              "Рейтинг (1-5 звёзд)", True),
                ToolParameter("comment", "string",
                              "Комментарий к оценке", False, ""),
                ToolParameter("category", "string",
                              "Категория: reliability/quality/pricing/communication/delivery_speed",
                              False, ""),
            ],
            handler=tool_rate_contact,
            category="crm",
        ),
        Tool(
            name="crm_search",
            description=(
                "Поиск в CRM: контакты, сделки, pipeline. "
                "Фильтрация по типу, рейтингу, тегам."
            ),
            parameters=[
                ToolParameter("query", "string",
                              "Поисковый запрос (имя, компания)", False, ""),
                ToolParameter("action", "string",
                              "Действие: search/pipeline/stats/add_contact/add_deal",
                              False, "search"),
                ToolParameter("contact_type", "string",
                              "Тип: supplier/client/partner/logistics/other", False, ""),
                ToolParameter("min_rating", "number",
                              "Минимальный рейтинг (0-5)", False, 0),
            ],
            handler=tool_crm_search,
            category="crm",
        ),

        # ─── Part 9: Evening Digest ─────────────────────────────────
        Tool(
            name="evening_digest",
            description=(
                "Вечерний дайджест: итоги дня, сравнение с вчера, "
                "рекомендации на завтра. Автоматическая аналитика."
            ),
            parameters=[
                ToolParameter("format", "string",
                              "Формат: full/short", False, "full"),
                ToolParameter("revenue", "number",
                              "Доход за сегодня (если не из БД)", False, 0),
                ToolParameter("expenses", "number",
                              "Расходы за сегодня", False, 0),
                ToolParameter("orders_created", "number",
                              "Заказов создано", False, 0),
                ToolParameter("tasks_completed", "number",
                              "Задач завершено", False, 0),
            ],
            handler=tool_evening_digest,
            category="reports",
        ),

        # ─── Part 9: Workflow & Templates ────────────────────────────
        Tool(
            name="create_template",
            description=(
                "Создать шаблон заказа, чек-лист или workflow. "
                "Шаблоны можно переиспользовать для быстрого создания."
            ),
            parameters=[
                ToolParameter("name", "string", "Название шаблона", True),
                ToolParameter("template_type", "string",
                              "Тип: order/checklist/workflow/message", False, "checklist"),
                ToolParameter("content", "string",
                              "Содержимое/шаги (каждый шаг на новой строке)", True),
                ToolParameter("description", "string",
                              "Описание шаблона", False, ""),
            ],
            handler=tool_create_template,
            category="workflow",
        ),

        # ─── Part 10: Semantic Search V2 ────────────────────────────
        Tool(
            name="knowledge_add",
            description=(
                "Добавить знание в базу знаний. Знания индексируются "
                "для семантического поиска и могут быть найдены по смыслу."
            ),
            parameters=[
                ToolParameter("content", "string", "Содержимое знания", True),
                ToolParameter("category", "string",
                              "Категория: answer/document/conversation/fact/skill/business/general",
                              False, "general"),
                ToolParameter("source", "string", "Источник", False, ""),
                ToolParameter("tags", "string",
                              "Теги через запятую", False, ""),
            ],
            handler=tool_knowledge_add,
            category="knowledge",
        ),
        Tool(
            name="knowledge_search",
            description=(
                "Семантический поиск по базе знаний. "
                "Находит релевантные знания по смыслу, а не по точному совпадению."
            ),
            parameters=[
                ToolParameter("query", "string", "Поисковый запрос", True),
                ToolParameter("category", "string",
                              "Фильтр по категории", False, ""),
                ToolParameter("max_results", "number",
                              "Максимум результатов", False, 5),
            ],
            handler=tool_knowledge_search,
            category="knowledge",
        ),

        # ─── Part 10: Confidence Tracker ────────────────────────────
        Tool(
            name="confidence_check",
            description=(
                "Оценить уверенность в ответе. Показывает: уровень "
                "уверенности, факторы неопределённости, нужен ли "
                "дополнительный поиск."
            ),
            parameters=[
                ToolParameter("text", "string", "Текст для оценки", True),
                ToolParameter("source_count", "number",
                              "Количество источников", False, 1),
                ToolParameter("source_agreement", "number",
                              "Согласованность источников (0-1)", False, 0.5),
            ],
            handler=tool_confidence_check,
            category="confidence",
        ),

        # ─── Part 10: Adaptive Query Expansion ──────────────────────
        Tool(
            name="expand_query",
            description=(
                "Расширить/улучшить поисковый запрос. "
                "Добавляет синонимы, контекстные термины, временные маркеры. "
                "Помогает найти больше релевантных результатов."
            ),
            parameters=[
                ToolParameter("query", "string", "Исходный запрос", True),
                ToolParameter("context", "string",
                              "Контекст для расширения", False, ""),
                ToolParameter("strategy", "string",
                              "Стратегия: synonym/related/specific/broad/temporal/contextual",
                              False, "synonym"),
            ],
            handler=tool_expand_query,
            category="search",
        ),
        Tool(
            name="find_gaps",
            description=(
                "Найти пробелы в ответе: чего не хватает? "
                "Анализирует полноту, наличие данных, подтверждений."
            ),
            parameters=[
                ToolParameter("query", "string", "Исходный вопрос", True),
                ToolParameter("answer", "string", "Текущий ответ", True),
                ToolParameter("confidence", "number",
                              "Текущая уверенность (0-1)", False, 0.5),
            ],
            handler=tool_find_gaps,
            category="search",
        ),

        # ─── Part 10: Task Prioritizer ──────────────────────────────
        Tool(
            name="task_add",
            description=(
                "Добавить задачу в умную очередь с приоритетом. "
                "Задачи сортируются по приоритету, дедлайну, "
                "и возрасту (anti-starvation)."
            ),
            parameters=[
                ToolParameter("name", "string", "Название задачи", True),
                ToolParameter("priority", "string",
                              "Приоритет: critical/high/medium/low/background",
                              False, "medium"),
                ToolParameter("task_type", "string",
                              "Тип задачи: general/api/research/report",
                              False, "general"),
                ToolParameter("deadline_sec", "number",
                              "Дедлайн в секундах (0 = нет)", False, 0),
            ],
            handler=tool_task_add,
            category="tasks",
        ),
        Tool(
            name="task_queue",
            description=(
                "Показать очередь задач, план выполнения, "
                "оценку времени."
            ),
            parameters=[
                ToolParameter("action", "string",
                              "Действие: list/plan/next/stats",
                              False, "list"),
            ],
            handler=tool_task_queue,
            category="tasks",
        ),

        # ─── Part 10: Context Compressor ────────────────────────────
        Tool(
            name="summarize_text",
            description=(
                "Суммаризировать текст (экстрактивная суммаризация). "
                "Выбирает ключевые предложения. Для длинных текстов "
                "используется рекурсивная суммаризация."
            ),
            parameters=[
                ToolParameter("text", "string",
                              "Текст для суммаризации", True),
                ToolParameter("ratio", "number",
                              "Степень сжатия (0.1-0.9, меньше = короче)",
                              False, 0.3),
                ToolParameter("recursive", "boolean",
                              "Рекурсивная суммаризация (для очень длинных)",
                              False, False),
            ],
            handler=tool_summarize_text,
            category="text",
        ),

        # ─── Part 10: Time & Relevance ──────────────────────────────
        Tool(
            name="check_freshness",
            description=(
                "Проверить актуальность данных. Извлекает даты, "
                "оценивает свежесть, даёт рекомендацию об обновлении. "
                "«Этот ответ основан на данных за 2023 год — проверить?»"
            ),
            parameters=[
                ToolParameter("text", "string", "Текст для проверки", True),
            ],
            handler=tool_check_freshness,
            category="analysis",
        ),
        Tool(
            name="time_decay",
            description=(
                "Применить временное затухание к оценке. "
                "Учитывает возраст данных для корректировки скора."
            ),
            parameters=[
                ToolParameter("score", "number", "Базовый скор (0-1)", True),
                ToolParameter("age_days", "number",
                              "Возраст данных в днях", True),
                ToolParameter("method", "string",
                              "Метод: exponential/linear/hyperbolic",
                              False, "exponential"),
            ],
            handler=tool_time_decay,
            category="analysis",
        ),

        # ─── Part 11: Integration Layer ─────────────────────────────
        Tool(
            name="run_chain",
            description=(
                "Запустить цепочку инструментов. Цепочки объединяют "
                "несколько tools в pipeline с передачей данных между шагами."
            ),
            parameters=[
                ToolParameter("chain_name", "string",
                              "Имя цепочки (research_summarize, confidence_check_search, "
                              "freshness_update, finance_report)", True),
                ToolParameter("query", "string",
                              "Входной запрос / данные", False, ""),
            ],
            handler=tool_run_chain,
            category="integration",
        ),
        Tool(
            name="tool_health",
            description=(
                "Показать здоровье инструментов: какие работают, "
                "какие деградируют, какие отключены circuit breaker."
            ),
            parameters=[
                ToolParameter("action", "string",
                              "Действие: report/unhealthy/slow/stats",
                              False, "report"),
            ],
            handler=tool_health_check,
            category="integration",
        ),
        Tool(
            name="parallel_tools",
            description=(
                "Выполнить несколько инструментов параллельно. "
                "Принимает список вызовов и возвращает все результаты."
            ),
            parameters=[
                ToolParameter("calls", "string",
                              "Вызовы в формате: tool1:param1=val1;tool2:param2=val2",
                              True),
            ],
            handler=tool_parallel_execute,
            category="integration",
        ),
        Tool(
            name="list_chains",
            description=(
                "Показать все доступные цепочки инструментов."
            ),
            parameters=[],
            handler=tool_list_chains,
            category="integration",
        ),
    ]

    for tool in tools:
        tool_registry.register(tool)

    logger.info(f"Зарегистрировано {len(tools)} бизнес-инструментов агента")
    return len(tools)


# ═══════════════════════════════════════════════════════════════════════════════
# PART 8: PLUGIN TOOLS (handlers)
# ═══════════════════════════════════════════════════════════════════════════════


async def tool_plugin_connect(
    name: str,
    base_url: str,
    api_key: str = "",
    plugin_type: str = "REST_API",
    **kwargs,
) -> ToolResult:
    """Подключить внешний API как плагин."""
    from pds_ultimate.core.plugin_system import PluginType, plugin_manager

    try:
        # Маппинг строки в enum
        type_map = {t.value: t for t in PluginType}
        p_type = type_map.get(plugin_type.upper(), PluginType.REST_API)

        plugin = await plugin_manager.register_plugin(
            name=name,
            base_url=base_url,
            api_key=api_key if api_key else None,
            plugin_type=p_type,
            user_id=kwargs.get("_user_id", "system"),
        )

        return ToolResult(
            "plugin_connect", True,
            f"✅ Плагин «{plugin.name}» подключён\n"
            f"  🔗 URL: {plugin.base_url}\n"
            f"  📋 Тип: {plugin.plugin_type.value}\n"
            f"  🆔 ID: {plugin.id}",
            data={"plugin_id": plugin.id, "name": plugin.name},
        )
    except Exception as e:
        return ToolResult(
            "plugin_connect", False, "",
            error=f"Ошибка подключения плагина: {e}",
        )


async def tool_plugin_execute(
    plugin_name: str,
    endpoint: str,
    method: str = "GET",
    body: str = "",
    **kwargs,
) -> ToolResult:
    """Выполнить запрос через плагин."""
    import json as _json

    from pds_ultimate.core.plugin_system import plugin_manager

    try:
        plugin = plugin_manager.get_by_name(plugin_name)
        if not plugin:
            return ToolResult(
                "plugin_execute", False, "",
                error=f"Плагин «{plugin_name}» не найден",
            )

        # Парсим тело запроса
        json_body = None
        if body:
            try:
                json_body = _json.loads(body)
            except _json.JSONDecodeError:
                json_body = {"data": body}

        result = await plugin_manager.execute(
            plugin_id=plugin.id,
            endpoint=endpoint,
            method=method.upper(),
            json_data=json_body,
        )

        # Форматируем ответ
        if isinstance(result, dict):
            output = _json.dumps(result, ensure_ascii=False, indent=2)[:3000]
        else:
            output = str(result)[:3000]

        return ToolResult(
            "plugin_execute", True,
            f"📡 {plugin_name} → {method.upper()} {endpoint}\n\n{output}",
            data=result if isinstance(result, dict) else {"response": output},
        )
    except Exception as e:
        return ToolResult(
            "plugin_execute", False, "",
            error=f"Ошибка вызова плагина: {e}",
        )


async def tool_plugin_list(**kwargs) -> ToolResult:
    """Список подключённых плагинов."""
    from pds_ultimate.core.plugin_system import plugin_manager

    stats = plugin_manager.get_stats()
    plugins = plugin_manager.get_active_plugins()

    if not plugins:
        return ToolResult(
            "plugin_list", True,
            "📋 Нет подключённых плагинов.\n"
            "Используй plugin_connect для подключения API.",
        )

    lines = [f"📋 Плагины ({stats['total']}):"]
    for p in plugins:
        lines.append(
            f"  • {p.name} [{p.plugin_type.value}] — {p.status.value}\n"
            f"    🔗 {p.base_url}"
        )

    return ToolResult(
        "plugin_list", True, "\n".join(lines),
        data=stats,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PART 8: AUTONOMY TOOLS (handlers)
# ═══════════════════════════════════════════════════════════════════════════════


async def tool_autonomous_task(
    goal: str,
    priority: str = "normal",
    deadline_hours: float = 0,
    **kwargs,
) -> ToolResult:
    """Создать автономную задачу."""
    from pds_ultimate.core.autonomy_engine import TaskPriority, autonomy_engine

    try:
        # Маппинг строки в приоритет
        priority_map = {
            "critical": TaskPriority.CRITICAL,
            "high": TaskPriority.HIGH,
            "normal": TaskPriority.NORMAL,
            "low": TaskPriority.LOW,
            "background": TaskPriority.BACKGROUND,
        }
        p = priority_map.get(priority.lower(), TaskPriority.NORMAL)

        # Дедлайн
        from datetime import datetime, timedelta
        deadline = None
        if deadline_hours and float(deadline_hours) > 0:
            deadline = datetime.utcnow() + timedelta(hours=float(deadline_hours))

        task = autonomy_engine.create_task(
            goal=goal,
            user_id=kwargs.get("_user_id", "system"),
            priority=p,
            deadline=deadline,
        )

        lines = [
            "🤖 Автономная задача создана:",
            f"  🆔 ID: {task.id}",
            f"  🎯 Цель: {task.goal}",
            f"  ⚡ Приоритет: {priority}",
        ]
        if deadline:
            lines.append(f"  ⏰ Дедлайн: {deadline.strftime('%Y-%m-%d %H:%M')}")

        return ToolResult(
            "autonomous_task", True, "\n".join(lines),
            data={"task_id": task.id, "status": task.status.value},
        )
    except Exception as e:
        return ToolResult(
            "autonomous_task", False, "",
            error=f"Ошибка создания задачи: {e}",
        )


async def tool_task_status(task_id: str = "", **kwargs) -> ToolResult:
    """Статус автономных задач."""
    from pds_ultimate.core.autonomy_engine import autonomy_engine

    try:
        if task_id:
            task = autonomy_engine.get_task(task_id)
            if not task:
                return ToolResult(
                    "task_status", False, "",
                    error=f"Задача {task_id} не найдена",
                )
            lines = [
                f"📋 Задача {task.id}:",
                f"  🎯 {task.goal}",
                f"  📊 Статус: {task.status.value}",
                f"  📈 Прогресс: {task.progress:.0%}",
                f"  🔧 Шагов: {len(task.steps)}",
            ]
            if task.corrections:
                lines.append(f"  🔄 Коррекций: {len(task.corrections)}")
            return ToolResult(
                "task_status", True, "\n".join(lines),
                data={"task_id": task.id, "status": task.status.value,
                      "progress": task.progress},
            )

        # Все активные
        stats = autonomy_engine.get_stats()
        queue = autonomy_engine.format_queue()
        return ToolResult(
            "task_status", True,
            f"📋 Автономные задачи:\n{queue}\n\n"
            f"📊 Всего: {stats['total']}, Активных: {stats['active']}",
            data=stats,
        )
    except Exception as e:
        return ToolResult(
            "task_status", False, "",
            error=f"Ошибка получения статуса: {e}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PART 8: MEMORY V2 TOOLS (handlers)
# ═══════════════════════════════════════════════════════════════════════════════


async def tool_learn_skill(
    name: str,
    pattern: str,
    strategy: str,
    **kwargs,
) -> ToolResult:
    """Научить агента новому навыку."""
    from pds_ultimate.core.memory_v2 import memory_v2

    try:
        skill = memory_v2.learn_skill(
            name=name,
            pattern=pattern,
            strategy=strategy,
        )
        return ToolResult(
            "learn_skill", True,
            f"🎓 Навык «{skill.name}» сохранён!\n"
            f"  📋 Паттерн: {pattern}\n"
            f"  💡 Стратегия: {strategy}",
            data=skill.to_dict(),
        )
    except Exception as e:
        return ToolResult(
            "learn_skill", False, "",
            error=f"Ошибка сохранения навыка: {e}",
        )


async def tool_memory_stats(**kwargs) -> ToolResult:
    """Статистика памяти v2."""
    from pds_ultimate.core.memory_v2 import memory_v2

    try:
        stats = memory_v2.get_stats()

        lines = [
            "🧠 Статистика памяти v2:",
            f"  🎓 Навыков: {stats['skills']}",
            f"  ⚠️ Ошибок записано: {stats['failures']}",
            f"  📊 Паттернов: {stats['patterns']}",
        ]

        if stats.get("top_skills"):
            lines.append("\n🏆 Топ навыки:")
            for s in stats["top_skills"]:
                lines.append(f"  • {s['name']} ({s['success_rate']})")

        fail_stats = stats.get("failure_stats", {})
        if fail_stats.get("by_type"):
            lines.append("\n📊 Ошибки по типу:")
            for t, c in fail_stats["by_type"].items():
                lines.append(f"  • {t}: {c}")

        return ToolResult(
            "memory_stats", True, "\n".join(lines),
            data=stats,
        )
    except Exception as e:
        return ToolResult(
            "memory_stats", False, "",
            error=f"Ошибка получения статистики: {e}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PART 9: SMART TRIGGERS (handlers)
# ═══════════════════════════════════════════════════════════════════════════════


async def tool_set_trigger(
    name: str,
    trigger_type: str = "threshold",
    field: str = "",
    operator: str = ">",
    value: str = "",
    severity: str = "warning",
    template: str = "",
    **kwargs,
) -> ToolResult:
    """Установить умный триггер."""
    from pds_ultimate.core.smart_triggers import (
        ComparisonOp,
        TriggerCondition,
        trigger_manager,
    )

    try:
        # Если указан шаблон — используем его
        if template:
            template_kwargs = {}
            if value:
                # Парсим значение для шаблона
                try:
                    template_kwargs["threshold"] = float(value)
                except ValueError:
                    template_kwargs["supplier_name"] = value

            trigger = trigger_manager.create_from_template(
                template, **template_kwargs,
            )
            trigger.name = name or trigger.name
        else:
            # Создаём пользовательский триггер
            condition = None
            if field and value:
                try:
                    op = ComparisonOp(operator)
                except ValueError:
                    op = ComparisonOp.GT

                try:
                    val = float(value)
                except ValueError:
                    val = value

                condition = TriggerCondition(
                    field=field,
                    operator=op,
                    value=val,
                )

            trigger = trigger_manager.create_trigger(
                name=name,
                trigger_type=trigger_type,
                condition=condition,
                severity=severity,
            )

        return ToolResult(
            "set_trigger", True,
            f"🔔 Триггер «{trigger.name}» создан!\n"
            f"  🆔 ID: {trigger.id}\n"
            f"  📋 Тип: {trigger.trigger_type.value}\n"
            f"  ⚡ Серьёзность: {trigger.severity.value}\n"
            f"  📌 Условие: {trigger.condition.describe() if trigger.condition else 'custom'}",
            data=trigger.to_dict(),
        )
    except Exception as e:
        return ToolResult(
            "set_trigger", False, "",
            error=f"Ошибка создания триггера: {e}",
        )


async def tool_list_triggers(
    show_history: bool = False,
    **kwargs,
) -> ToolResult:
    """Список триггеров и алертов."""
    from pds_ultimate.core.smart_triggers import trigger_manager

    try:
        triggers_text = trigger_manager.format_triggers_list()
        stats = trigger_manager.get_stats()

        lines = [triggers_text]
        lines.append(
            f"\n📊 Всего: {stats['total']}, "
            f"активных: {stats['active']}, "
            f"срабатываний: {stats['total_fires']}"
        )

        if show_history:
            recent = trigger_manager.history.get_recent(10)
            if recent:
                lines.append("\n📜 Последние алерты:")
                for a in recent:
                    lines.append(f"  • {a.format_message()}")
            else:
                lines.append("\n📜 Алертов пока нет.")

        return ToolResult(
            "list_triggers", True, "\n".join(lines),
            data=stats,
        )
    except Exception as e:
        return ToolResult(
            "list_triggers", False, "",
            error=f"Ошибка получения триггеров: {e}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PART 9: ANALYTICS DASHBOARD (handlers)
# ═══════════════════════════════════════════════════════════════════════════════


async def tool_dashboard(
    action: str = "show",
    metric_name: str = "",
    value: float = 0.0,
    unit: str = "",
    **kwargs,
) -> ToolResult:
    """Бизнес-дашборд."""
    from pds_ultimate.core.analytics_dashboard import analytics_dashboard

    try:
        if action == "record" and metric_name:
            analytics_dashboard.record_metric(
                name=metric_name,
                value=float(value),
                unit=unit,
            )
            return ToolResult(
                "dashboard", True,
                f"📊 Записано: {metric_name} = {value} {unit}",
            )
        elif action == "trend" and metric_name:
            report = analytics_dashboard.generate_trend_report()
            return ToolResult(
                "dashboard", True, report,
                data=analytics_dashboard.get_stats(),
            )
        elif action == "forecast" and metric_name:
            forecast = analytics_dashboard.forecast(metric_name)
            return ToolResult(
                "dashboard", True,
                f"📈 Прогноз {metric_name}: {forecast}",
                data={"forecast": forecast},
            )
        else:
            dashboard = analytics_dashboard.generate_dashboard()
            return ToolResult(
                "dashboard", True, dashboard,
                data=analytics_dashboard.get_stats(),
            )
    except Exception as e:
        return ToolResult(
            "dashboard", False, "",
            error=f"Ошибка дашборда: {e}",
        )


async def tool_kpi_track(
    action: str = "board",
    name: str = "",
    target: float = 0.0,
    value: float = 0.0,
    unit: str = "",
    **kwargs,
) -> ToolResult:
    """Отслеживание KPI."""
    from pds_ultimate.core.analytics_dashboard import analytics_dashboard

    try:
        if action == "create" and name:
            kpi = analytics_dashboard.create_kpi(
                name=name,
                target=float(target),
                unit=unit,
            )
            return ToolResult(
                "kpi_track", True,
                f"🎯 KPI «{kpi.name}» создан!\n"
                f"  📊 Цель: {kpi.target_value} {kpi.unit}\n"
                f"  📈 Прогресс: {kpi.progress_percent}%",
                data=kpi.to_dict(),
            )
        elif action == "update" and name:
            kpi = analytics_dashboard.update_kpi(name, float(value))
            if not kpi:
                return ToolResult(
                    "kpi_track", False, "",
                    error=f"KPI «{name}» не найден",
                )
            return ToolResult(
                "kpi_track", True,
                f"📊 KPI «{kpi.name}» обновлён!\n"
                f"  📈 {kpi.current_value:.0f}/{kpi.target_value:.0f} "
                f"{kpi.unit} [{kpi.progress_percent}%]\n"
                f"  📋 Статус: {kpi.status.value}",
                data=kpi.to_dict(),
            )
        else:
            board = analytics_dashboard.kpi_tracker.format_kpi_board()
            stats = analytics_dashboard.kpi_tracker.get_stats()
            return ToolResult(
                "kpi_track", True, board,
                data=stats,
            )
    except Exception as e:
        return ToolResult(
            "kpi_track", False, "",
            error=f"Ошибка KPI: {e}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PART 9: CRM (handlers)
# ═══════════════════════════════════════════════════════════════════════════════


async def tool_rate_contact(
    name: str,
    rating: float,
    comment: str = "",
    category: str = "",
    **kwargs,
) -> ToolResult:
    """Оценить контакт/поставщика."""
    from pds_ultimate.core.crm_engine import crm_engine

    try:
        rating = max(1.0, min(5.0, float(rating)))

        if category:
            # Оценка поставщика по категории
            scorecard = crm_engine.rate_supplier(name, category, rating)
            if not scorecard:
                # Автосоздание контакта
                contact = crm_engine.add_contact(
                    name=name, contact_type="supplier",
                    rating=rating,
                )
                scorecard = crm_engine.rate_supplier(name, category, rating)

            return ToolResult(
                "rate_contact", True,
                f"📊 Оценка «{name}» [{category}]: {rating}/5\n"
                f"  🏆 Общий балл: {scorecard.overall_score}/5.0"
                if scorecard else f"⚠️ Не удалось оценить {name}",
                data=scorecard.to_dict() if scorecard else {},
            )
        else:
            # Общая оценка контакта
            contact = crm_engine.rate_contact(name, rating, comment)
            if not contact:
                # Автосоздание
                contact = crm_engine.add_contact(
                    name=name, rating=rating,
                )

            return ToolResult(
                "rate_contact", True,
                f"⭐ «{name}» оценён: {contact.star_rating} ({contact.rating}/5)"
                + (f"\n  💬 {comment}" if comment else ""),
                data=contact.to_dict(),
            )
    except Exception as e:
        return ToolResult(
            "rate_contact", False, "",
            error=f"Ошибка оценки: {e}",
        )


async def tool_crm_search(
    query: str = "",
    action: str = "search",
    contact_type: str = "",
    min_rating: float = 0.0,
    **kwargs,
) -> ToolResult:
    """Поиск в CRM."""
    from pds_ultimate.core.crm_engine import crm_engine

    try:
        if action == "pipeline":
            text = crm_engine.pipeline.format_pipeline()
            stats = crm_engine.pipeline.get_stats()
            return ToolResult(
                "crm_search", True, text,
                data=stats,
            )
        elif action == "stats":
            stats = crm_engine.get_stats()
            lines = [
                "📊 CRM Статистика:",
                f"  👤 Контактов: {stats['contacts']['total']}",
                f"  📊 Средний рейтинг: {stats['contacts']['avg_rating']}",
                f"  💼 Сделок: {stats['pipeline']['total']}",
                f"  💬 Взаимодействий: {stats['interactions']}",
                f"  📞 Ожидают follow-up: {stats['pending_followups']}",
            ]
            return ToolResult(
                "crm_search", True, "\n".join(lines),
                data=stats,
            )
        elif action == "add_contact" and query:
            contact = crm_engine.add_contact(
                name=query, contact_type=contact_type or "other",
            )
            return ToolResult(
                "crm_search", True,
                f"✅ Контакт «{contact.name}» добавлен (ID: {contact.id})",
                data=contact.to_dict(),
            )
        elif action == "add_deal" and query:
            deal = crm_engine.create_deal(title=query)
            return ToolResult(
                "crm_search", True,
                f"✅ Сделка «{deal.title}» создана (ID: {deal.id})",
                data=deal.to_dict(),
            )
        else:
            # Search
            contacts = crm_engine.search_contacts(
                query=query,
                contact_type=contact_type,
                min_rating=float(min_rating),
            )
            if not contacts:
                return ToolResult(
                    "crm_search", True,
                    f"🔍 По запросу «{query}» контактов не найдено.",
                )

            lines = [f"🔍 Найдено контактов: {len(contacts)}"]
            for c in contacts[:10]:
                lines.append(f"\n{c.format_card()}")
            return ToolResult(
                "crm_search", True, "\n".join(lines),
                data={"count": len(contacts),
                      "contacts": [c.to_dict() for c in contacts[:10]]},
            )
    except Exception as e:
        return ToolResult(
            "crm_search", False, "",
            error=f"Ошибка CRM: {e}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PART 9: EVENING DIGEST (handlers)
# ═══════════════════════════════════════════════════════════════════════════════


async def tool_evening_digest(
    format: str = "full",
    revenue: float = 0.0,
    expenses: float = 0.0,
    orders_created: int = 0,
    tasks_completed: int = 0,
    **kwargs,
) -> ToolResult:
    """Вечерний дайджест."""
    from pds_ultimate.core.evening_digest import DaySummary, evening_digest

    try:
        summary = DaySummary(
            revenue=float(revenue),
            expenses=float(expenses),
            profit=float(revenue) - float(expenses),
            orders_created=int(orders_created),
            tasks_completed=int(tasks_completed),
        )
        evening_digest.record_day_summary(summary)

        if format == "short":
            text = evening_digest.generate_short_digest(summary)
        else:
            text = evening_digest.generate_digest(summary)

        return ToolResult(
            "evening_digest", True, text,
            data=summary.to_dict(),
        )
    except Exception as e:
        return ToolResult(
            "evening_digest", False, "",
            error=f"Ошибка дайджеста: {e}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PART 9: WORKFLOW & TEMPLATES (handlers)
# ═══════════════════════════════════════════════════════════════════════════════


async def tool_create_template(
    name: str,
    template_type: str = "checklist",
    content: str = "",
    description: str = "",
    **kwargs,
) -> ToolResult:
    """Создать шаблон или чек-лист."""
    from pds_ultimate.core.workflow_engine import workflow_engine

    try:
        if template_type == "checklist" and content:
            # Создаём чек-лист из содержимого
            steps = [
                s.strip().lstrip("0123456789.-) ")
                for s in content.split("\n")
                if s.strip()
            ]
            checklist = workflow_engine.create_checklist(
                name=name,
                steps=steps,
                description=description,
            )
            return ToolResult(
                "create_template", True,
                f"📋 Чек-лист «{checklist.name}» создан!\n"
                f"{checklist.format_text()}",
                data=checklist.to_dict(),
            )
        else:
            # Создаём шаблон
            template = workflow_engine.create_template(
                name=name,
                template_type=template_type,
                content=content,
                description=description,
            )
            return ToolResult(
                "create_template", True,
                f"📝 Шаблон «{template.name}» создан!\n"
                f"  📋 Тип: {template.template_type.value}\n"
                f"  🆔 ID: {template.id}",
                data=template.to_dict(),
            )
    except Exception as e:
        return ToolResult(
            "create_template", False, "",
            error=f"Ошибка создания шаблона: {e}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# BROWSER TOOLS (handlers)
# ═══════════════════════════════════════════════════════════════════════════════

async def tool_web_search(query: str, max_results: int = 10, **kwargs) -> ToolResult:
    """Поиск в интернете через Browser Engine."""
    from pds_ultimate.core.browser_engine import browser_engine

    try:
        results = await browser_engine.web_search(
            query, max_results=min(int(max_results), 20)
        )
        if not results:
            return ToolResult("web_search", True,
                              f"По запросу «{query}» ничего не найдено.",
                              data={"results": []})

        lines = [f"🔍 Результаты поиска: «{query}» ({len(results)} шт.)\n"]
        for r in results:
            lines.append(f"  {r.position}. {r.title}")
            lines.append(f"     🔗 {r.url}")
            if r.snippet:
                lines.append(f"     {r.snippet[:150]}")
            lines.append("")

        return ToolResult(
            "web_search", True, "\n".join(lines),
            data={"results": [
                {"title": r.title, "url": r.url, "snippet": r.snippet}
                for r in results
            ]},
        )

    except Exception as e:
        return ToolResult("web_search", False, "",
                          error=f"Ошибка поиска: {e}")


async def tool_open_page(url: str, **kwargs) -> ToolResult:
    """Открыть страницу и извлечь данные."""
    from pds_ultimate.core.browser_engine import browser_engine

    try:
        data = await browser_engine.extract_data(url)

        if not data.text and not data.title:
            return ToolResult("open_page", False, "",
                              error=f"Не удалось загрузить: {url}")

        # Обрезаем текст до разумного размера для LLM
        text = data.text[:4000] if data.text else ""
        if len(data.text) > 4000:
            text += f"\n\n... (ещё {len(data.text) - 4000} символов)"

        lines = [f"📄 {data.title}", f"🔗 {data.url}", ""]
        if text:
            lines.append(text)

        if data.tables:
            lines.append(f"\n📊 Найдено таблиц: {len(data.tables)}")
            # Показываем первую таблицу
            for row in data.tables[0][:10]:
                lines.append("  | " + " | ".join(row[:5]) + " |")

        return ToolResult(
            "open_page", True, "\n".join(lines),
            data=data.to_dict(),
        )

    except Exception as e:
        return ToolResult("open_page", False, "",
                          error=f"Ошибка загрузки страницы: {e}")


async def tool_browser_screenshot(full_page: bool = False, **kwargs) -> ToolResult:
    """Скриншот текущей страницы."""
    from pds_ultimate.core.browser_engine import browser_engine

    try:
        path = await browser_engine.screenshot(full_page=bool(full_page))
        return ToolResult(
            "browser_screenshot", True,
            f"📸 Скриншот сохранён: {path}",
            data={"path": str(path)},
        )
    except RuntimeError as e:
        return ToolResult("browser_screenshot", False, "", error=str(e))
    except Exception as e:
        return ToolResult("browser_screenshot", False, "",
                          error=f"Ошибка скриншота: {e}")


async def tool_browser_click(selector: str, **kwargs) -> ToolResult:
    """Кликнуть по элементу."""
    from pds_ultimate.core.browser_engine import browser_engine

    try:
        await browser_engine.click(selector, human_like=True)
        # Ждём загрузку после клика
        await asyncio.sleep(1.0)
        info = await browser_engine.get_page_info()
        return ToolResult(
            "browser_click", True,
            f"✅ Кликнул по '{selector}'. Текущая страница: {info.title}",
            data={"url": info.url, "title": info.title},
        )
    except RuntimeError as e:
        return ToolResult("browser_click", False, "", error=str(e))
    except Exception as e:
        return ToolResult("browser_click", False, "",
                          error=f"Ошибка клика: {e}")


async def tool_browser_fill(selector: str, value: str, **kwargs) -> ToolResult:
    """Заполнить поле."""
    from pds_ultimate.core.browser_engine import browser_engine

    try:
        await browser_engine.fill(selector, value, human_like=True)
        return ToolResult(
            "browser_fill", True,
            f"✅ Заполнил '{selector}' значением: {value[:100]}",
        )
    except RuntimeError as e:
        return ToolResult("browser_fill", False, "", error=str(e))
    except Exception as e:
        return ToolResult("browser_fill", False, "",
                          error=f"Ошибка заполнения: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# RESEARCH TOOLS (handlers) — Internet Reasoning
# ═══════════════════════════════════════════════════════════════════════════════


async def tool_research(
    query: str,
    max_sources: int = 5,
    **kwargs,
) -> ToolResult:
    """
    Исследовать вопрос с проверкой множества источников.
    Использует Internet Reasoning Engine: поиск, анализ,
    извлечение фактов, обнаружение противоречий, синтез ответа.
    """
    from pds_ultimate.core.internet_reasoning import reasoning_engine

    try:
        answer = await reasoning_engine.research(
            query=query,
            max_sources=int(max_sources),
            expand_queries=True,
        )

        lines = [answer.summary]
        lines.append(f"\n📊 Уверенность: {answer.confidence:.0%}")
        lines.append(f"📖 Источников: {answer.sources_count}")
        lines.append(f"🏷️ Качество: {answer.quality_label}")

        if answer.has_contradictions:
            lines.append(
                f"⚠️ Противоречий: {len(answer.contradictions)}"
            )

        return ToolResult(
            "research", True, "\n".join(lines),
            data=answer.to_dict(),
        )
    except Exception as e:
        return ToolResult(
            "research", False, "",
            error=f"Ошибка исследования: {e}",
        )


async def tool_deep_research(
    query: str,
    max_sources: int = 10,
    **kwargs,
) -> ToolResult:
    """
    Глубокое исследование с расширенным покрытием источников.
    Для сложных вопросов, где нужна проверка из множества
    независимых источников.
    """
    from pds_ultimate.core.internet_reasoning import reasoning_engine

    try:
        answer = await reasoning_engine.deep_research(
            query=query,
            max_sources=int(max_sources),
        )

        lines = [answer.summary]
        lines.append(f"\n📊 Уверенность: {answer.confidence:.0%}")
        lines.append(f"📖 Источников: {answer.sources_count}")
        lines.append(f"🔬 Фактов проанализировано: {len(answer.facts)}")
        lines.append(f"🏷️ Качество: {answer.quality_label}")

        if answer.has_contradictions:
            lines.append(
                f"⚠️ Противоречий: {len(answer.contradictions)}"
            )

        stats = reasoning_engine.get_stats()
        lines.append(
            f"\n📈 Статистика: {stats['queries']} запросов, "
            f"{stats['pages']} стр, {stats['time_ms']}мс"
        )

        return ToolResult(
            "deep_research", True, "\n".join(lines),
            data=answer.to_dict(),
        )
    except Exception as e:
        return ToolResult(
            "deep_research", False, "",
            error=f"Ошибка глубокого исследования: {e}",
        )


async def tool_quick_search(
    query: str,
    **kwargs,
) -> ToolResult:
    """
    Быстрый поиск без расширения запросов.
    Для простых вопросов, когда нужен быстрый ответ.
    """
    from pds_ultimate.core.internet_reasoning import reasoning_engine

    try:
        answer = await reasoning_engine.quick_search(query=query)

        lines = [answer.summary]
        lines.append(f"\n📊 Уверенность: {answer.confidence:.0%}")
        lines.append(f"📖 Источников: {answer.sources_count}")

        return ToolResult(
            "quick_search", True, "\n".join(lines),
            data=answer.to_dict(),
        )
    except Exception as e:
        return ToolResult(
            "quick_search", False, "",
            error=f"Ошибка быстрого поиска: {e}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PART 10: KNOWLEDGE BASE / SEMANTIC SEARCH V2 (handlers)
# ═══════════════════════════════════════════════════════════════════════════════


async def tool_knowledge_add(
    content: str,
    category: str = "general",
    source: str = "",
    tags: str = "",
    **kwargs,
) -> ToolResult:
    """Добавить знание в базу знаний."""
    from pds_ultimate.core.semantic_search_v2 import semantic_search_v2

    try:
        tag_list = [t.strip()
                    for t in tags.split(",") if t.strip()] if tags else []
        item_id = semantic_search_v2.add_knowledge(
            content=content,
            category=category,
            source=source,
            tags=tag_list,
        )
        return ToolResult(
            "knowledge_add", True,
            f"📚 Знание добавлено в базу!\n"
            f"  🆔 ID: {item_id}\n"
            f"  📁 Категория: {category}\n"
            f"  🏷️ Теги: {', '.join(tag_list) if tag_list else '—'}",
            data={"id": item_id, "category": category},
        )
    except Exception as e:
        return ToolResult(
            "knowledge_add", False, "",
            error=f"Ошибка добавления знания: {e}",
        )


async def tool_knowledge_search(
    query: str,
    category: str = "",
    max_results: int = 5,
    **kwargs,
) -> ToolResult:
    """Семантический поиск по базе знаний."""
    from pds_ultimate.core.semantic_search_v2 import semantic_search_v2

    try:
        results = semantic_search_v2.search_knowledge(
            query=query,
            category=category or None,
            max_results=int(max_results),
        )
        if not results:
            return ToolResult(
                "knowledge_search", True,
                "🔍 Ничего не найдено в базе знаний.",
                data={"results": [], "count": 0},
            )

        lines = [f"🔍 Найдено {len(results)} результатов:"]
        for i, r in enumerate(results, 1):
            lines.append(
                f"\n  {i}. [{r.item.category.value}] "
                f"(скор: {r.final_score:.2f})\n"
                f"     {r.item.content[:150]}..."
            )
        stats = semantic_search_v2.get_stats()
        lines.append(
            f"\n📊 Всего в базе: {stats['knowledge_base']['total']} знаний")

        return ToolResult(
            "knowledge_search", True, "\n".join(lines),
            data={"results": [r.to_dict() for r in results],
                  "count": len(results)},
        )
    except Exception as e:
        return ToolResult(
            "knowledge_search", False, "",
            error=f"Ошибка поиска: {e}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PART 10: CONFIDENCE TRACKER (handlers)
# ═══════════════════════════════════════════════════════════════════════════════


async def tool_confidence_check(
    text: str,
    source_count: int = 1,
    source_agreement: float = 0.5,
    **kwargs,
) -> ToolResult:
    """Оценить уверенность в ответе."""
    from pds_ultimate.core.confidence_tracker import confidence_tracker

    try:
        score = confidence_tracker.estimate(
            text=text,
            source_count=int(source_count),
            source_agreement=float(source_agreement),
        )
        needs = confidence_tracker.needs_search(score)

        lines = [
            f"{score.emoji} Уверенность: {score.value:.0%} ({score.level.value})",
        ]
        if score.factors:
            lines.append("📊 Факторы:")
            for k, v in score.factors.items():
                lines.append(f"  • {k}: {v:.2f}")
        if score.uncertainties:
            lines.append("⚠️ Неопределённости:")
            for u in score.uncertainties:
                lines.append(f"  • {u.value}")
        if needs:
            lines.append("🔍 Рекомендуется дополнительный поиск!")
            plan = confidence_tracker.get_search_plan(score)
            if plan:
                lines.append(f"  План: {plan.get('action', '?')}")

        return ToolResult(
            "confidence_check", True, "\n".join(lines),
            data=score.to_dict(),
        )
    except Exception as e:
        return ToolResult(
            "confidence_check", False, "",
            error=f"Ошибка оценки уверенности: {e}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PART 10: ADAPTIVE QUERY EXPANSION (handlers)
# ═══════════════════════════════════════════════════════════════════════════════


async def tool_expand_query(
    query: str,
    context: str = "",
    strategy: str = "synonym",
    **kwargs,
) -> ToolResult:
    """Расширить поисковый запрос."""
    from pds_ultimate.core.adaptive_query import adaptive_query

    try:
        expanded = adaptive_query.expand(
            query=query,
            context=context,
            strategy=strategy,
        )
        lines = [
            "🔄 Расширение запроса:",
            f"  📝 Оригинал: {expanded.original}",
            f"  ✨ Расширенный: {expanded.expanded}",
            f"  📋 Стратегия: {expanded.strategy.value}",
            f"  📊 Уверенность: {expanded.confidence:.0%}",
        ]
        if expanded.added_terms:
            lines.append(f"  ➕ Добавлено: {', '.join(expanded.added_terms)}")
        if expanded.removed_terms:
            lines.append(f"  ➖ Убрано: {', '.join(expanded.removed_terms)}")

        return ToolResult(
            "expand_query", True, "\n".join(lines),
            data=expanded.to_dict(),
        )
    except Exception as e:
        return ToolResult(
            "expand_query", False, "",
            error=f"Ошибка расширения запроса: {e}",
        )


async def tool_find_gaps(
    query: str,
    answer: str,
    confidence: float = 0.5,
    **kwargs,
) -> ToolResult:
    """Найти пробелы в ответе."""
    from pds_ultimate.core.adaptive_query import adaptive_query

    try:
        gaps = adaptive_query.find_gaps(
            query=query,
            answer=answer,
            confidence=float(confidence),
        )
        if not gaps:
            return ToolResult(
                "find_gaps", True,
                "✅ Пробелов не найдено — ответ полный!",
                data={"gaps": [], "count": 0},
            )

        lines = [f"🔍 Найдено {len(gaps)} пробелов:"]
        for i, gap in enumerate(gaps, 1):
            lines.append(
                f"\n  {i}. [{gap.gap_type.value}] {gap.description}\n"
                f"     Приоритет: {gap.priority:.0%}"
            )
            if gap.suggested_query:
                lines.append(f"     💡 Запрос: {gap.suggested_query}")

        return ToolResult(
            "find_gaps", True, "\n".join(lines),
            data={"gaps": [g.to_dict() for g in gaps], "count": len(gaps)},
        )
    except Exception as e:
        return ToolResult(
            "find_gaps", False, "",
            error=f"Ошибка анализа пробелов: {e}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PART 10: TASK PRIORITIZER (handlers)
# ═══════════════════════════════════════════════════════════════════════════════


async def tool_task_add(
    name: str,
    priority: str = "medium",
    task_type: str = "general",
    deadline_sec: float = 0,
    **kwargs,
) -> ToolResult:
    """Добавить задачу в очередь."""
    from pds_ultimate.core.task_prioritizer import task_prioritizer

    try:
        dl = float(deadline_sec) if float(deadline_sec) > 0 else None
        task = task_prioritizer.add_task(
            name=name,
            priority=priority,
            task_type=task_type,
            deadline_sec=dl,
        )
        lines = [
            "📋 Задача добавлена в очередь!",
            f"  🆔 ID: {task.id}",
            f"  📌 Приоритет: {task.priority.name}",
            f"  📁 Тип: {task.task_type}",
        ]
        if task.deadline:
            ttd = task.time_to_deadline
            if ttd is not None:
                lines.append(f"  ⏰ Дедлайн через: {ttd:.0f} сек")
        stats = task_prioritizer.get_stats()
        lines.append(
            f"\n📊 В очереди: {stats['queue']['pending']} задач"
        )
        return ToolResult(
            "task_add", True, "\n".join(lines),
            data=task.to_dict(),
        )
    except Exception as e:
        return ToolResult(
            "task_add", False, "",
            error=f"Ошибка добавления задачи: {e}",
        )


async def tool_task_queue(
    action: str = "list",
    **kwargs,
) -> ToolResult:
    """Показать очередь задач."""
    from pds_ultimate.core.task_prioritizer import task_prioritizer

    try:
        if action == "next":
            task = task_prioritizer.next_task()
            if task is None:
                return ToolResult(
                    "task_queue", True,
                    "📋 Очередь пуста — нет задач.",
                    data={"task": None},
                )
            return ToolResult(
                "task_queue", True,
                f"▶️ Следующая задача: {task.name}\n"
                f"  🆔 {task.id} | 📌 {task.priority.name}",
                data=task.to_dict(),
            )

        if action == "plan":
            plan = task_prioritizer.get_plan()
            if not plan:
                return ToolResult(
                    "task_queue", True,
                    "📋 Нет задач для планирования.",
                    data={"plan": []},
                )
            lines = ["📋 План выполнения:"]
            for i, wave in enumerate(plan, 1):
                lines.append(f"\n  🌊 Волна {i} ({len(wave)} задач):")
                for t in wave:
                    lines.append(f"    • {t['name']} [{t['priority']}]")
            est = task_prioritizer.estimate_time()
            lines.append(f"\n⏱️ Оценка времени: {est:.1f} сек")
            return ToolResult(
                "task_queue", True, "\n".join(lines),
                data={"plan": plan, "estimated_sec": est},
            )

        if action == "stats":
            stats = task_prioritizer.get_stats()
            q = stats["queue"]
            lines = [
                "📊 Статистика очереди:",
                f"  📋 Всего: {q['total']}",
                f"  ⏳ Ожидают: {q['pending']}",
                f"  ▶️ Выполняются: {q['running']}",
                f"  ✅ Завершены: {q['completed']}",
                f"  ❌ Ошибки: {q['failed']}",
                f"  ⚠️ Просрочены: {q['overdue']}",
            ]
            return ToolResult(
                "task_queue", True, "\n".join(lines),
                data=stats,
            )

        # Default: list
        stats = task_prioritizer.get_stats()
        q = stats["queue"]
        return ToolResult(
            "task_queue", True,
            f"📋 Очередь задач: {q['pending']} ожидают, "
            f"{q['running']} выполняются, {q['completed']} завершены",
            data=stats,
        )
    except Exception as e:
        return ToolResult(
            "task_queue", False, "",
            error=f"Ошибка очереди задач: {e}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PART 10: CONTEXT COMPRESSOR (handlers)
# ═══════════════════════════════════════════════════════════════════════════════


async def tool_summarize_text(
    text: str,
    ratio: float = 0.3,
    recursive: bool = False,
    **kwargs,
) -> ToolResult:
    """Суммаризировать текст."""
    from pds_ultimate.core.context_compressor import context_compressor

    try:
        ratio_val = max(0.1, min(0.9, float(ratio)))
        if recursive or len(text) > 3000:
            result = context_compressor.summarize_recursive(text)
        else:
            result = context_compressor.summarize(text, ratio=ratio_val)

        lines = [
            "📝 Суммаризация:",
            f"  📏 Оригинал: {result.original_length} символов",
            f"  📐 Сжато: {result.compressed_length} символов",
            f"  💾 Экономия: {result.savings_pct:.1f}%",
            f"  📋 Метод: {result.method}",
        ]
        if result.key_terms:
            lines.append(f"  🏷️ Ключевые: {', '.join(result.key_terms[:5])}")
        lines.append(f"\n{result.text}")

        return ToolResult(
            "summarize_text", True, "\n".join(lines),
            data=result.to_dict(),
        )
    except Exception as e:
        return ToolResult(
            "summarize_text", False, "",
            error=f"Ошибка суммаризации: {e}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PART 10: TIME & RELEVANCE (handlers)
# ═══════════════════════════════════════════════════════════════════════════════


async def tool_check_freshness(
    text: str,
    **kwargs,
) -> ToolResult:
    """Проверить актуальность данных."""
    from pds_ultimate.core.time_relevance import time_relevance

    try:
        report = time_relevance.check_freshness(text)

        lines = [
            f"{report.grade.emoji} Свежесть: {report.grade.value.upper()}",
            f"  📊 Скор: {report.score:.0%}",
            f"  📅 Возраст: {report.data_age_days:.0f} дней",
        ]
        if report.markers:
            lines.append(f"  🔍 Дат найдено: {len(report.markers)}")
            for m in report.markers[:3]:
                lines.append(f"    • «{m.text}» → {m.scope.value}")
        if report.recommendation:
            lines.append(f"\n💡 {report.recommendation}")
        if report.needs_update:
            lines.append("⚠️ Рекомендуется обновить данные!")

        return ToolResult(
            "check_freshness", True, "\n".join(lines),
            data=report.to_dict(),
        )
    except Exception as e:
        return ToolResult(
            "check_freshness", False, "",
            error=f"Ошибка проверки свежести: {e}",
        )


async def tool_time_decay(
    score: float,
    age_days: float,
    method: str = "exponential",
    **kwargs,
) -> ToolResult:
    """Применить временное затухание."""
    from pds_ultimate.core.time_relevance import time_relevance

    try:
        adjusted = time_relevance.apply_time_decay(
            score=float(score),
            age_days=float(age_days),
            method=method,
        )
        delta = adjusted - float(score)
        lines = [
            "⏱️ Временное затухание:",
            f"  📊 Исходный скор: {float(score):.3f}",
            f"  📅 Возраст: {float(age_days):.0f} дней",
            f"  📈 Метод: {method}",
            f"  🎯 Скорректированный: {adjusted:.3f}",
            f"  📉 Дельта: {delta:+.3f}",
        ]
        return ToolResult(
            "time_decay", True, "\n".join(lines),
            data={
                "original": float(score),
                "adjusted": round(adjusted, 4),
                "delta": round(delta, 4),
                "method": method,
                "age_days": float(age_days),
            },
        )
    except Exception as e:
        return ToolResult(
            "time_decay", False, "",
            error=f"Ошибка затухания: {e}",
        )


# ── Part 11: Integration Layer handlers ──────────────────────────────

async def tool_run_chain(
    chain_name: str,
    query: str = "",
    **kwargs,
) -> ToolResult:
    """Запустить цепочку инструментов."""
    from pds_ultimate.core.integration_layer import integration_layer

    try:
        result = await integration_layer.execute_chain(
            chain_name, {"query": query} if query else {},
        )
        if result is None:
            return ToolResult(
                "run_chain", False, "",
                error=f"Цепочка '{chain_name}' не найдена. "
                "Используйте list_chains для списка.",
            )
        lines = [
            f"🔗 Цепочка: {chain_name}",
            f"  📊 Статус: {result.status.value}",
            f"  ⏱️ Время: {result.total_time:.2f}с",
            f"  📋 Шагов: {len(result.step_results)}",
        ]
        for i, sr in enumerate(result.step_results, 1):
            icon = "✅" if sr.success else "❌"
            lines.append(f"  {icon} Шаг {i}: {sr.step_name} "
                         f"({sr.duration:.2f}с)")
        return ToolResult(
            "run_chain", result.success, "\n".join(lines),
            data={
                "chain": chain_name,
                "status": result.status.value,
                "success": result.success,
                "total_time": round(result.total_time, 3),
                "steps": len(result.step_results),
            },
        )
    except Exception as e:
        return ToolResult(
            "run_chain", False, "",
            error=f"Ошибка выполнения цепочки: {e}",
        )


async def tool_health_check(
    action: str = "report",
    **kwargs,
) -> ToolResult:
    """Показать здоровье инструментов."""
    from pds_ultimate.core.integration_layer import integration_layer

    try:
        if action == "stats":
            stats = integration_layer.get_stats()
            lines = [
                "📊 Статистика интеграции:",
                f"  🔗 Цепочек: {stats.get('chains', 0)}",
                f"  🛡️ Breakers: {stats.get('circuit_breakers', 0)}",
                f"  📈 Метрик: {stats.get('metrics', 0)}",
                f"  🔄 Fallbacks: {stats.get('fallbacks', 0)}",
                f"  🩺 Auto-heals: {stats.get('auto_heals', 0)}",
            ]
            return ToolResult(
                "tool_health", True, "\n".join(lines), data=stats,
            )

        report = integration_layer.get_health_report()
        if action == "unhealthy":
            report = {k: v for k, v in report.items()
                      if v.get("health") != "healthy"}
        elif action == "slow":
            report = {k: v for k, v in report.items()
                      if v.get("avg_time", 0) > 2.0}

        if not report:
            return ToolResult(
                "tool_health", True,
                "✅ Все инструменты работают нормально.",
                data={"healthy": True},
            )

        lines = [f"🩺 Здоровье инструментов ({len(report)}):"]
        for name, info in list(report.items())[:20]:
            health = info.get("health", "unknown")
            icon = {"healthy": "✅", "degraded": "⚠️",
                    "unhealthy": "❌"}.get(health, "❓")
            lines.append(f"  {icon} {name}: {health}")
        return ToolResult(
            "tool_health", True, "\n".join(lines), data=report,
        )
    except Exception as e:
        return ToolResult(
            "tool_health", False, "",
            error=f"Ошибка проверки здоровья: {e}",
        )


async def tool_parallel_execute(
    calls: str,
    **kwargs,
) -> ToolResult:
    """Выполнить несколько инструментов параллельно."""
    from pds_ultimate.core.integration_layer import integration_layer

    try:
        # Парсим формат: tool1:p1=v1,p2=v2;tool2:p1=v1
        parsed = []
        for part in calls.split(";"):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                tname, params_str = part.split(":", 1)
                params = {}
                for kv in params_str.split(","):
                    kv = kv.strip()
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        params[k.strip()] = v.strip()
                parsed.append((tname.strip(), params))
            else:
                parsed.append((part.strip(), {}))

        if not parsed:
            return ToolResult(
                "parallel_tools", False, "",
                error="Не указаны вызовы. Формат: tool1:p1=v1;tool2:p2=v2",
            )

        results = await integration_layer.execute_parallel(parsed)
        ok = sum(1 for r in results if getattr(r, "success", False))
        lines = [
            f"⚡ Параллельное выполнение: {ok}/{len(results)} успешно",
        ]
        for i, r in enumerate(results):
            tname = parsed[i][0] if i < len(parsed) else "?"
            icon = "✅" if getattr(r, "success", False) else "❌"
            out = getattr(r, "output", "")
            snippet = (out[:60] + "…") if len(out) > 60 else out
            lines.append(f"  {icon} {tname}: {snippet}")
        return ToolResult(
            "parallel_tools", True, "\n".join(lines),
            data={"total": len(results), "success": ok},
        )
    except Exception as e:
        return ToolResult(
            "parallel_tools", False, "",
            error=f"Ошибка параллельного выполнения: {e}",
        )


async def tool_list_chains(**kwargs) -> ToolResult:
    """Показать все доступные цепочки."""
    from pds_ultimate.core.integration_layer import integration_layer

    try:
        chains = list(integration_layer.chains.keys())
        router_chains = list(integration_layer.router.routes.keys()) \
            if integration_layer.router else []
        lines = [f"🔗 Доступные цепочки ({len(chains)}):"]
        for ch in chains:
            chain = integration_layer.chains[ch]
            lines.append(f"  • {ch} ({len(chain.steps)} шагов)")
        if router_chains:
            lines.append(f"\n🗺️ Авто-маршруты ({len(router_chains)}):")
            for rc in router_chains:
                lines.append(f"  • {rc}")
        return ToolResult(
            "list_chains", True, "\n".join(lines),
            data={"chains": chains, "routes": router_chains},
        )
    except Exception as e:
        return ToolResult(
            "list_chains", False, "",
            error=f"Ошибка получения списка цепочек: {e}",
        )
