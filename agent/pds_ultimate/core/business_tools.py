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
    ]

    for tool in tools:
        tool_registry.register(tool)

    logger.info(f"Зарегистрировано {len(tools)} бизнес-инструментов агента")
    return len(tools)
