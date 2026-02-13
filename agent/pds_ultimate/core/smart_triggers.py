"""
PDS-Ultimate — Smart Triggers Engine (Part 9)
================================================
Проактивная система алертов и триггеров.

Функциональность:
- Триггеры на курсы валют (выше/ниже порога)
- Триггеры на тишину поставщика (нет ответа N дней)
- Триггеры на баланс (ниже порога)
- Триггеры на дедлайны заказов
- Триггеры на ценовые изменения
- Пользовательские триггеры (cron/interval/threshold)
- Цепочки триггеров (если A → запустить B)
- История срабатываний
- Снузинг и мьютинг

Архитектура:
    TriggerManager
    ├── TriggerEvaluator — проверяет условия
    ├── AlertHistory — история срабатываний
    ├── TriggerChain — цепочки триггеров
    └── NotificationRouter — маршрутизация алертов
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable

# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════════


class TriggerType(str, Enum):
    """Типы триггеров."""
    THRESHOLD = "threshold"          # Порог (значение > / < / == X)
    SILENCE = "silence"              # Тишина (нет событий N дней)
    SCHEDULE = "schedule"            # По расписанию (cron/interval)
    PRICE_CHANGE = "price_change"    # Изменение цены
    DEADLINE = "deadline"            # Дедлайн приближается
    BALANCE = "balance"              # Порог баланса
    EXCHANGE_RATE = "exchange_rate"  # Курс валюты
    CUSTOM = "custom"               # Пользовательский


class TriggerStatus(str, Enum):
    """Статус триггера."""
    ACTIVE = "active"
    PAUSED = "paused"
    FIRED = "fired"
    EXPIRED = "expired"
    MUTED = "muted"


class ComparisonOp(str, Enum):
    """Операторы сравнения."""
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "=="
    NEQ = "!="
    CONTAINS = "contains"
    REGEX = "regex"


class AlertSeverity(str, Enum):
    """Серьёзность алерта."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertChannel(str, Enum):
    """Канал уведомления."""
    TELEGRAM = "telegram"
    LOG = "log"
    EMAIL = "email"
    WEBHOOK = "webhook"


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class TriggerCondition:
    """Условие срабатывания."""
    field: str                          # Что проверяем (rate_usd_cny, balance, etc.)
    operator: ComparisonOp              # Оператор сравнения
    value: Any                          # Пороговое значение
    unit: str = ""                      # Единица измерения

    def evaluate(self, current_value: Any) -> bool:
        """Проверить условие."""
        try:
            if self.operator == ComparisonOp.GT:
                return float(current_value) > float(self.value)
            elif self.operator == ComparisonOp.GTE:
                return float(current_value) >= float(self.value)
            elif self.operator == ComparisonOp.LT:
                return float(current_value) < float(self.value)
            elif self.operator == ComparisonOp.LTE:
                return float(current_value) <= float(self.value)
            elif self.operator == ComparisonOp.EQ:
                return str(current_value) == str(self.value)
            elif self.operator == ComparisonOp.NEQ:
                return str(current_value) != str(self.value)
            elif self.operator == ComparisonOp.CONTAINS:
                return str(self.value).lower() in str(current_value).lower()
            elif self.operator == ComparisonOp.REGEX:
                return bool(re.search(str(self.value), str(current_value)))
            return False
        except (ValueError, TypeError):
            return False

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "operator": self.operator.value,
            "value": self.value,
            "unit": self.unit,
        }

    def describe(self) -> str:
        """Человекочитаемое описание."""
        op_map = {
            ">": "больше", ">=": "не менее", "<": "меньше",
            "<=": "не более", "==": "равно", "!=": "не равно",
            "contains": "содержит", "regex": "совпадает с",
        }
        op_name = op_map.get(self.operator.value, self.operator.value)
        unit = f" {self.unit}" if self.unit else ""
        return f"{self.field} {op_name} {self.value}{unit}"


