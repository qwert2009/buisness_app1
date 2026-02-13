"""
PDS-Ultimate — Evening Digest Engine (Part 9)
================================================
Вечерний дайджест и итоговые отчёты дня.

Функциональность:
- Итоги дня (заказы, финансы, контакты)
- Нерешённые вопросы / пропущенные follow-up
- Рекомендации на завтра
- Сравнение с вчерашним днём
- Краткая сводка по KPI
- Персонализация (что важно для пользователя)
- Формат для Telegram / text

Архитектура:
    EveningDigestEngine
    ├── DayRecapCollector — сбор итогов дня
    ├── RecommendationEngine — рекомендации
    └── DigestFormatter — форматирование
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════════


class DigestSection(str, Enum):
    """Секции дайджеста."""
    ORDERS = "orders"
    FINANCE = "finance"
    CONTACTS = "contacts"
    TASKS = "tasks"
    ALERTS = "alerts"
    KPI = "kpi"
    RECOMMENDATIONS = "recommendations"
    UNRESOLVED = "unresolved"


class RecommendationType(str, Enum):
    """Типы рекомендаций."""
    FOLLOWUP = "followup"           # Нужен follow-up
    OPPORTUNITY = "opportunity"     # Возможность
    RISK = "risk"                   # Риск
    REMINDER = "reminder"           # Напоминание
    OPTIMIZATION = "optimization"   # Оптимизация
    CELEBRATION = "celebration"     # Достижение


class DigestPriority(str, Enum):
    """Приоритет элемента."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class DigestItem:
    """Элемент дайджеста."""
    section: DigestSection
    title: str
    description: str = ""
    priority: DigestPriority = DigestPriority.MEDIUM
    value: Any = None
    icon: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "section": self.section.value,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
        }

    def format_line(self) -> str:
        """Однострочный формат."""
        icon = self.icon or self._default_icon()
        return f"{icon} {self.title}" + (f" — {self.description}" if self.description else "")

    def _default_icon(self) -> str:
        icons = {
            "orders": "📦", "finance": "💰", "contacts": "👤",
            "tasks": "✅", "alerts": "🔔", "kpi": "📊",
            "recommendations": "💡", "unresolved": "❓",
        }
        return icons.get(self.section.value, "•")


