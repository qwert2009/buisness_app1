"""
PDS-Ultimate — CRM Engine (Part 9)
=====================================
CRM-Lite: управление контактами, рейтинги, сделки, pipeline.

Функциональность:
- Рейтинг контактов/поставщиков (1-5 звёзд)
- История взаимодействий (interaction log)
- Метки и теги на контакты
- Deal pipeline (воронка сделок)
- Supplier scorecard (надёжность, сроки, цена)
- Follow-up reminders (напоминания о follow-up)
- Contact search & filtering
- CRM analytics (конверсия, средний цикл)

Архитектура:
    CRMEngine
    ├── ContactManager — управление контактами с рейтингами
    ├── InteractionLog — история взаимодействий
    ├── DealPipeline — воронка сделок
    └── SupplierScorecard — оценка поставщиков
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════════


class ContactType(str, Enum):
    """Тип контакта."""
    SUPPLIER = "supplier"
    CLIENT = "client"
    PARTNER = "partner"
    LOGISTICS = "logistics"
    OTHER = "other"


class InteractionType(str, Enum):
    """Тип взаимодействия."""
    CALL = "call"
    MESSAGE = "message"
    MEETING = "meeting"
    EMAIL = "email"
    ORDER = "order"
    PAYMENT = "payment"
    COMPLAINT = "complaint"
    NOTE = "note"


class DealStage(str, Enum):
    """Этап сделки."""
    LEAD = "lead"
    QUALIFIED = "qualified"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


class DealPriority(str, Enum):
    """Приоритет сделки."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class Interaction:
    """Запись о взаимодействии."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    contact_id: str = ""
    interaction_type: InteractionType = InteractionType.NOTE
    summary: str = ""
    details: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    sentiment: float = 0.0       # -1.0 .. +1.0
    follow_up_date: datetime | None = None
    follow_up_done: bool = False
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "contact_id": self.contact_id,
            "type": self.interaction_type.value,
            "summary": self.summary,
            "timestamp": self.timestamp.isoformat(),
            "sentiment": self.sentiment,
            "follow_up_date": (
                self.follow_up_date.isoformat() if self.follow_up_date else None
            ),
            "follow_up_done": self.follow_up_done,
        }


@dataclass
class CRMContact:
    """Контакт CRM с рейтингом и историей."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    contact_type: ContactType = ContactType.OTHER
    company: str = ""
    phone: str = ""
    email: str = ""
    telegram: str = ""
    rating: float = 0.0             # 0.0 - 5.0
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_interaction: datetime | None = None
    interaction_count: int = 0
    total_volume: float = 0.0       # Общий объём сделок
    metadata: dict = field(default_factory=dict)

    @property
    def star_rating(self) -> str:
        """Звёздный рейтинг."""
        full = int(self.rating)
        half = 1 if self.rating - full >= 0.5 else 0
        empty = 5 - full - half
        return "★" * full + "½" * half + "☆" * empty

    @property
    def days_since_contact(self) -> int:
        """Дней с последнего контакта."""
        if not self.last_interaction:
            return -1
        return (datetime.utcnow() - self.last_interaction).days

    def update_rating(self, new_rating: float) -> None:
        """Обновить рейтинг (скользящее среднее)."""
        if self.rating == 0:
            self.rating = new_rating
        else:
            # Weighted: новый рейтинг имеет вес 0.3
            self.rating = self.rating * 0.7 + new_rating * 0.3
        self.rating = max(0.0, min(5.0, round(self.rating, 1)))

    def add_volume(self, amount: float) -> None:
        """Добавить объём."""
        self.total_volume += amount

    def record_interaction(self) -> None:
        """Обновить счётчик."""
        self.interaction_count += 1
        self.last_interaction = datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.contact_type.value,
            "company": self.company,
            "rating": self.rating,
            "star_rating": self.star_rating,
            "tags": self.tags,
            "interaction_count": self.interaction_count,
            "total_volume": self.total_volume,
            "days_since_contact": self.days_since_contact,
            "phone": self.phone,
            "email": self.email,
        }

    def format_card(self) -> str:
        """Карточка контакта."""
        lines = [
            f"👤 {self.name} {self.star_rating}",
            f"  🏢 {self.company}" if self.company else "",
            f"  📋 Тип: {self.contact_type.value}",
            f"  📞 {self.phone}" if self.phone else "",
            f"  📧 {self.email}" if self.email else "",
            f"  💬 Взаимодействий: {self.interaction_count}",
            f"  💰 Объём: ${self.total_volume:,.2f}" if self.total_volume else "",
            f"  🏷️ {', '.join(self.tags)}" if self.tags else "",
        ]
        if self.days_since_contact >= 0:
            lines.append(
                f"  📅 Последний контакт: {self.days_since_contact} дн. назад")
        if self.notes:
            lines.append(f"  📝 {self.notes[:100]}")
        return "\n".join(line for line in lines if line)


