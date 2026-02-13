"""
PDS-Ultimate — Analytics Dashboard Engine (Part 9)
=====================================================
Бизнес-аналитика, KPI, графики, тренды.

Функциональность:
- Revenue trends (доход/расход/прибыль за период)
- Order analytics (статусы, средний чек, воронка)
- Profit margins по товарам / поставщикам
- KPI tracking (выполнение целей)
- Supplier analytics (рейтинг, объём, сроки)
- Custom metrics (пользовательские метрики)
- Period comparison (сравнение периодов)
- Экспорт в текст / JSON / CSV

Архитектура:
    AnalyticsDashboard
    ├── MetricsCollector — сбор метрик из модулей
    ├── KPITracker — отслеживание KPI / целей
    ├── TrendAnalyzer — анализ трендов
    ├── PeriodComparator — сравнение периодов
    └── ReportFormatter — форматирование отчётов
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════════


class MetricType(str, Enum):
    """Типы метрик."""
    REVENUE = "revenue"
    EXPENSE = "expense"
    PROFIT = "profit"
    ORDER_COUNT = "order_count"
    AVG_CHECK = "avg_check"
    CONVERSION = "conversion"
    RESPONSE_TIME = "response_time"
    CUSTOM = "custom"


class Period(str, Enum):
    """Периоды для аналитики."""
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


class TrendDirection(str, Enum):
    """Направление тренда."""
    UP = "up"
    DOWN = "down"
    STABLE = "stable"
    VOLATILE = "volatile"


class KPIStatus(str, Enum):
    """Статус KPI."""
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    BEHIND = "behind"
    ACHIEVED = "achieved"
    EXCEEDED = "exceeded"


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class MetricPoint:
    """Точка метрики (значение в момент времени)."""
    timestamp: datetime
    value: float
    label: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "value": self.value,
            "label": self.label,
        }


@dataclass
class MetricSeries:
    """Серия метрик (временной ряд)."""
    name: str
    metric_type: MetricType
    points: list[MetricPoint] = field(default_factory=list)
    unit: str = ""

    def add_point(self, value: float, timestamp: datetime | None = None,
                  label: str = "", metadata: dict | None = None) -> None:
        """Добавить точку."""
        self.points.append(MetricPoint(
            timestamp=timestamp or datetime.utcnow(),
            value=value,
            label=label,
            metadata=metadata or {},
        ))

    @property
    def values(self) -> list[float]:
        """Все значения."""
        return [p.value for p in self.points]

    @property
    def total(self) -> float:
        """Сумма."""
        return sum(self.values)

    @property
    def average(self) -> float:
        """Среднее."""
        vals = self.values
        return sum(vals) / len(vals) if vals else 0.0

    @property
    def min_value(self) -> float:
        vals = self.values
        return min(vals) if vals else 0.0

    @property
    def max_value(self) -> float:
        vals = self.values
        return max(vals) if vals else 0.0

    @property
    def median(self) -> float:
        vals = self.values
        return statistics.median(vals) if vals else 0.0

    @property
    def std_dev(self) -> float:
        vals = self.values
        return statistics.stdev(vals) if len(vals) >= 2 else 0.0

    @property
    def count(self) -> int:
        return len(self.points)

    def get_for_period(
        self,
        start: datetime,
        end: datetime,
    ) -> list[MetricPoint]:
        """Точки за период."""
        return [
            p for p in self.points
            if start <= p.timestamp <= end
        ]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.metric_type.value,
            "count": self.count,
            "total": round(self.total, 2),
            "average": round(self.average, 2),
            "min": round(self.min_value, 2),
            "max": round(self.max_value, 2),
            "unit": self.unit,
        }


@dataclass
class KPI:
    """Key Performance Indicator."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    description: str = ""
    target_value: float = 0.0
    current_value: float = 0.0
    unit: str = ""
    period: Period = Period.MONTH
    metric_type: MetricType = MetricType.CUSTOM
    created_at: datetime = field(default_factory=datetime.utcnow)
    deadline: datetime | None = None
    owner_id: int = 0
    tags: list[str] = field(default_factory=list)

    @property
    def progress(self) -> float:
        """Прогресс (0.0 - 1.0+)."""
        if self.target_value == 0:
            return 1.0 if self.current_value > 0 else 0.0
        return self.current_value / self.target_value

    @property
    def progress_percent(self) -> float:
        """Прогресс в процентах."""
        return round(self.progress * 100, 1)

    @property
    def status(self) -> KPIStatus:
        """Статус KPI."""
        p = self.progress
        if p >= 1.1:
            return KPIStatus.EXCEEDED
        if p >= 1.0:
            return KPIStatus.ACHIEVED
        if p >= 0.7:
            return KPIStatus.ON_TRACK
        if p >= 0.4:
            return KPIStatus.AT_RISK
        return KPIStatus.BEHIND

    @property
    def remaining(self) -> float:
        """Осталось до цели."""
        return max(0, self.target_value - self.current_value)

    def update(self, value: float, cumulative: bool = True) -> None:
        """Обновить значение."""
        if cumulative:
            self.current_value += value
        else:
            self.current_value = value

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "target": self.target_value,
            "current": self.current_value,
            "progress": self.progress_percent,
            "status": self.status.value,
            "unit": self.unit,
            "period": self.period.value,
        }