@dataclass
class Alert:
    """Сработавший алерт."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    trigger_id: str = ""
    trigger_name: str = ""
    severity: AlertSeverity = AlertSeverity.INFO
    message: str = ""
    current_value: Any = None
    threshold_value: Any = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    acknowledged: bool = False
    channel: AlertChannel = AlertChannel.TELEGRAM
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "trigger_id": self.trigger_id,
            "trigger_name": self.trigger_name,
            "severity": self.severity.value,
            "message": self.message,
            "current_value": self.current_value,
            "threshold_value": self.threshold_value,
            "timestamp": self.timestamp.isoformat(),
            "acknowledged": self.acknowledged,
        }

    def format_message(self) -> str:
        """Форматированное сообщение."""
        severity_icons = {
            "info": "ℹ️",
            "warning": "⚠️",
            "critical": "🔴",
            "emergency": "🚨",
        }
        icon = severity_icons.get(self.severity.value, "📢")
        parts = [
            f"{icon} **{self.trigger_name}**",
            f"📌 {self.message}",
        ]
        if self.current_value is not None:
            parts.append(f"📊 Текущее: {self.current_value}")
        if self.threshold_value is not None:
            parts.append(f"🎯 Порог: {self.threshold_value}")
        parts.append(f"🕐 {self.timestamp.strftime('%Y-%m-%d %H:%M')}")
        return "\n".join(parts)


@dataclass
class Trigger:
    """Триггер."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    description: str = ""
    trigger_type: TriggerType = TriggerType.THRESHOLD
    status: TriggerStatus = TriggerStatus.ACTIVE
    condition: TriggerCondition | None = None
    severity: AlertSeverity = AlertSeverity.WARNING
    channel: AlertChannel = AlertChannel.TELEGRAM
    owner_id: int = 0
    chat_id: int = 0

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_checked: datetime | None = None
    last_fired: datetime | None = None
    expires_at: datetime | None = None
    cooldown_minutes: int = 60          # Минимум между срабатываниями

    # Repetition
    one_shot: bool = False              # Сработать один раз и деактивировать
    max_fires: int = 0                  # Максимум срабатываний (0 = безлимит)
    fire_count: int = 0

    # Snooze / Mute
    muted_until: datetime | None = None
    snooze_minutes: int = 0

    # Chain
    chain_trigger_ids: list[str] = field(default_factory=list)

    # Tags
    tags: list[str] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        """Активен ли триггер."""
        if self.status != TriggerStatus.ACTIVE:
            return False
        now = datetime.utcnow()
        if self.expires_at and now > self.expires_at:
            return False
        if self.muted_until and now < self.muted_until:
            return False
        if self.max_fires > 0 and self.fire_count >= self.max_fires:
            return False
        return True

    @property
    def is_in_cooldown(self) -> bool:
        """В кулдауне ли."""
        if not self.last_fired:
            return False
        cooldown = timedelta(minutes=self.cooldown_minutes)
        return datetime.utcnow() - self.last_fired < cooldown

    def can_fire(self) -> bool:
        """Может ли сработать."""
        return self.is_active and not self.is_in_cooldown

    def fire(self, current_value: Any = None, message: str = "") -> Alert:
        """Сработать."""
        now = datetime.utcnow()
        self.last_fired = now
        self.fire_count += 1
        self.last_checked = now

        if self.one_shot:
            self.status = TriggerStatus.FIRED

        if self.max_fires > 0 and self.fire_count >= self.max_fires:
            self.status = TriggerStatus.FIRED

        alert = Alert(
            trigger_id=self.id,
            trigger_name=self.name,
            severity=self.severity,
            message=message or f"Триггер «{self.name}» сработал",
            current_value=current_value,
            threshold_value=self.condition.value if self.condition else None,
            timestamp=now,
            channel=self.channel,
        )
        return alert

    def snooze(self, minutes: int = 0) -> None:
        """Снузить триггер."""
        mins = minutes or self.snooze_minutes or 30
        self.muted_until = datetime.utcnow() + timedelta(minutes=mins)

    def mute(self, hours: int = 24) -> None:
        """Замьютить триггер."""
        self.muted_until = datetime.utcnow() + timedelta(hours=hours)
        self.status = TriggerStatus.MUTED

    def unmute(self) -> None:
        """Размьютить."""
        self.muted_until = None
        self.status = TriggerStatus.ACTIVE

    def pause(self) -> None:
        """Приостановить."""
        self.status = TriggerStatus.PAUSED

    def resume(self) -> None:
        """Возобновить."""
        self.status = TriggerStatus.ACTIVE

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "type": self.trigger_type.value,
            "status": self.status.value,
            "condition": self.condition.to_dict() if self.condition else None,
            "severity": self.severity.value,
            "fire_count": self.fire_count,
            "created_at": self.created_at.isoformat(),
            "last_fired": self.last_fired.isoformat() if self.last_fired else None,
            "cooldown_minutes": self.cooldown_minutes,
            "one_shot": self.one_shot,
            "tags": self.tags,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# TRIGGER EVALUATOR
