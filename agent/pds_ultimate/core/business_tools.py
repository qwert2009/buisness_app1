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
    ]

    for tool in tools:
        tool_registry.register(tool)

    logger.info(f"Зарегистрировано {len(tools)} бизнес-инструментов агента")
    return len(tools)


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