@dataclass
class Recommendation:
    """Рекомендация."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    rec_type: RecommendationType = RecommendationType.REMINDER
    title: str = ""
    description: str = ""
    priority: DigestPriority = DigestPriority.MEDIUM
    action_text: str = ""           # Что делать
    deadline: datetime | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.rec_type.value,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "action": self.action_text,
        }

    def format_text(self) -> str:
        """Текстовый формат."""
        type_icons = {
            "followup": "📞", "opportunity": "🎯",
            "risk": "⚠️", "reminder": "🔔",
            "optimization": "⚡", "celebration": "🎉",
        }
        icon = type_icons.get(self.rec_type.value, "💡")
        parts = [f"{icon} {self.title}"]
        if self.description:
            parts.append(f"   {self.description}")
        if self.action_text:
            parts.append(f"   → {self.action_text}")
        return "\n".join(parts)


@dataclass
class DaySummary:
    """Итоги дня."""
    date: datetime = field(default_factory=datetime.utcnow)
    orders_created: int = 0
    orders_completed: int = 0
    orders_total_value: float = 0.0
    revenue: float = 0.0
    expenses: float = 0.0
    profit: float = 0.0
    new_contacts: int = 0
    interactions: int = 0
    tasks_completed: int = 0
    tasks_pending: int = 0
    alerts_fired: int = 0
    critical_alerts: int = 0
    messages_sent: int = 0
    messages_received: int = 0

    @property
    def net_profit_margin(self) -> float:
        """Маржа прибыли."""
        if self.revenue == 0:
            return 0.0
        return (self.profit / self.revenue) * 100

    def to_dict(self) -> dict:
        return {
            "date": self.date.strftime("%Y-%m-%d"),
            "orders_created": self.orders_created,
            "orders_completed": self.orders_completed,
            "revenue": self.revenue,
            "expenses": self.expenses,
            "profit": self.profit,
            "profit_margin": round(self.net_profit_margin, 1),
            "tasks_completed": self.tasks_completed,
            "tasks_pending": self.tasks_pending,
            "alerts": self.alerts_fired,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# DAY RECAP COLLECTOR
# ═══════════════════════════════════════════════════════════════════════════════


class DayRecapCollector:
    """Сборщик итогов дня."""

    def __init__(self):
        self._summaries: list[DaySummary] = []
        self._max_history = 365     # Хранить год

    def record_day(self, summary: DaySummary) -> None:
        """Записать итоги дня."""
        self._summaries.append(summary)
        if len(self._summaries) > self._max_history:
            self._summaries = self._summaries[-self._max_history:]

    def get_today(self) -> DaySummary:
        """Итоги за сегодня."""
        today = datetime.utcnow().date()
        for s in reversed(self._summaries):
            if s.date.date() == today:
                return s
        return DaySummary()

    def get_yesterday(self) -> DaySummary:
        """Итоги за вчера."""
        yesterday = (datetime.utcnow() - timedelta(days=1)).date()
        for s in reversed(self._summaries):
            if s.date.date() == yesterday:
                return s
        return DaySummary()

    def get_last_n_days(self, n: int = 7) -> list[DaySummary]:
        """Итоги за N дней."""
        cutoff = datetime.utcnow() - timedelta(days=n)
        return [
            s for s in self._summaries
            if s.date >= cutoff
        ]

    def compare_with_yesterday(self) -> dict[str, dict]:
        """Сравнение сегодня с вчера."""
        today = self.get_today()
        yesterday = self.get_yesterday()

        fields = [
            ("revenue", "Доход"),
            ("expenses", "Расходы"),
            ("profit", "Прибыль"),
            ("orders_created", "Заказы"),
            ("tasks_completed", "Задачи"),
        ]

        comparison = {}
        for field_name, label in fields:
            today_val = getattr(today, field_name, 0)
            yest_val = getattr(yesterday, field_name, 0)
            change = today_val - yest_val
            pct = (change / abs(yest_val) * 100) if yest_val != 0 else 0

            comparison[field_name] = {
                "label": label,
                "today": today_val,
                "yesterday": yest_val,
                "change": change,
                "change_pct": round(pct, 1),
                "improved": change > 0,
            }

        return comparison

    @property
    def total_days(self) -> int:
        return len(self._summaries)


# ═══════════════════════════════════════════════════════════════════════════════
# RECOMMENDATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════


class RecommendationEngine:
    """Движок рекомендаций."""

    def __init__(self):
        self._rules: list[dict] = []
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        """Стандартные правила рекомендаций."""
        self._rules = [
            {
                "name": "low_profit_margin",
                "check": lambda s: s.net_profit_margin < 20 and s.revenue > 0,
                "generate": lambda s: Recommendation(
                    rec_type=RecommendationType.RISK,
                    title="Низкая маржа",
                    description=f"Маржа прибыли {s.net_profit_margin:.1f}% (цель: 20%+)",
                    priority=DigestPriority.HIGH,
                    action_text="Пересмотрите ценообразование или снизьте расходы",
                ),
            },
            {
                "name": "pending_tasks",
                "check": lambda s: s.tasks_pending > 5,
                "generate": lambda s: Recommendation(
                    rec_type=RecommendationType.REMINDER,
                    title=f"Незавершённых задач: {s.tasks_pending}",
                    description="Много отложенных задач",
                    priority=DigestPriority.MEDIUM,
                    action_text="Разберите задачи завтра утром",
                ),
            },
            {
                "name": "no_orders",
                "check": lambda s: s.orders_created == 0 and s.revenue == 0,
                "generate": lambda s: Recommendation(
                    rec_type=RecommendationType.OPPORTUNITY,
                    title="Нет новых заказов сегодня",
                    description="Рассмотрите активные продажи",
                    priority=DigestPriority.LOW,
                    action_text="Свяжитесь с клиентами из списка",
                ),
            },
            {
                "name": "good_day",
                "check": lambda s: s.profit > 0 and s.tasks_completed > 3,
                "generate": lambda s: Recommendation(
                    rec_type=RecommendationType.CELEBRATION,
                    title="Продуктивный день!",
                    description=(
                        f"Прибыль: ${s.profit:,.2f}, "
                        f"задач выполнено: {s.tasks_completed}"
                    ),
                    priority=DigestPriority.LOW,
                    action_text="Отличная работа! Так держать!",
                ),
            },
            {
                "name": "critical_alerts",
                "check": lambda s: s.critical_alerts > 0,
                "generate": lambda s: Recommendation(
                    rec_type=RecommendationType.RISK,
                    title=f"Критических алертов: {s.critical_alerts}",
                    description="Есть нерешённые критические проблемы",
                    priority=DigestPriority.HIGH,
                    action_text="Проверьте алерты и примите меры",
                ),
            },
        ]

    def add_rule(
        self,
        name: str,
        check_fn,
        generate_fn,
    ) -> None:
        """Добавить правило рекомендаций."""
        self._rules.append({
            "name": name,
            "check": check_fn,
            "generate": generate_fn,
        })

    def generate(self, summary: DaySummary) -> list[Recommendation]:
        """Сгенерировать рекомендации на основе итогов дня."""
        recommendations = []

        for rule in self._rules:
            try:
                if rule["check"](summary):
                    rec = rule["generate"](summary)
                    recommendations.append(rec)
            except Exception:
                continue

        # Sort: HIGH first
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(
            key=lambda r: priority_order.get(r.priority.value, 99)
        )

        return recommendations


# ═══════════════════════════════════════════════════════════════════════════════
# DIGEST FORMATTER
# ═══════════════════════════════════════════════════════════════════════════════


class DigestFormatter:
    """Форматирование дайджеста."""

    def format_evening_digest(
        self,
        summary: DaySummary,
        comparison: dict[str, dict] | None = None,
        recommendations: list[Recommendation] | None = None,
        unresolved: list[str] | None = None,
        kpi_summary: str = "",
    ) -> str:
        """Полный вечерний дайджест."""
        lines = []
        lines.append("🌙 ВЕЧЕРНИЙ ДАЙДЖЕСТ")
        lines.append(f"📅 {summary.date.strftime('%d.%m.%Y')}")
        lines.append("═" * 40)

        # Финансы
        lines.append("\n💰 Финансы:")
        lines.append(f"  📈 Доход: ${summary.revenue:,.2f}")
        lines.append(f"  📉 Расходы: ${summary.expenses:,.2f}")
        profit_icon = "✅" if summary.profit >= 0 else "❌"
        lines.append(f"  {profit_icon} Прибыль: ${summary.profit:,.2f}")
        if summary.revenue > 0:
            lines.append(f"  📊 Маржа: {summary.net_profit_margin:.1f}%")

        # Заказы
        lines.append("\n📦 Заказы:")
        lines.append(f"  🆕 Создано: {summary.orders_created}")
        lines.append(f"  ✅ Завершено: {summary.orders_completed}")
        if summary.orders_total_value > 0:
            lines.append(f"  💵 Объём: ${summary.orders_total_value:,.2f}")

        # Задачи
        lines.append("\n✅ Задачи:")
        lines.append(f"  ✔️ Выполнено: {summary.tasks_completed}")
        lines.append(f"  ⏳ В ожидании: {summary.tasks_pending}")

        # Коммуникации
        if summary.interactions > 0 or summary.new_contacts > 0:
            lines.append("\n👥 Коммуникации:")
            if summary.new_contacts > 0:
                lines.append(f"  🆕 Новые контакты: {summary.new_contacts}")
            if summary.interactions > 0:
                lines.append(f"  💬 Взаимодействий: {summary.interactions}")

        # Алерты
        if summary.alerts_fired > 0:
            lines.append(f"\n🔔 Алерты: {summary.alerts_fired}")
            if summary.critical_alerts > 0:
                lines.append(f"  🔴 Критических: {summary.critical_alerts}")

        # Сравнение с вчера
        if comparison:
            lines.append("\n📊 По сравнению с вчера:")
            for field_data in comparison.values():
                if field_data["yesterday"] == 0 and field_data["today"] == 0:
                    continue
                arrow = "📈" if field_data["improved"] else "📉"
                sign = "+" if field_data["change"] >= 0 else ""
                lines.append(
                    f"  {arrow} {field_data['label']}: "
                    f"{sign}{field_data['change_pct']:.0f}%"
                )

        # KPI
        if kpi_summary:
            lines.append(f"\n{kpi_summary}")

        # Нерешённые вопросы
        if unresolved:
            lines.append("\n❓ Нерешённые вопросы:")
            for item in unresolved[:5]:
                lines.append(f"  • {item}")

        # Рекомендации
        if recommendations:
            lines.append("\n💡 Рекомендации:")
            for rec in recommendations[:5]:
                lines.append(f"  {rec.format_text()}")

        lines.append("\n" + "═" * 40)
        lines.append("Хорошего вечера! 🌟")

        return "\n".join(lines)

    def format_short_digest(self, summary: DaySummary) -> str:
        """Краткий дайджест (1-2 строки)."""
        parts = []
        if summary.revenue > 0:
            parts.append(f"💰${summary.revenue:,.0f}")
        if summary.profit != 0:
            sign = "+" if summary.profit >= 0 else ""
            parts.append(f"📈{sign}${summary.profit:,.0f}")
        if summary.orders_created > 0:
            parts.append(f"📦{summary.orders_created}")
        if summary.tasks_completed > 0:
            parts.append(f"✅{summary.tasks_completed}")
        if summary.alerts_fired > 0:
            parts.append(f"🔔{summary.alerts_fired}")

        return " | ".join(parts) if parts else "📋 Спокойный день"


# ═══════════════════════════════════════════════════════════════════════════════
# EVENING DIGEST ENGINE
# ═══════════════════════════════════════════════════════════════════════════════


class EveningDigestEngine:
    """
    Движок вечернего дайджеста.

    Собирает итоги дня, генерирует рекомендации и форматирует отчёт.
    """

    def __init__(self):
        self.recap = DayRecapCollector()
        self.recommender = RecommendationEngine()
        self.formatter = DigestFormatter()

    def record_day_summary(self, summary: DaySummary) -> None:
        """Записать итоги дня."""
        self.recap.record_day(summary)

    def create_summary(self, **kwargs) -> DaySummary:
        """Создать и записать итоги дня."""
        summary = DaySummary(**kwargs)
        self.recap.record_day(summary)
        return summary

    def generate_digest(
        self,
        summary: DaySummary | None = None,
        kpi_summary: str = "",
        unresolved: list[str] | None = None,
    ) -> str:
        """Сгенерировать полный вечерний дайджест."""
        if summary is None:
            summary = self.recap.get_today()

        comparison = self.recap.compare_with_yesterday()
        recommendations = self.recommender.generate(summary)

        return self.formatter.format_evening_digest(
            summary=summary,
            comparison=comparison,
            recommendations=recommendations,
            unresolved=unresolved,
            kpi_summary=kpi_summary,
        )

    def generate_short_digest(
        self,
        summary: DaySummary | None = None,
    ) -> str:
        """Краткий дайджест."""
        if summary is None:
            summary = self.recap.get_today()
        return self.formatter.format_short_digest(summary)

    def get_stats(self) -> dict:
        """Статистика."""
        return {
            "days_recorded": self.recap.total_days,
            "rules_count": len(self.recommender._rules),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

evening_digest = EveningDigestEngine()