# ═══════════════════════════════════════════════════════════════════════════════


class TriggerEvaluator:
    """Оценщик условий триггеров."""

    def __init__(self):
        self._data_providers: dict[str, Callable] = {}
        self._register_default_providers()

    def _register_default_providers(self) -> None:
        """Встроенные провайдеры данных."""
        # Курсы валют (фиксированные)
        self._data_providers["rate_usd_tmt"] = lambda: 19.5
        self._data_providers["rate_usd_cny"] = lambda: 7.1
        self._data_providers["rate_tmt_usd"] = lambda: 1 / 19.5
        self._data_providers["rate_cny_usd"] = lambda: 1 / 7.1

    def register_provider(self, field: str, provider: Callable) -> None:
        """Зарегистрировать провайдер данных."""
        self._data_providers[field] = provider

    def get_current_value(self, field: str) -> Any:
        """Получить текущее значение поля."""
        provider = self._data_providers.get(field)
        if provider:
            return provider()
        return None

    def evaluate_trigger(
        self,
        trigger: Trigger,
        context: dict | None = None,
    ) -> tuple[bool, Any]:
        """
        Проверить триггер.
        Returns:
            (сработал, текущее_значение)
        """
        if not trigger.can_fire():
            return False, None

        if not trigger.condition:
            return False, None

        # Берём значение из контекста или провайдера
        current_value = None
        if context and trigger.condition.field in context:
            current_value = context[trigger.condition.field]
        else:
            current_value = self.get_current_value(trigger.condition.field)

        if current_value is None:
            return False, None

        trigger.last_checked = datetime.utcnow()
        fired = trigger.condition.evaluate(current_value)
        return fired, current_value

    def evaluate_silence_trigger(
        self,
        trigger: Trigger,
        last_activity: datetime | None,
    ) -> tuple[bool, float]:
        """
        Проверить триггер тишины.
        Returns:
            (сработал, дней_тишины)
        """
        if not trigger.can_fire():
            return False, 0.0

        if not last_activity:
            return True, float("inf")

        silence_days = (datetime.utcnow() -
                        last_activity).total_seconds() / 86400

        if trigger.condition:
            threshold_days = float(trigger.condition.value)
            fired = silence_days >= threshold_days
        else:
            fired = silence_days >= 7  # Default: 7 дней

        trigger.last_checked = datetime.utcnow()
        return fired, round(silence_days, 1)

    def evaluate_deadline_trigger(
        self,
        trigger: Trigger,
        deadline: datetime,
    ) -> tuple[bool, float]:
        """
        Проверить триггер дедлайна.
        Returns:
            (сработал, часов_до_дедлайна)
        """
        if not trigger.can_fire():
            return False, 0.0

        now = datetime.utcnow()
        hours_left = (deadline - now).total_seconds() / 3600

        if trigger.condition:
            threshold_hours = float(trigger.condition.value)
            fired = hours_left <= threshold_hours and hours_left > 0
        else:
            fired = hours_left <= 24 and hours_left > 0

        trigger.last_checked = now
        return fired, round(hours_left, 1)

    @property
    def available_fields(self) -> list[str]:
        """Доступные поля для мониторинга."""
        return list(self._data_providers.keys())