@dataclass
class TrendResult:
    """Результат анализа тренда."""
    direction: TrendDirection
    change_percent: float
    average: float
    slope: float
    confidence: float
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "direction": self.direction.value,
            "change_percent": round(self.change_percent, 1),
            "average": round(self.average, 2),
            "slope": round(self.slope, 4),
            "confidence": round(self.confidence, 2),
            "description": self.description,
        }


@dataclass
class PeriodComparison:
    """Сравнение двух периодов."""
    period_1_label: str
    period_2_label: str
    metric_name: str
    value_1: float
    value_2: float
    change: float
    change_percent: float
    improved: bool

    def to_dict(self) -> dict:
        return {
            "period_1": self.period_1_label,
            "period_2": self.period_2_label,
            "metric": self.metric_name,
            "value_1": round(self.value_1, 2),
            "value_2": round(self.value_2, 2),
            "change": round(self.change, 2),
            "change_percent": round(self.change_percent, 1),
            "improved": self.improved,
        }

    def format_text(self) -> str:
        """Текстовое представление."""
        arrow = "📈" if self.improved else "📉"
        sign = "+" if self.change >= 0 else ""
        return (
            f"{arrow} {self.metric_name}: "
            f"{self.value_1:.2f} → {self.value_2:.2f} "
            f"({sign}{self.change_percent:.1f}%)"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# METRICS COLLECTOR
# ═══════════════════════════════════════════════════════════════════════════════


class MetricsCollector:
    """Сборщик метрик из различных модулей."""

    def __init__(self):
        self._series: dict[str, MetricSeries] = {}

    def get_or_create_series(
        self,
        name: str,
        metric_type: MetricType = MetricType.CUSTOM,
        unit: str = "",
    ) -> MetricSeries:
        """Получить или создать серию."""
        if name not in self._series:
            self._series[name] = MetricSeries(
                name=name,
                metric_type=metric_type,
                unit=unit,
            )
        return self._series[name]

    def record(
        self,
        series_name: str,
        value: float,
        timestamp: datetime | None = None,
        label: str = "",
        metric_type: MetricType = MetricType.CUSTOM,
        unit: str = "",
        metadata: dict | None = None,
    ) -> None:
        """Записать значение."""
        series = self.get_or_create_series(series_name, metric_type, unit)
        series.add_point(value, timestamp, label, metadata)

    def get_series(self, name: str) -> MetricSeries | None:
        """Получить серию по имени."""
        return self._series.get(name)

    def list_series(self) -> list[str]:
        """Список всех серий."""
        return list(self._series.keys())

    def get_all_series(self) -> dict[str, MetricSeries]:
        """Все серии."""
        return dict(self._series)

    def get_summary(self) -> dict[str, dict]:
        """Сводка по всем сериям."""
        return {
            name: series.to_dict()
            for name, series in self._series.items()
        }

    def clear_series(self, name: str) -> bool:
        """Очистить серию."""
        if name in self._series:
            self._series[name].points.clear()
            return True
        return False

    def delete_series(self, name: str) -> bool:
        """Удалить серию."""
        if name in self._series:
            del self._series[name]
            return True
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# KPI TRACKER
# ═══════════════════════════════════════════════════════════════════════════════


class KPITracker:
    """Отслеживание KPI и бизнес-целей."""

    def __init__(self, max_kpis: int = 100):
        self._kpis: dict[str, KPI] = {}
        self._max_kpis = max_kpis

    def create_kpi(
        self,
        name: str,
        target_value: float,
        unit: str = "",
        period: Period | str = Period.MONTH,
        metric_type: MetricType | str = MetricType.CUSTOM,
        description: str = "",
        owner_id: int = 0,
        deadline: datetime | None = None,
        tags: list[str] | None = None,
    ) -> KPI:
        """Создать KPI."""
        if len(self._kpis) >= self._max_kpis:
            raise ValueError(f"Достигнут лимит KPI ({self._max_kpis})")

        if isinstance(period, str):
            period = Period(period.lower())
        if isinstance(metric_type, str):
            metric_type = MetricType(metric_type.lower())

        kpi = KPI(
            name=name,
            description=description,
            target_value=target_value,
            unit=unit,
            period=period,
            metric_type=metric_type,
            owner_id=owner_id,
            deadline=deadline,
            tags=tags or [],
        )
        self._kpis[kpi.id] = kpi
        return kpi

    def get_kpi(self, kpi_id: str) -> KPI | None:
        """Получить KPI по ID."""
        return self._kpis.get(kpi_id)

    def find_kpi(self, name: str) -> KPI | None:
        """Найти KPI по имени."""
        for kpi in self._kpis.values():
            if kpi.name.lower() == name.lower():
                return kpi
        return None

    def update_kpi(
        self,
        kpi_id: str,
        value: float,
        cumulative: bool = True,
    ) -> KPI | None:
        """Обновить значение KPI."""
        kpi = self._kpis.get(kpi_id)
        if kpi:
            kpi.update(value, cumulative)
        return kpi

    def delete_kpi(self, kpi_id: str) -> bool:
        """Удалить KPI."""
        if kpi_id in self._kpis:
            del self._kpis[kpi_id]
            return True
        return False

    def get_all_kpis(
        self,
        owner_id: int | None = None,
        status: KPIStatus | None = None,
    ) -> list[KPI]:
        """Все KPI с фильтрацией."""
        result = list(self._kpis.values())
        if owner_id is not None:
            result = [k for k in result if k.owner_id == owner_id]
        if status is not None:
            result = [k for k in result if k.status == status]
        return result

    def get_at_risk(self) -> list[KPI]:
        """KPI под риском."""
        return [
            k for k in self._kpis.values()
            if k.status in (KPIStatus.AT_RISK, KPIStatus.BEHIND)
        ]

    def get_achieved(self) -> list[KPI]:
        """Достигнутые KPI."""
        return [
            k for k in self._kpis.values()
            if k.status in (KPIStatus.ACHIEVED, KPIStatus.EXCEEDED)
        ]

    def format_kpi_board(self) -> str:
        """Форматированная доска KPI."""
        kpis = sorted(
            self._kpis.values(),
            key=lambda k: -k.progress,
        )

        if not kpis:
            return "📊 KPI не определены."

        status_icons = {
            "exceeded": "🏆",
            "achieved": "✅",
            "on_track": "🟢",
            "at_risk": "🟡",
            "behind": "🔴",
        }

        lines = [f"📊 KPI Dashboard ({len(kpis)}):"]
        for kpi in kpis:
            icon = status_icons.get(kpi.status.value, "❓")
            bar = self._progress_bar(kpi.progress)
            lines.append(
                f"  {icon} {kpi.name}: {kpi.current_value:.0f}/{kpi.target_value:.0f}"
                f" {kpi.unit} [{bar}] {kpi.progress_percent}%"
            )

        return "\n".join(lines)

    @staticmethod
    def _progress_bar(progress: float, width: int = 10) -> str:
        """Прогресс-бар."""
        filled = min(int(progress * width), width)
        return "█" * filled + "░" * (width - filled)

    def get_stats(self) -> dict:
        """Статистика KPI."""
        kpis = list(self._kpis.values())
        by_status = {}
        for k in kpis:
            by_status[k.status.value] = by_status.get(k.status.value, 0) + 1

        return {
            "total": len(kpis),
            "by_status": by_status,
            "at_risk": len(self.get_at_risk()),
            "achieved": len(self.get_achieved()),
            "average_progress": (
                sum(k.progress for k in kpis) / len(kpis) * 100
                if kpis else 0
            ),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# TREND ANALYZER
# ═══════════════════════════════════════════════════════════════════════════════


class TrendAnalyzer:
    """Анализатор трендов."""

    def analyze(self, series: MetricSeries) -> TrendResult:
        """Анализировать тренд серии."""
        values = series.values
        if len(values) < 2:
            return TrendResult(
                direction=TrendDirection.STABLE,
                change_percent=0.0,
                average=series.average,
                slope=0.0,
                confidence=0.0,
                description="Недостаточно данных для анализа тренда",
            )

        # Простая линейная регрессия
        n = len(values)
        x = list(range(n))
        x_mean = sum(x) / n
        y_mean = sum(values) / n

        numerator = sum((x[i] - x_mean) * (values[i] - y_mean)
                        for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        slope = numerator / denominator if denominator != 0 else 0

        # R² для confidence
        y_pred = [y_mean + slope * (xi - x_mean) for xi in x]
        ss_res = sum((values[i] - y_pred[i]) ** 2 for i in range(n))
        ss_tot = sum((values[i] - y_mean) ** 2 for i in range(n))
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        # Direction
        first_half = values[: n // 2]
        second_half = values[n // 2:]
        avg_first = sum(first_half) / len(first_half) if first_half else 0
        avg_second = sum(second_half) / len(second_half) if second_half else 0

        if avg_first == 0:
            change_pct = 0.0
        else:
            change_pct = ((avg_second - avg_first) / abs(avg_first)) * 100

        # Volatility check
        cv = series.std_dev / abs(y_mean) if y_mean != 0 else 0

        if cv > 0.5:
            direction = TrendDirection.VOLATILE
        elif abs(change_pct) < 5:
            direction = TrendDirection.STABLE
        elif change_pct > 0:
            direction = TrendDirection.UP
        else:
            direction = TrendDirection.DOWN

        dir_desc = {
            TrendDirection.UP: "📈 Рост",
            TrendDirection.DOWN: "📉 Падение",
            TrendDirection.STABLE: "➡️ Стабильно",
            TrendDirection.VOLATILE: "📊 Волатильно",
        }

        return TrendResult(
            direction=direction,
            change_percent=round(change_pct, 1),
            average=round(y_mean, 2),
            slope=round(slope, 4),
            confidence=round(max(0, r_squared), 2),
            description=f"{dir_desc[direction]} ({change_pct:+.1f}%)",
        )

    def compare_periods(
        self,
        series: MetricSeries,
        period_1: tuple[datetime, datetime],
        period_2: tuple[datetime, datetime],
    ) -> PeriodComparison:
        """Сравнить два периода."""
        points_1 = series.get_for_period(period_1[0], period_1[1])
        points_2 = series.get_for_period(period_2[0], period_2[1])

        val_1 = sum(p.value for p in points_1) if points_1 else 0.0
        val_2 = sum(p.value for p in points_2) if points_2 else 0.0

        change = val_2 - val_1
        change_pct = (change / abs(val_1) * 100) if val_1 != 0 else 0.0

        # Для profit-like metrics, up is good
        improved = change > 0

        return PeriodComparison(
            period_1_label=f"{period_1[0].strftime('%d.%m')}–{period_1[1].strftime('%d.%m')}",
            period_2_label=f"{period_2[0].strftime('%d.%m')}–{period_2[1].strftime('%d.%m')}",
            metric_name=series.name,
            value_1=val_1,
            value_2=val_2,
            change=change,
            change_percent=change_pct,
            improved=improved,
        )

    def forecast_simple(
        self,
        series: MetricSeries,
        periods_ahead: int = 3,
    ) -> list[float]:
        """Простой прогноз на основе тренда."""
        values = series.values
        if len(values) < 2:
            return [series.average] * periods_ahead

        trend = self.analyze(series)
        last_value = values[-1]

        forecasted = []
        for i in range(1, periods_ahead + 1):
            forecasted.append(round(last_value + trend.slope * i, 2))

        return forecasted


# ═══════════════════════════════════════════════════════════════════════════════
# REPORT FORMATTER
# ═══════════════════════════════════════════════════════════════════════════════


class ReportFormatter:
    """Форматировщик отчётов."""

    def format_dashboard(
        self,
        metrics: dict[str, MetricSeries],
        kpis: list[KPI],
        trends: dict[str, TrendResult] | None = None,
    ) -> str:
        """Форматировать дашборд."""
        lines = ["═" * 50]
        lines.append("📊 БИЗНЕС ДАШБОРД")
        lines.append("═" * 50)

        # Метрики
        if metrics:
            lines.append("\n📈 Ключевые метрики:")
            for name, series in metrics.items():
                trend_str = ""
                if trends and name in trends:
                    t = trends[name]
                    trend_str = f" {t.description}"
                lines.append(
                    f"  • {name}: {series.total:.2f} {series.unit}"
                    f" (avg: {series.average:.2f}){trend_str}"
                )

        # KPIs
        if kpis:
            lines.append("\n🎯 KPI:")
            status_icons = {
                "exceeded": "🏆", "achieved": "✅",
                "on_track": "🟢", "at_risk": "🟡", "behind": "🔴",
            }
            for kpi in kpis:
                icon = status_icons.get(kpi.status.value, "❓")
                lines.append(
                    f"  {icon} {kpi.name}: {kpi.progress_percent}% "
                    f"({kpi.current_value:.0f}/{kpi.target_value:.0f} {kpi.unit})"
                )

        lines.append("\n" + "═" * 50)
        return "\n".join(lines)

    def format_trend_report(
        self,
        trends: dict[str, TrendResult],
    ) -> str:
        """Отчёт о трендах."""
        lines = ["📊 Анализ трендов:"]

        for name, trend in trends.items():
            dir_icon = {
                "up": "📈", "down": "📉",
                "stable": "➡️", "volatile": "📊",
            }
            icon = dir_icon.get(trend.direction.value, "❓")
            lines.append(
                f"  {icon} {name}: {trend.change_percent:+.1f}% "
                f"(avg: {trend.average:.2f}, confidence: {trend.confidence:.0%})"
            )

        return "\n".join(lines)

    def format_comparison(
        self,
        comparisons: list[PeriodComparison],
    ) -> str:
        """Отчёт сравнения периодов."""
        if not comparisons:
            return "📊 Нет данных для сравнения."

        lines = [
            f"📊 Сравнение: {comparisons[0].period_1_label} vs "
            f"{comparisons[0].period_2_label}"
        ]
        for c in comparisons:
            lines.append(f"  {c.format_text()}")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYTICS DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════


class AnalyticsDashboard:
    """
    Центральный аналитический дашборд.

    Объединяет метрики, KPI, тренды и отчёты.
    """

    def __init__(self):
        self.collector = MetricsCollector()
        self.kpi_tracker = KPITracker()
        self.trend_analyzer = TrendAnalyzer()
        self.formatter = ReportFormatter()

    # ── Metrics ───────────────────────────────────────────────────────────

    def record_metric(
        self,
        name: str,
        value: float,
        metric_type: MetricType | str = MetricType.CUSTOM,
        unit: str = "",
        timestamp: datetime | None = None,
        label: str = "",
    ) -> None:
        """Записать метрику."""
        if isinstance(metric_type, str):
            metric_type = MetricType(metric_type.lower())
        self.collector.record(
            name, value, timestamp, label, metric_type, unit,
        )

    def record_revenue(self, amount: float, label: str = "") -> None:
        """Записать доход."""
        self.collector.record(
            "revenue", amount, label=label,
            metric_type=MetricType.REVENUE, unit="USD",
        )

    def record_expense(self, amount: float, label: str = "") -> None:
        """Записать расход."""
        self.collector.record(
            "expense", amount, label=label,
            metric_type=MetricType.EXPENSE, unit="USD",
        )

    # ── KPI ────────────────────────────────────────────────────────────────

    def create_kpi(
        self,
        name: str,
        target: float,
        unit: str = "",
        period: str = "month",
        description: str = "",
    ) -> KPI:
        """Создать KPI."""
        return self.kpi_tracker.create_kpi(
            name=name,
            target_value=target,
            unit=unit,
            period=period,
            description=description,
        )

    def update_kpi(self, name: str, value: float) -> KPI | None:
        """Обновить KPI по имени."""
        kpi = self.kpi_tracker.find_kpi(name)
        if kpi:
            kpi.update(value)
        return kpi

    # ── Dashboard ─────────────────────────────────────────────────────────

    def generate_dashboard(self) -> str:
        """Сгенерировать текстовый дашборд."""
        metrics = self.collector.get_all_series()
        kpis = self.kpi_tracker.get_all_kpis()

        # Trends
        trends = {}
        for name, series in metrics.items():
            if series.count >= 2:
                trends[name] = self.trend_analyzer.analyze(series)

        return self.formatter.format_dashboard(metrics, kpis, trends)

    def generate_trend_report(self) -> str:
        """Отчёт о трендах."""
        trends = {}
        for name, series in self.collector.get_all_series().items():
            if series.count >= 2:
                trends[name] = self.trend_analyzer.analyze(series)
        return self.formatter.format_trend_report(trends)

    def compare_periods(
        self,
        metric_name: str,
        period_1: tuple[datetime, datetime],
        period_2: tuple[datetime, datetime],
    ) -> PeriodComparison | None:
        """Сравнить периоды для метрики."""
        series = self.collector.get_series(metric_name)
        if not series:
            return None
        return self.trend_analyzer.compare_periods(
            series, period_1, period_2,
        )

    def forecast(
        self,
        metric_name: str,
        periods_ahead: int = 3,
    ) -> list[float]:
        """Прогноз метрики."""
        series = self.collector.get_series(metric_name)
        if not series:
            return []
        return self.trend_analyzer.forecast_simple(series, periods_ahead)

    # ── Stats ─────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Полная статистика."""
        return {
            "metrics": {
                "series_count": len(self.collector.list_series()),
                "summary": self.collector.get_summary(),
            },
            "kpi": self.kpi_tracker.get_stats(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

analytics_dashboard = AnalyticsDashboard()