@dataclass
class Deal:
    """Сделка в pipeline."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    contact_id: str = ""
    contact_name: str = ""
    stage: DealStage = DealStage.LEAD
    priority: DealPriority = DealPriority.MEDIUM
    amount: float = 0.0
    currency: str = "USD"
    probability: float = 0.5        # Вероятность закрытия (0-1)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    expected_close: datetime | None = None
    closed_at: datetime | None = None
    notes: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def is_open(self) -> bool:
        """Открыта ли сделка."""
        return self.stage not in (DealStage.CLOSED_WON, DealStage.CLOSED_LOST)

    @property
    def weighted_amount(self) -> float:
        """Взвешенная сумма (amount × probability)."""
        return self.amount * self.probability

    @property
    def age_days(self) -> int:
        """Возраст сделки в днях."""
        return (datetime.utcnow() - self.created_at).days

    def advance_stage(self) -> DealStage:
        """Продвинуть на следующий этап."""
        stages = [
            DealStage.LEAD, DealStage.QUALIFIED,
            DealStage.PROPOSAL, DealStage.NEGOTIATION,
        ]
        if self.stage in stages:
            idx = stages.index(self.stage)
            if idx + 1 < len(stages):
                self.stage = stages[idx + 1]
                self.updated_at = datetime.utcnow()
                # Increase probability as stage advances
                stage_probs = {
                    DealStage.QUALIFIED: 0.3,
                    DealStage.PROPOSAL: 0.5,
                    DealStage.NEGOTIATION: 0.7,
                }
                self.probability = stage_probs.get(
                    self.stage, self.probability)
        return self.stage

    def close_won(self) -> None:
        """Закрыть как выигранную."""
        self.stage = DealStage.CLOSED_WON
        self.probability = 1.0
        self.closed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def close_lost(self, reason: str = "") -> None:
        """Закрыть как проигранную."""
        self.stage = DealStage.CLOSED_LOST
        self.probability = 0.0
        self.closed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        if reason:
            self.notes = f"Lost: {reason}\n{self.notes}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "contact_name": self.contact_name,
            "stage": self.stage.value,
            "priority": self.priority.value,
            "amount": self.amount,
            "currency": self.currency,
            "probability": self.probability,
            "weighted_amount": self.weighted_amount,
            "age_days": self.age_days,
            "is_open": self.is_open,
        }


@dataclass
class SupplierScore:
    """Скоркарта поставщика."""
    contact_id: str = ""
    reliability: float = 3.0        # Надёжность (1-5)
    quality: float = 3.0            # Качество (1-5)
    pricing: float = 3.0            # Ценовая конкурентность (1-5)
    communication: float = 3.0      # Коммуникация (1-5)
    delivery_speed: float = 3.0     # Скорость доставки (1-5)
    total_orders: int = 0
    on_time_deliveries: int = 0
    defect_rate: float = 0.0        # % брака
    avg_response_hours: float = 24.0
    notes: str = ""

    @property
    def overall_score(self) -> float:
        """Общий балл (взвешенное среднее)."""
        weights = {
            "reliability": 0.25,
            "quality": 0.25,
            "pricing": 0.2,
            "communication": 0.15,
            "delivery_speed": 0.15,
        }
        score = (
            self.reliability * weights["reliability"]
            + self.quality * weights["quality"]
            + self.pricing * weights["pricing"]
            + self.communication * weights["communication"]
            + self.delivery_speed * weights["delivery_speed"]
        )
        return round(score, 1)

    @property
    def on_time_rate(self) -> float:
        """% вовремя доставок."""
        if self.total_orders == 0:
            return 0.0
        return self.on_time_deliveries / self.total_orders * 100

    def update_category(self, category: str, score: float) -> None:
        """Обновить категорию (скользящее среднее)."""
        score = max(1.0, min(5.0, score))
        current = getattr(self, category, None)
        if current is not None:
            new_val = current * 0.7 + score * 0.3
            setattr(self, category, round(new_val, 1))

    def to_dict(self) -> dict:
        return {
            "contact_id": self.contact_id,
            "overall": self.overall_score,
            "reliability": self.reliability,
            "quality": self.quality,
            "pricing": self.pricing,
            "communication": self.communication,
            "delivery_speed": self.delivery_speed,
            "total_orders": self.total_orders,
            "on_time_rate": round(self.on_time_rate, 1),
            "defect_rate": self.defect_rate,
        }

    def format_scorecard(self, name: str = "") -> str:
        """Форматированная скоркарта."""
        def bar(val: float) -> str:
            filled = int(val)
            return "★" * filled + "☆" * (5 - filled)

        lines = [
            f"📊 Скоркарта: {name}" if name else "📊 Скоркарта поставщика",
            f"  🏆 Общий балл: {self.overall_score}/5.0",
            f"  🔒 Надёжность:  {bar(self.reliability)} ({self.reliability})",
            f"  ✅ Качество:    {bar(self.quality)} ({self.quality})",
            f"  💰 Цена:        {bar(self.pricing)} ({self.pricing})",
            f"  💬 Коммуникация: {bar(self.communication)} ({self.communication})",
            f"  🚚 Доставка:    {bar(self.delivery_speed)} ({self.delivery_speed})",
            f"  📦 Заказов: {self.total_orders} (вовремя: {self.on_time_rate:.0f}%)",
        ]
        if self.defect_rate > 0:
            lines.append(f"  ⚠️ Брак: {self.defect_rate:.1f}%")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# INTERACTION LOG
# ═══════════════════════════════════════════════════════════════════════════════


class InteractionLog:
    """История взаимодействий."""

    def __init__(self, max_per_contact: int = 200):
        self._interactions: dict[str, list[Interaction]] = {}
        self._max_per_contact = max_per_contact

    def add(
        self,
        contact_id: str,
        interaction_type: InteractionType | str,
        summary: str,
        details: str = "",
        sentiment: float = 0.0,
        follow_up_days: int = 0,
    ) -> Interaction:
        """Добавить взаимодействие."""
        if isinstance(interaction_type, str):
            interaction_type = InteractionType(interaction_type.lower())

        interaction = Interaction(
            contact_id=contact_id,
            interaction_type=interaction_type,
            summary=summary,
            details=details,
            sentiment=sentiment,
        )

        if follow_up_days > 0:
            interaction.follow_up_date = (
                datetime.utcnow() + timedelta(days=follow_up_days)
            )

        if contact_id not in self._interactions:
            self._interactions[contact_id] = []

        self._interactions[contact_id].append(interaction)

        # Trim
        if len(self._interactions[contact_id]) > self._max_per_contact:
            self._interactions[contact_id] = (
                self._interactions[contact_id][-self._max_per_contact:]
            )

        return interaction

    def get_history(
        self,
        contact_id: str,
        limit: int = 20,
    ) -> list[Interaction]:
        """История контакта."""
        interactions = self._interactions.get(contact_id, [])
        return list(reversed(interactions[-limit:]))

    def get_pending_followups(self) -> list[Interaction]:
        """Ожидающие follow-up."""
        now = datetime.utcnow()
        pending = []
        for interactions in self._interactions.values():
            for i in interactions:
                if (
                    i.follow_up_date
                    and not i.follow_up_done
                    and i.follow_up_date <= now
                ):
                    pending.append(i)
        return sorted(pending, key=lambda i: i.follow_up_date or now)

    def get_upcoming_followups(self, days: int = 7) -> list[Interaction]:
        """Предстоящие follow-up."""
        now = datetime.utcnow()
        cutoff = now + timedelta(days=days)
        upcoming = []
        for interactions in self._interactions.values():
            for i in interactions:
                if (
                    i.follow_up_date
                    and not i.follow_up_done
                    and now < i.follow_up_date <= cutoff
                ):
                    upcoming.append(i)
        return sorted(upcoming, key=lambda i: i.follow_up_date or now)

    def mark_followup_done(self, interaction_id: str) -> bool:
        """Отметить follow-up как выполненный."""
        for interactions in self._interactions.values():
            for i in interactions:
                if i.id == interaction_id:
                    i.follow_up_done = True
                    return True
        return False

    def get_contact_sentiment(self, contact_id: str) -> float:
        """Средний sentiment контакта."""
        interactions = self._interactions.get(contact_id, [])
        if not interactions:
            return 0.0
        sentiments = [i.sentiment for i in interactions if i.sentiment != 0]
        return sum(sentiments) / len(sentiments) if sentiments else 0.0

    @property
    def total_interactions(self) -> int:
        return sum(len(v) for v in self._interactions.values())


# ═══════════════════════════════════════════════════════════════════════════════
# DEAL PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════


class DealPipeline:
    """Воронка сделок."""

    def __init__(self, max_deals: int = 500):
        self._deals: dict[str, Deal] = {}
        self._max_deals = max_deals

    def create_deal(
        self,
        title: str,
        contact_id: str = "",
        contact_name: str = "",
        amount: float = 0.0,
        currency: str = "USD",
        priority: DealPriority | str = DealPriority.MEDIUM,
        expected_close_days: int = 30,
        tags: list[str] | None = None,
    ) -> Deal:
        """Создать сделку."""
        if len(self._deals) >= self._max_deals:
            # Clean closed
            self._cleanup_closed()
            if len(self._deals) >= self._max_deals:
                raise ValueError(f"Лимит сделок ({self._max_deals})")

        if isinstance(priority, str):
            priority = DealPriority(priority.lower())

        deal = Deal(
            title=title,
            contact_id=contact_id,
            contact_name=contact_name,
            amount=amount,
            currency=currency,
            priority=priority,
            tags=tags or [],
        )

        if expected_close_days > 0:
            deal.expected_close = (
                datetime.utcnow() + timedelta(days=expected_close_days)
            )

        self._deals[deal.id] = deal
        return deal

    def get_deal(self, deal_id: str) -> Deal | None:
        """Получить сделку."""
        return self._deals.get(deal_id)

    def find_deals(
        self,
        contact_id: str | None = None,
        stage: DealStage | None = None,
        priority: DealPriority | None = None,
        open_only: bool = False,
    ) -> list[Deal]:
        """Найти сделки."""
        result = list(self._deals.values())
        if contact_id:
            result = [d for d in result if d.contact_id == contact_id]
        if stage:
            result = [d for d in result if d.stage == stage]
        if priority:
            result = [d for d in result if d.priority == priority]
        if open_only:
            result = [d for d in result if d.is_open]
        return result

    def advance_deal(self, deal_id: str) -> Deal | None:
        """Продвинуть сделку."""
        deal = self._deals.get(deal_id)
        if deal and deal.is_open:
            deal.advance_stage()
        return deal

    def close_deal_won(self, deal_id: str) -> Deal | None:
        """Закрыть сделку (выиграна)."""
        deal = self._deals.get(deal_id)
        if deal:
            deal.close_won()
        return deal

    def close_deal_lost(self, deal_id: str, reason: str = "") -> Deal | None:
        """Закрыть сделку (проиграна)."""
        deal = self._deals.get(deal_id)
        if deal:
            deal.close_lost(reason)
        return deal

    def delete_deal(self, deal_id: str) -> bool:
        """Удалить сделку."""
        if deal_id in self._deals:
            del self._deals[deal_id]
            return True
        return False

    # ── Pipeline analytics ────────────────────────────────────────────────

    def get_pipeline_value(self) -> float:
        """Общая стоимость pipeline (открытые)."""
        return sum(
            d.amount for d in self._deals.values() if d.is_open
        )

    def get_weighted_pipeline(self) -> float:
        """Взвешенная стоимость pipeline."""
        return sum(
            d.weighted_amount for d in self._deals.values() if d.is_open
        )

    def get_conversion_rate(self) -> float:
        """Конверсия (won / total closed)."""
        closed = [d for d in self._deals.values() if not d.is_open]
        if not closed:
            return 0.0
        won = sum(1 for d in closed if d.stage == DealStage.CLOSED_WON)
        return won / len(closed) * 100

    def get_avg_deal_cycle(self) -> float:
        """Средний цикл сделки (дни)."""
        closed_won = [
            d for d in self._deals.values()
            if d.stage == DealStage.CLOSED_WON and d.closed_at
        ]
        if not closed_won:
            return 0.0
        cycles = [(d.closed_at - d.created_at).days for d in closed_won]
        return sum(cycles) / len(cycles)

    def get_stage_distribution(self) -> dict[str, int]:
        """Распределение по этапам."""
        dist: dict[str, int] = {}
        for d in self._deals.values():
            dist[d.stage.value] = dist.get(d.stage.value, 0) + 1
        return dist

    def format_pipeline(self) -> str:
        """Форматированный pipeline."""
        open_deals = sorted(
            [d for d in self._deals.values() if d.is_open],
            key=lambda d: (-d.amount, d.created_at),
        )

        if not open_deals:
            return "📊 Pipeline пуст."

        stage_icons = {
            "lead": "🔵", "qualified": "🟢",
            "proposal": "🟡", "negotiation": "🟠",
        }

        lines = [
            f"📊 Pipeline ({len(open_deals)} сделок, "
            f"${self.get_pipeline_value():,.0f}):"
        ]

        for d in open_deals:
            icon = stage_icons.get(d.stage.value, "⚪")
            lines.append(
                f"  {icon} {d.title} — ${d.amount:,.0f} "
                f"[{d.stage.value}] {d.contact_name}"
            )

        return "\n".join(lines)

    def _cleanup_closed(self, keep_last: int = 100) -> int:
        """Очистить старые закрытые сделки."""
        closed = sorted(
            [d for d in self._deals.values() if not d.is_open],
            key=lambda d: d.closed_at or d.created_at,
        )
        to_remove = closed[:-keep_last] if len(closed) > keep_last else []
        for d in to_remove:
            del self._deals[d.id]
        return len(to_remove)

    def get_stats(self) -> dict:
        """Статистика pipeline."""
        deals = list(self._deals.values())
        return {
            "total": len(deals),
            "open": sum(1 for d in deals if d.is_open),
            "closed_won": sum(1 for d in deals if d.stage == DealStage.CLOSED_WON),
            "closed_lost": sum(1 for d in deals if d.stage == DealStage.CLOSED_LOST),
            "pipeline_value": round(self.get_pipeline_value(), 2),
            "weighted_value": round(self.get_weighted_pipeline(), 2),
            "conversion_rate": round(self.get_conversion_rate(), 1),
            "avg_cycle_days": round(self.get_avg_deal_cycle(), 1),
            "by_stage": self.get_stage_distribution(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# CONTACT MANAGER (CRM)
# ═══════════════════════════════════════════════════════════════════════════════


class ContactManager:
    """Управление контактами CRM."""

    def __init__(self, max_contacts: int = 2000):
        self._contacts: dict[str, CRMContact] = {}
        self._max_contacts = max_contacts

    def create_contact(
        self,
        name: str,
        contact_type: ContactType | str = ContactType.OTHER,
        company: str = "",
        phone: str = "",
        email: str = "",
        telegram: str = "",
        rating: float = 3.0,
        tags: list[str] | None = None,
        notes: str = "",
    ) -> CRMContact:
        """Создать контакт."""
        if len(self._contacts) >= self._max_contacts:
            raise ValueError(f"Лимит контактов ({self._max_contacts})")

        if isinstance(contact_type, str):
            contact_type = ContactType(contact_type.lower())

        contact = CRMContact(
            name=name,
            contact_type=contact_type,
            company=company,
            phone=phone,
            email=email,
            telegram=telegram,
            rating=max(0, min(5, rating)),
            tags=tags or [],
            notes=notes,
        )
        self._contacts[contact.id] = contact
        return contact

    def get_contact(self, contact_id: str) -> CRMContact | None:
        """Получить контакт."""
        return self._contacts.get(contact_id)

    def find_by_name(self, query: str) -> list[CRMContact]:
        """Найти по имени."""
        query_lower = query.lower()
        return [
            c for c in self._contacts.values()
            if query_lower in c.name.lower()
            or query_lower in c.company.lower()
        ]

    def find_by_tags(self, tags: list[str]) -> list[CRMContact]:
        """Найти по тегам."""
        return [
            c for c in self._contacts.values()
            if any(t in c.tags for t in tags)
        ]

    def find_by_type(self, contact_type: ContactType) -> list[CRMContact]:
        """Найти по типу."""
        return [
            c for c in self._contacts.values()
            if c.contact_type == contact_type
        ]

    def search(
        self,
        query: str = "",
        contact_type: ContactType | None = None,
        min_rating: float = 0.0,
        tags: list[str] | None = None,
        sort_by: str = "rating",
    ) -> list[CRMContact]:
        """Расширенный поиск."""
        results = list(self._contacts.values())

        if query:
            q = query.lower()
            results = [
                c for c in results
                if q in c.name.lower()
                or q in c.company.lower()
                or q in c.notes.lower()
                or q in c.phone
                or q in c.email
            ]

        if contact_type:
            results = [c for c in results if c.contact_type == contact_type]

        if min_rating > 0:
            results = [c for c in results if c.rating >= min_rating]

        if tags:
            results = [
                c for c in results
                if any(t in c.tags for t in tags)
            ]

        sort_keys = {
            "rating": lambda c: -c.rating,
            "name": lambda c: c.name.lower(),
            "volume": lambda c: -c.total_volume,
            "recent": lambda c: -(c.last_interaction or c.created_at).timestamp(),
            "interactions": lambda c: -c.interaction_count,
        }
        key_fn = sort_keys.get(sort_by, sort_keys["rating"])
        results.sort(key=key_fn)

        return results

    def rate_contact(
        self,
        contact_id: str,
        rating: float,
    ) -> CRMContact | None:
        """Оценить контакт."""
        contact = self._contacts.get(contact_id)
        if contact:
            contact.update_rating(rating)
        return contact

    def update_contact(
        self,
        contact_id: str,
        **kwargs,
    ) -> CRMContact | None:
        """Обновить поля контакта."""
        contact = self._contacts.get(contact_id)
        if not contact:
            return None
        for key, value in kwargs.items():
            if hasattr(contact, key) and key != "id":
                setattr(contact, key, value)
        return contact

    def delete_contact(self, contact_id: str) -> bool:
        """Удалить контакт."""
        if contact_id in self._contacts:
            del self._contacts[contact_id]
            return True
        return False

    def get_top_rated(self, limit: int = 10) -> list[CRMContact]:
        """Топ по рейтингу."""
        return sorted(
            self._contacts.values(),
            key=lambda c: -c.rating,
        )[:limit]

    def get_inactive(self, days: int = 30) -> list[CRMContact]:
        """Контакты без взаимодействия N+ дней."""
        return [
            c for c in self._contacts.values()
            if c.days_since_contact >= days or c.days_since_contact == -1
        ]

    def get_stats(self) -> dict:
        """Статистика контактов."""
        contacts = list(self._contacts.values())
        by_type: dict[str, int] = {}
        for c in contacts:
            by_type[c.contact_type.value] = by_type.get(
                c.contact_type.value, 0) + 1

        ratings = [c.rating for c in contacts if c.rating > 0]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0.0

        return {
            "total": len(contacts),
            "by_type": by_type,
            "avg_rating": round(avg_rating, 1),
            "inactive_30d": len(self.get_inactive(30)),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# CRM ENGINE
# ═══════════════════════════════════════════════════════════════════════════════


class CRMEngine:
    """
    CRM-Lite Engine.

    Объединяет контакты, взаимодействия, сделки и оценки поставщиков.
    """

    def __init__(self):
        self.contacts = ContactManager()
        self.interactions = InteractionLog()
        self.pipeline = DealPipeline()
        self._supplier_scores: dict[str, SupplierScore] = {}

    # ── Contact shortcuts ─────────────────────────────────────────────────

    def add_contact(
        self,
        name: str,
        contact_type: str = "other",
        company: str = "",
        phone: str = "",
        email: str = "",
        rating: float = 3.0,
        tags: list[str] | None = None,
    ) -> CRMContact:
        """Добавить контакт."""
        return self.contacts.create_contact(
            name=name,
            contact_type=contact_type,
            company=company,
            phone=phone,
            email=email,
            rating=rating,
            tags=tags,
        )

    def rate_contact(
        self,
        name: str,
        rating: float,
        comment: str = "",
    ) -> CRMContact | None:
        """Оценить контакт по имени."""
        results = self.contacts.find_by_name(name)
        if not results:
            return None
        contact = results[0]
        contact.update_rating(rating)

        if comment:
            self.interactions.add(
                contact.id,
                InteractionType.NOTE,
                f"Рейтинг: {rating}/5 — {comment}",
                sentiment=rating / 5 * 2 - 1,  # Map 1-5 to -1..+1
            )
            contact.record_interaction()

        return contact

    def log_interaction(
        self,
        name: str,
        interaction_type: str,
        summary: str,
        details: str = "",
        follow_up_days: int = 0,
    ) -> Interaction | None:
        """Записать взаимодействие по имени контакта."""
        results = self.contacts.find_by_name(name)
        if not results:
            return None
        contact = results[0]
        contact.record_interaction()

        return self.interactions.add(
            contact.id,
            interaction_type,
            summary,
            details,
            follow_up_days=follow_up_days,
        )

    def search_contacts(
        self,
        query: str = "",
        contact_type: str = "",
        min_rating: float = 0.0,
    ) -> list[CRMContact]:
        """Поиск контактов."""
        ct = ContactType(contact_type.lower()) if contact_type else None
        return self.contacts.search(
            query=query,
            contact_type=ct,
            min_rating=min_rating,
        )

    # ── Supplier scoring ──────────────────────────────────────────────────

    def get_supplier_score(self, contact_id: str) -> SupplierScore:
        """Получить или создать скоркарту поставщика."""
        if contact_id not in self._supplier_scores:
            self._supplier_scores[contact_id] = SupplierScore(
                contact_id=contact_id
            )
        return self._supplier_scores[contact_id]

    def rate_supplier(
        self,
        name: str,
        category: str,
        score: float,
    ) -> SupplierScore | None:
        """Оценить поставщика в категории."""
        results = self.contacts.find_by_name(name)
        if not results:
            return None
        contact = results[0]
        scorecard = self.get_supplier_score(contact.id)
        scorecard.update_category(category, score)

        # Update contact rating from overall
        contact.update_rating(scorecard.overall_score)

        return scorecard

    def get_supplier_ranking(self) -> list[tuple[CRMContact, SupplierScore]]:
        """Рейтинг поставщиков."""
        ranking = []
        for cid, score in self._supplier_scores.items():
            contact = self.contacts.get_contact(cid)
            if contact:
                ranking.append((contact, score))
        return sorted(ranking, key=lambda x: -x[1].overall_score)

    # ── Deal shortcuts ────────────────────────────────────────────────────

    def create_deal(
        self,
        title: str,
        contact_name: str = "",
        amount: float = 0.0,
        priority: str = "medium",
    ) -> Deal:
        """Создать сделку."""
        contact_id = ""
        if contact_name:
            results = self.contacts.find_by_name(contact_name)
            if results:
                contact_id = results[0].id

        return self.pipeline.create_deal(
            title=title,
            contact_id=contact_id,
            contact_name=contact_name,
            amount=amount,
            priority=priority,
        )

    # ── Stats ─────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Полная статистика CRM."""
        return {
            "contacts": self.contacts.get_stats(),
            "pipeline": self.pipeline.get_stats(),
            "interactions": self.interactions.total_interactions,
            "suppliers_scored": len(self._supplier_scores),
            "pending_followups": len(self.interactions.get_pending_followups()),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

crm_engine = CRMEngine()