# ═══════════════════════════════════════════════════════════════════════════════
# ALERT HISTORY
# ═══════════════════════════════════════════════════════════════════════════════


class AlertHistory:
    """История алертов."""

    def __init__(self, max_history: int = 1000):
        self._alerts: list[Alert] = []
        self._max_history = max_history

    def add(self, alert: Alert) -> None:
        """Добавить алерт в историю."""
        self._alerts.append(alert)
        if len(self._alerts) > self._max_history:
            self._alerts = self._alerts[-self._max_history:]

    def get_recent(self, count: int = 20) -> list[Alert]:
        """Получить последние алерты."""
        return list(reversed(self._alerts[-count:]))

    def get_by_trigger(self, trigger_id: str) -> list[Alert]:
        """Алерты конкретного триггера."""
        return [a for a in self._alerts if a.trigger_id == trigger_id]

    def get_unacknowledged(self) -> list[Alert]:
        """Неподтверждённые алерты."""
        return [a for a in self._alerts if not a.acknowledged]

    def acknowledge(self, alert_id: str) -> bool:
        """Подтвердить алерт."""
        for a in self._alerts:
            if a.id == alert_id:
                a.acknowledged = True
                return True
        return False

    def acknowledge_all(self) -> int:
        """Подтвердить все алерты."""
        count = 0
        for a in self._alerts:
            if not a.acknowledged:
                a.acknowledged = True
                count += 1
        return count

    def get_by_severity(self, severity: AlertSeverity) -> list[Alert]:
        """Алерты по уровню серьёзности."""
        return [a for a in self._alerts if a.severity == severity]

    def get_stats(self) -> dict:
        """Статистика алертов."""
        by_severity = {}
        for a in self._alerts:
            by_severity[a.severity.value] = by_severity.get(
                a.severity.value, 0) + 1

        by_trigger = {}
        for a in self._alerts:
            by_trigger[a.trigger_name] = by_trigger.get(a.trigger_name, 0) + 1

        return {
            "total": len(self._alerts),
            "unacknowledged": len(self.get_unacknowledged()),
            "by_severity": by_severity,
            "by_trigger": by_trigger,
        }

    def clear(self) -> int:
        """Очистить историю."""
        count = len(self._alerts)
        self._alerts.clear()
        return count

    @property
    def total(self) -> int:
        return len(self._alerts)


# ═══════════════════════════════════════════════════════════════════════════════
# NOTIFICATION ROUTER
# ═══════════════════════════════════════════════════════════════════════════════


class NotificationRouter:
    """Маршрутизатор уведомлений."""

    def __init__(self):
        self._handlers: dict[AlertChannel, list[Callable]] = {}
        self._default_channel = AlertChannel.TELEGRAM
        self._severity_channels: dict[AlertSeverity, list[AlertChannel]] = {
            AlertSeverity.INFO: [AlertChannel.LOG],
            AlertSeverity.WARNING: [AlertChannel.TELEGRAM],
            AlertSeverity.CRITICAL: [AlertChannel.TELEGRAM, AlertChannel.LOG],
            AlertSeverity.EMERGENCY: [AlertChannel.TELEGRAM, AlertChannel.LOG,
                                      AlertChannel.EMAIL],
        }

    def register_handler(
        self,
        channel: AlertChannel,
        handler: Callable,
    ) -> None:
        """Зарегистрировать обработчик канала."""
        if channel not in self._handlers:
            self._handlers[channel] = []
        self._handlers[channel].append(handler)

    def get_channels_for_alert(self, alert: Alert) -> list[AlertChannel]:
        """Определить каналы для алерта."""
        channels = self._severity_channels.get(
            alert.severity,
            [self._default_channel],
        )
        if alert.channel not in channels:
            channels.append(alert.channel)
        return channels

    async def route(self, alert: Alert) -> list[str]:
        """Маршрутизировать алерт по каналам."""
        channels = self.get_channels_for_alert(alert)
        results = []

        for channel in channels:
            handlers = self._handlers.get(channel, [])
            for handler in handlers:
                try:
                    result = handler(alert)
                    if hasattr(result, "__await__"):
                        result = await result
                    results.append(f"{channel.value}: OK")
                except Exception as e:
                    results.append(f"{channel.value}: ERROR ({e})")

        if not results:
            results.append("log: " + alert.format_message())

        return results

    def set_severity_channels(
        self,
        severity: AlertSeverity,
        channels: list[AlertChannel],
    ) -> None:
        """Настроить каналы для уровня серьёзности."""
        self._severity_channels[severity] = channels


# ═══════════════════════════════════════════════════════════════════════════════
# TRIGGER CHAIN
# ═══════════════════════════════════════════════════════════════════════════════


class TriggerChain:
    """Цепочка триггеров (если A сработал → активировать B)."""

    def __init__(self):
        self._chains: dict[str, list[str]] = {}  # trigger_id -> [trigger_ids]

    def add_chain(self, source_id: str, target_id: str) -> None:
        """Добавить связь."""
        if source_id not in self._chains:
            self._chains[source_id] = []
        if target_id not in self._chains[source_id]:
            self._chains[source_id].append(target_id)

    def remove_chain(self, source_id: str, target_id: str) -> bool:
        """Удалить связь."""
        if source_id in self._chains:
            if target_id in self._chains[source_id]:
                self._chains[source_id].remove(target_id)
                return True
        return False

    def get_chain_targets(self, source_id: str) -> list[str]:
        """Получить цепочку."""
        return self._chains.get(source_id, [])

    def has_chain(self, source_id: str) -> bool:
        """Есть ли цепочка."""
        return source_id in self._chains and len(self._chains[source_id]) > 0

    def get_all_chains(self) -> dict[str, list[str]]:
        """Все цепочки."""
        return dict(self._chains)

    def detect_cycle(self, source_id: str, target_id: str) -> bool:
        """Определить цикл (A→B→A)."""
        visited = set()
        queue = [target_id]
        while queue:
            current = queue.pop(0)
            if current == source_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            queue.extend(self._chains.get(current, []))
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# TRIGGER TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════════


class TriggerTemplates:
    """Шаблоны для быстрого создания триггеров."""

    @staticmethod
    def exchange_rate_alert(
        currency_pair: str = "usd_cny",
        operator: str = ">",
        threshold: float = 7.2,
        name: str = "",
    ) -> Trigger:
        """Триггер на курс валют."""
        op = ComparisonOp(operator)
        return Trigger(
            name=name or f"Курс {currency_pair.upper()} {operator} {threshold}",
            description=f"Алерт когда курс {currency_pair} {operator} {threshold}",
            trigger_type=TriggerType.EXCHANGE_RATE,
            condition=TriggerCondition(
                field=f"rate_{currency_pair}",
                operator=op,
                value=threshold,
                unit=currency_pair.split("_")[-1].upper(),
            ),
            severity=AlertSeverity.WARNING,
            cooldown_minutes=60,
        )

    @staticmethod
    def balance_alert(
        threshold: float = 1000.0,
        currency: str = "USD",
        name: str = "",
    ) -> Trigger:
        """Триггер на баланс."""
        return Trigger(
            name=name or f"Баланс ниже {threshold} {currency}",
            description=f"Алерт когда баланс падает ниже {threshold} {currency}",
            trigger_type=TriggerType.BALANCE,
            condition=TriggerCondition(
                field="balance",
                operator=ComparisonOp.LT,
                value=threshold,
                unit=currency,
            ),
            severity=AlertSeverity.CRITICAL,
            cooldown_minutes=120,
        )

    @staticmethod
    def supplier_silence_alert(
        supplier_name: str,
        days: int = 7,
        name: str = "",
    ) -> Trigger:
        """Триггер на тишину поставщика."""
        return Trigger(
            name=name or f"Тишина от {supplier_name} ({days}+ дней)",
            description=f"Алерт если {supplier_name} молчит {days}+ дней",
            trigger_type=TriggerType.SILENCE,
            condition=TriggerCondition(
                field=f"supplier_{supplier_name.lower().replace(' ', '_')}",
                operator=ComparisonOp.GTE,
                value=days,
                unit="дней",
            ),
            severity=AlertSeverity.WARNING,
            cooldown_minutes=24 * 60,
        )

    @staticmethod
    def deadline_alert(
        hours_before: int = 24,
        name: str = "",
    ) -> Trigger:
        """Триггер на приближающийся дедлайн."""
        return Trigger(
            name=name or f"Дедлайн через {hours_before}ч",
            description=f"Алерт за {hours_before} часов до дедлайна",
            trigger_type=TriggerType.DEADLINE,
            condition=TriggerCondition(
                field="hours_to_deadline",
                operator=ComparisonOp.LTE,
                value=hours_before,
                unit="часов",
            ),
            severity=AlertSeverity.WARNING,
            cooldown_minutes=60,
        )

    @staticmethod
    def price_change_alert(
        item_name: str,
        change_percent: float = 10.0,
        name: str = "",
    ) -> Trigger:
        """Триггер на изменение цены."""
        return Trigger(
            name=name or f"Цена {item_name} изменилась на {change_percent}%+",
            description=f"Алерт при изменении цены {item_name} на {change_percent}%",
            trigger_type=TriggerType.PRICE_CHANGE,
            condition=TriggerCondition(
                field=f"price_{item_name.lower().replace(' ', '_')}",
                operator=ComparisonOp.GTE,
                value=change_percent,
                unit="%",
            ),
            severity=AlertSeverity.INFO,
            cooldown_minutes=60,
        )

    @classmethod
    def get_templates(cls) -> dict[str, dict]:
        """Список доступных шаблонов."""
        return {
            "exchange_rate": {
                "name": "Курс валют",
                "description": "Алерт при изменении курса валют",
                "params": ["currency_pair", "operator", "threshold"],
            },
            "balance": {
                "name": "Баланс",
                "description": "Алерт при низком балансе",
                "params": ["threshold", "currency"],
            },
            "supplier_silence": {
                "name": "Тишина поставщика",
                "description": "Алерт если поставщик молчит",
                "params": ["supplier_name", "days"],
            },
            "deadline": {
                "name": "Дедлайн",
                "description": "Алерт перед дедлайном",
                "params": ["hours_before"],
            },
            "price_change": {
                "name": "Изменение цены",
                "description": "Алерт при изменении цены",
                "params": ["item_name", "change_percent"],
            },
        }


# ═══════════════════════════════════════════════════════════════════════════════
# TRIGGER MANAGER
# ═══════════════════════════════════════════════════════════════════════════════


class TriggerManager:
    """
    Центральный менеджер триггеров.

    Управляет созданием, обновлением, проверкой и удалением триггеров.
    """

    def __init__(self, max_triggers: int = 500):
        self._triggers: dict[str, Trigger] = {}
        self._max_triggers = max_triggers
        self.evaluator = TriggerEvaluator()
        self.history = AlertHistory()
        self.router = NotificationRouter()
        self.chains = TriggerChain()
        self.templates = TriggerTemplates()

    # ── CRUD ──────────────────────────────────────────────────────────────

    def create_trigger(
        self,
        name: str,
        trigger_type: TriggerType | str,
        condition: TriggerCondition | None = None,
        severity: AlertSeverity | str = AlertSeverity.WARNING,
        owner_id: int = 0,
        chat_id: int = 0,
        cooldown_minutes: int = 60,
        one_shot: bool = False,
        max_fires: int = 0,
        tags: list[str] | None = None,
        description: str = "",
        expires_hours: int = 0,
    ) -> Trigger:
        """Создать новый триггер."""
        if len(self._triggers) >= self._max_triggers:
            # Удалить expired
            self._cleanup_expired()
            if len(self._triggers) >= self._max_triggers:
                raise ValueError(
                    f"Достигнут лимит триггеров ({self._max_triggers})"
                )

        # Normalize enums
        if isinstance(trigger_type, str):
            trigger_type = TriggerType(trigger_type.lower())
        if isinstance(severity, str):
            severity = AlertSeverity(severity.lower())

        trigger = Trigger(
            name=name,
            description=description,
            trigger_type=trigger_type,
            condition=condition,
            severity=severity,
            owner_id=owner_id,
            chat_id=chat_id,
            cooldown_minutes=cooldown_minutes,
            one_shot=one_shot,
            max_fires=max_fires,
            tags=tags or [],
        )

        if expires_hours > 0:
            trigger.expires_at = datetime.utcnow() + timedelta(hours=expires_hours)

        self._triggers[trigger.id] = trigger
        return trigger

    def create_from_template(
        self,
        template_name: str,
        owner_id: int = 0,
        **kwargs,
    ) -> Trigger:
        """Создать триггер из шаблона."""
        factory_map = {
            "exchange_rate": self.templates.exchange_rate_alert,
            "balance": self.templates.balance_alert,
            "supplier_silence": self.templates.supplier_silence_alert,
            "deadline": self.templates.deadline_alert,
            "price_change": self.templates.price_change_alert,
        }

        factory = factory_map.get(template_name)
        if not factory:
            raise ValueError(
                f"Шаблон «{template_name}» не найден. "
                f"Доступные: {', '.join(factory_map.keys())}"
            )

        trigger = factory(**kwargs)
        trigger.owner_id = owner_id
        self._triggers[trigger.id] = trigger
        return trigger

    def get_trigger(self, trigger_id: str) -> Trigger | None:
        """Получить триггер по ID."""
        return self._triggers.get(trigger_id)

    def get_by_name(self, name: str) -> Trigger | None:
        """Найти триггер по имени."""
        for t in self._triggers.values():
            if t.name.lower() == name.lower():
                return t
        return None

    def get_triggers(
        self,
        owner_id: int | None = None,
        status: TriggerStatus | None = None,
        trigger_type: TriggerType | None = None,
        tags: list[str] | None = None,
    ) -> list[Trigger]:
        """Получить триггеры с фильтрацией."""
        result = list(self._triggers.values())
        if owner_id is not None:
            result = [t for t in result if t.owner_id == owner_id]
        if status is not None:
            result = [t for t in result if t.status == status]
        if trigger_type is not None:
            result = [t for t in result if t.trigger_type == trigger_type]
        if tags:
            result = [
                t for t in result
                if any(tag in t.tags for tag in tags)
            ]
        return result

    def get_active_triggers(self) -> list[Trigger]:
        """Все активные триггеры."""
        return [t for t in self._triggers.values() if t.is_active]

    def delete_trigger(self, trigger_id: str) -> bool:
        """Удалить триггер."""
        if trigger_id in self._triggers:
            del self._triggers[trigger_id]
            return True
        return False

    def pause_trigger(self, trigger_id: str) -> bool:
        """Приостановить триггер."""
        t = self._triggers.get(trigger_id)
        if t:
            t.pause()
            return True
        return False

    def resume_trigger(self, trigger_id: str) -> bool:
        """Возобновить триггер."""
        t = self._triggers.get(trigger_id)
        if t:
            t.resume()
            return True
        return False

    def snooze_trigger(self, trigger_id: str, minutes: int = 30) -> bool:
        """Снузить триггер."""
        t = self._triggers.get(trigger_id)
        if t:
            t.snooze(minutes)
            return True
        return False

    # ── Evaluation ────────────────────────────────────────────────────────

    def check_trigger(
        self,
        trigger_id: str,
        context: dict | None = None,
    ) -> Alert | None:
        """Проверить конкретный триггер."""
        trigger = self._triggers.get(trigger_id)
        if not trigger or not trigger.can_fire():
            return None

        fired, current_value = self.evaluator.evaluate_trigger(
            trigger, context
        )

        if fired:
            message = (
                f"{trigger.condition.describe()}\n"
                f"Текущее значение: {current_value}"
            ) if trigger.condition else f"Триггер «{trigger.name}» сработал"

            alert = trigger.fire(current_value, message)
            self.history.add(alert)
            return alert

        return None

    def check_all(
        self,
        context: dict | None = None,
    ) -> list[Alert]:
        """Проверить все активные триггеры."""
        alerts = []
        for trigger in self.get_active_triggers():
            alert = self.check_trigger(trigger.id, context)
            if alert:
                alerts.append(alert)
                # Проверяем цепочки
                chain_targets = self.chains.get_chain_targets(trigger.id)
                for target_id in chain_targets:
                    chain_alert = self.check_trigger(target_id, context)
                    if chain_alert:
                        alerts.append(chain_alert)

        return alerts

    async def check_and_notify(
        self,
        context: dict | None = None,
    ) -> list[Alert]:
        """Проверить и отправить уведомления."""
        alerts = self.check_all(context)
        for alert in alerts:
            await self.router.route(alert)
        return alerts

    # ── Cleanup ───────────────────────────────────────────────────────────

    def _cleanup_expired(self) -> int:
        """Удалить истекшие триггеры."""
        now = datetime.utcnow()
        expired = [
            tid for tid, t in self._triggers.items()
            if (t.expires_at and now > t.expires_at)
            or t.status == TriggerStatus.EXPIRED
        ]
        for tid in expired:
            del self._triggers[tid]
        return len(expired)

    # ── Stats ─────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Статистика триггеров."""
        triggers = list(self._triggers.values())
        by_type = {}
        by_status = {}
        total_fires = 0

        for t in triggers:
            by_type[t.trigger_type.value] = by_type.get(
                t.trigger_type.value, 0) + 1
            by_status[t.status.value] = by_status.get(t.status.value, 0) + 1
            total_fires += t.fire_count

        return {
            "total": len(triggers),
            "active": len(self.get_active_triggers()),
            "by_type": by_type,
            "by_status": by_status,
            "total_fires": total_fires,
            "alerts": self.history.get_stats(),
            "chains": len(self.chains.get_all_chains()),
        }

    def format_triggers_list(self) -> str:
        """Форматированный список триггеров."""
        triggers = sorted(
            self._triggers.values(),
            key=lambda t: (t.status != TriggerStatus.ACTIVE, -t.fire_count),
        )

        if not triggers:
            return "📋 Триггеров нет."

        lines = [f"🔔 Триггеры ({len(triggers)}):"]
        status_icons = {
            "active": "🟢", "paused": "⏸️", "fired": "✅",
            "expired": "⏰", "muted": "🔇",
        }

        for t in triggers:
            icon = status_icons.get(t.status.value, "❓")
            line = f"  {icon} {t.name}"
            if t.condition:
                line += f" [{t.condition.describe()}]"
            if t.fire_count > 0:
                line += f" (×{t.fire_count})"
            lines.append(line)

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

trigger_manager = TriggerManager()
