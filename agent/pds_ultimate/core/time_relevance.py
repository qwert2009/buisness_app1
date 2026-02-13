"""
PDS-Ultimate Time & Relevance Awareness (Part 10 — Item 10)
=============================================================
Учёт времени и актуальности данных.

«Этот ответ основан на данных за 2023 год — проверить обновления?»

Компоненты:
1. TemporalExtractor — извлечение дат/периодов из текста
2. FreshnessScorer — оценка актуальности данных
3. TimeDecayCalculator — формула затухания
4. RelevanceTracker — отслеживание релевантности источников
5. TimeRelevanceEngine — фасад
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS & DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class FreshnessGrade(str, Enum):
    """Оценка свежести данных."""
    FRESH = "fresh"           # < 1 day
    RECENT = "recent"         # < 7 days
    CURRENT = "current"       # < 30 days
    AGING = "aging"           # < 90 days
    STALE = "stale"           # < 365 days
    OUTDATED = "outdated"     # > 365 days

    @property
    def emoji(self) -> str:
        return {
            "fresh": "🟢",
            "recent": "🟢",
            "current": "🟡",
            "aging": "🟠",
            "stale": "🔴",
            "outdated": "⚫",
        }.get(self.value, "⚪")


class TemporalScope(str, Enum):
    """Временной охват."""
    REAL_TIME = "real_time"       # Мгновенно
    HOURLY = "hourly"            # Часовые данные
    DAILY = "daily"              # Дневные данные
    WEEKLY = "weekly"            # Недельные данные
    MONTHLY = "monthly"          # Месячные данные
    QUARTERLY = "quarterly"      # Квартальные данные
    ANNUAL = "annual"            # Годовые данные
    HISTORICAL = "historical"    # Исторические


@dataclass
class TemporalMarker:
    """Временной маркер, извлечённый из текста."""
    text: str                    # Исходный текст маркера
    date: datetime | None        # Распознанная дата
    scope: TemporalScope = TemporalScope.DAILY
    confidence: float = 0.5
    position: int = 0            # Позиция в тексте

    @property
    def age_days(self) -> float:
        if self.date is None:
            return float('inf')
        delta = datetime.now() - self.date
        return delta.total_seconds() / 86400

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "date": self.date.isoformat() if self.date else None,
            "scope": self.scope.value,
            "age_days": round(self.age_days, 1),
            "confidence": round(self.confidence, 2),
        }


@dataclass
class FreshnessReport:
    """Отчёт о свежести данных."""
    grade: FreshnessGrade
    score: float               # 0-1 (1 = самый свежий)
    data_age_days: float
    markers: list[TemporalMarker] = field(default_factory=list)
    recommendation: str = ""
    needs_update: bool = False

    def to_dict(self) -> dict:
        return {
            "grade": self.grade.value,
            "grade_emoji": self.grade.emoji,
            "score": round(self.score, 3),
            "age_days": round(self.data_age_days, 1),
            "markers_count": len(self.markers),
            "needs_update": self.needs_update,
            "recommendation": self.recommendation,
        }


@dataclass
class RelevanceEntry:
    """Запись о релевантности источника."""
    source_id: str
    source_name: str
    content_hash: str = ""
    first_seen: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 1
    freshness_score: float = 1.0
    relevance_score: float = 0.5
    tags: list[str] = field(default_factory=list)

    @property
    def age_days(self) -> float:
        return (time.time() - self.first_seen) / 86400

    @property
    def combined_score(self) -> float:
        """Комбинированная оценка: freshness × relevance."""
        return self.freshness_score * self.relevance_score

    def touch(self) -> None:
        """Обновить время доступа."""
        self.last_accessed = time.time()
        self.access_count += 1

    def to_dict(self) -> dict:
        return {
            "source": self.source_name,
            "age_days": round(self.age_days, 1),
            "freshness": round(self.freshness_score, 3),
            "relevance": round(self.relevance_score, 3),
            "combined": round(self.combined_score, 3),
            "accesses": self.access_count,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. TEMPORAL EXTRACTOR — Извлечение дат
# ═══════════════════════════════════════════════════════════════════════════════


class TemporalExtractor:
    """
    Извлекает даты и временные маркеры из текста.

    Поддерживает:
    - «2024», «январь 2024», «01.01.2024», «2024-01-15»
    - «вчера», «сегодня», «на прошлой неделе»
    - «Q1 2024», «первый квартал»
    """

    # Паттерны
    YEAR_PATTERN = re.compile(r'\b(20[12]\d)\b')
    DATE_PATTERN = re.compile(
        r'\b(\d{1,2})[./](\d{1,2})[./](20[12]\d)\b'
    )
    ISO_PATTERN = re.compile(r'\b(20[12]\d)-(\d{2})-(\d{2})\b')
    QUARTER_PATTERN = re.compile(
        r'\b[QqКк]([1-4])\s*(20[12]\d)\b'
    )

    MONTH_NAMES_RU = {
        "январ": 1, "феврал": 2, "март": 3, "апрел": 4,
        "мая": 5, "май": 5, "июн": 6, "июл": 7, "август": 8,
        "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
    }

    RELATIVE_MARKERS = {
        "сегодня": 0, "вчера": 1, "позавчера": 2,
        "today": 0, "yesterday": 1,
    }

    RELATIVE_PERIODS = {
        "на прошлой неделе": 7, "last week": 7,
        "в прошлом месяце": 30, "last month": 30,
        "в прошлом году": 365, "last year": 365,
    }

    def extract(self, text: str) -> list[TemporalMarker]:
        """Извлечь все временные маркеры из текста."""
        markers: list[TemporalMarker] = []

        # ISO dates (2024-01-15)
        for m in self.ISO_PATTERN.finditer(text):
            try:
                dt = datetime(int(m.group(1)), int(
                    m.group(2)), int(m.group(3)))
                markers.append(TemporalMarker(
                    text=m.group(0), date=dt,
                    scope=TemporalScope.DAILY,
                    confidence=0.95, position=m.start(),
                ))
            except ValueError:
                pass

        # DD.MM.YYYY or DD/MM/YYYY
        for m in self.DATE_PATTERN.finditer(text):
            try:
                dt = datetime(int(m.group(3)), int(
                    m.group(2)), int(m.group(1)))
                markers.append(TemporalMarker(
                    text=m.group(0), date=dt,
                    scope=TemporalScope.DAILY,
                    confidence=0.9, position=m.start(),
                ))
            except ValueError:
                pass

        # Quarter (Q1 2024)
        for m in self.QUARTER_PATTERN.finditer(text):
            q = int(m.group(1))
            year = int(m.group(2))
            month = (q - 1) * 3 + 1
            markers.append(TemporalMarker(
                text=m.group(0),
                date=datetime(year, month, 1),
                scope=TemporalScope.QUARTERLY,
                confidence=0.85, position=m.start(),
            ))

        # Month names (январь 2024)
        lower = text.lower()
        for prefix, month_num in self.MONTH_NAMES_RU.items():
            pattern = re.compile(rf'{prefix}\w*\s*(20[12]\d)', re.IGNORECASE)
            for m in pattern.finditer(lower):
                year = int(m.group(1))
                markers.append(TemporalMarker(
                    text=m.group(0),
                    date=datetime(year, month_num, 1),
                    scope=TemporalScope.MONTHLY,
                    confidence=0.8,
                    position=m.start(),
                ))

        # Standalone years (2024) — lower confidence if already found more specific
        specific_years = {
            mk.date.year for mk in markers if mk.date is not None
        }
        for m in self.YEAR_PATTERN.finditer(text):
            year = int(m.group(1))
            if year not in specific_years:
                markers.append(TemporalMarker(
                    text=m.group(0),
                    date=datetime(year, 1, 1),
                    scope=TemporalScope.ANNUAL,
                    confidence=0.6,
                    position=m.start(),
                ))

        # Relative markers
        for phrase, days_ago in self.RELATIVE_MARKERS.items():
            if phrase in lower:
                dt = datetime.now() - timedelta(days=days_ago)
                markers.append(TemporalMarker(
                    text=phrase, date=dt,
                    scope=TemporalScope.DAILY,
                    confidence=0.7,
                    position=lower.index(phrase),
                ))

        for phrase, days_ago in self.RELATIVE_PERIODS.items():
            if phrase in lower:
                dt = datetime.now() - timedelta(days=days_ago)
                markers.append(TemporalMarker(
                    text=phrase, date=dt,
                    scope=TemporalScope.WEEKLY
                    if days_ago <= 7
                    else TemporalScope.MONTHLY,
                    confidence=0.6,
                    position=lower.index(phrase),
                ))

        markers.sort(key=lambda m: m.position)
        return markers

    def get_oldest_date(
        self, markers: list[TemporalMarker]
    ) -> datetime | None:
        """Найти самую старую дату."""
        dated = [m for m in markers if m.date is not None]
        if not dated:
            return None
        return min(m.date for m in dated)

    def get_newest_date(
        self, markers: list[TemporalMarker]
    ) -> datetime | None:
        """Найти самую свежую дату."""
        dated = [m for m in markers if m.date is not None]
        if not dated:
            return None
        return max(m.date for m in dated)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. FRESHNESS SCORER — Оценка актуальности
# ═══════════════════════════════════════════════════════════════════════════════


class FreshnessScorer:
    """
    Оценивает актуальность данных.

    Используется временная маркировка для определения возраста данных.
    """

    # Пороги для оценок (в днях)
    GRADE_THRESHOLDS = {
        FreshnessGrade.FRESH: 1,
        FreshnessGrade.RECENT: 7,
        FreshnessGrade.CURRENT: 30,
        FreshnessGrade.AGING: 90,
        FreshnessGrade.STALE: 365,
    }

    def __init__(self, extractor: TemporalExtractor | None = None):
        self._extractor = extractor or TemporalExtractor()

    def score_text(self, text: str) -> FreshnessReport:
        """Оценить актуальность текста."""
        markers = self._extractor.extract(text)
        if not markers:
            return FreshnessReport(
                grade=FreshnessGrade.CURRENT,
                score=0.5,
                data_age_days=0,
                recommendation="Не удалось определить дату данных",
            )

        newest = self._extractor.get_newest_date(markers)
        if newest is None:
            return FreshnessReport(
                grade=FreshnessGrade.CURRENT,
                score=0.5,
                data_age_days=0,
                markers=markers,
            )

        age_days = (datetime.now() - newest).total_seconds() / 86400
        return self._build_report(age_days, markers)

    def score_age(self, age_days: float) -> FreshnessReport:
        """Оценить по возрасту в днях."""
        return self._build_report(age_days, [])

    def _build_report(
        self,
        age_days: float,
        markers: list[TemporalMarker],
    ) -> FreshnessReport:
        """Построить отчёт."""
        grade = self._age_to_grade(age_days)
        score = self._age_to_score(age_days)
        needs_update = grade in (
            FreshnessGrade.STALE, FreshnessGrade.OUTDATED,
        )
        rec = self._recommendation(grade, age_days)

        return FreshnessReport(
            grade=grade,
            score=score,
            data_age_days=age_days,
            markers=markers,
            needs_update=needs_update,
            recommendation=rec,
        )

    def _age_to_grade(self, age_days: float) -> FreshnessGrade:
        for grade, threshold in self.GRADE_THRESHOLDS.items():
            if age_days <= threshold:
                return grade
        return FreshnessGrade.OUTDATED

    def _age_to_score(self, age_days: float) -> float:
        """Экспоненциальное затухание: score = e^(-λ*age)."""
        half_life = 90  # 90 дней — half-life
        lam = math.log(2) / half_life
        return math.exp(-lam * max(age_days, 0))

    def _recommendation(
        self, grade: FreshnessGrade, age_days: float
    ) -> str:
        recs = {
            FreshnessGrade.FRESH: "Данные актуальны ✅",
            FreshnessGrade.RECENT: "Данные свежие, можно использовать",
            FreshnessGrade.CURRENT: "Данные актуальны, но стоит проверить обновления",
            FreshnessGrade.AGING:
                f"Данные устаревают ({age_days:.0f} дней) — рекомендуется обновление",
            FreshnessGrade.STALE:
                f"⚠️ Данные устарели ({age_days:.0f} дней) — нужна проверка",
            FreshnessGrade.OUTDATED:
                f"🚫 Данные сильно устарели ({age_days:.0f} дней) — "
                "требуется обновление!",
        }
        return recs.get(grade, "")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. TIME DECAY CALCULATOR — Формула затухания
# ═══════════════════════════════════════════════════════════════════════════════


class TimeDecayCalculator:
    """
    Вычисляет коэффициент затухания для данных по времени.

    Формулы:
    - Экспоненциальное: f(t) = e^(-λ*t)
    - Линейное: f(t) = max(0, 1 - t/T)
    - Гиперболическое: f(t) = 1 / (1 + α*t)
    """

    def exponential(
        self,
        age_days: float,
        half_life_days: float = 90,
    ) -> float:
        """Экспоненциальное затухание."""
        if half_life_days <= 0:
            return 0.0
        lam = math.log(2) / half_life_days
        return math.exp(-lam * max(age_days, 0))

    def linear(
        self,
        age_days: float,
        max_age_days: float = 365,
    ) -> float:
        """Линейное затухание."""
        if max_age_days <= 0:
            return 0.0
        return max(0.0, 1.0 - age_days / max_age_days)

    def hyperbolic(
        self,
        age_days: float,
        alpha: float = 0.01,
    ) -> float:
        """Гиперболическое затухание."""
        return 1.0 / (1.0 + alpha * max(age_days, 0))

    def weighted_score(
        self,
        base_score: float,
        age_days: float,
        decay_type: str = "exponential",
        **kwargs: Any,
    ) -> float:
        """Применить затухание к базовому скору."""
        if decay_type == "exponential":
            factor = self.exponential(age_days, **kwargs)
        elif decay_type == "linear":
            factor = self.linear(age_days, **kwargs)
        elif decay_type == "hyperbolic":
            factor = self.hyperbolic(age_days, **kwargs)
        else:
            factor = self.exponential(age_days)
        return base_score * factor


# ═══════════════════════════════════════════════════════════════════════════════
# 4. RELEVANCE TRACKER — Отслеживание релевантности
# ═══════════════════════════════════════════════════════════════════════════════


class RelevanceTracker:
    """
    Отслеживает релевантность и актуальность источников.

    Автоматически понижает score устаревших источников.
    """

    def __init__(self, max_entries: int = 500):
        self._entries: dict[str, RelevanceEntry] = {}
        self._max_entries = max_entries
        self._decay = TimeDecayCalculator()

    def track(
        self,
        source_id: str,
        source_name: str = "",
        relevance: float = 0.5,
        tags: list[str] | None = None,
    ) -> RelevanceEntry:
        """Начать отслеживание источника."""
        if source_id in self._entries:
            entry = self._entries[source_id]
            entry.touch()
            entry.relevance_score = relevance
            return entry

        entry = RelevanceEntry(
            source_id=source_id,
            source_name=source_name or source_id,
            relevance_score=relevance,
            tags=tags or [],
        )
        self._entries[source_id] = entry
        self._enforce_limit()
        return entry

    def get(self, source_id: str) -> RelevanceEntry | None:
        return self._entries.get(source_id)

    def update_freshness(self) -> int:
        """Пересчитать freshness для всех источников."""
        updated = 0
        for entry in self._entries.values():
            new_score = self._decay.exponential(entry.age_days)
            if abs(new_score - entry.freshness_score) > 0.01:
                entry.freshness_score = new_score
                updated += 1
        return updated

    def get_stale(self, threshold: float = 0.3) -> list[RelevanceEntry]:
        """Найти устаревшие источники."""
        self.update_freshness()
        return [
            e for e in self._entries.values()
            if e.freshness_score < threshold
        ]

    def get_top(self, n: int = 10) -> list[RelevanceEntry]:
        """Топ-N самых релевантных источников."""
        self.update_freshness()
        entries = sorted(
            self._entries.values(),
            key=lambda e: e.combined_score,
            reverse=True,
        )
        return entries[:n]

    def remove(self, source_id: str) -> bool:
        return self._entries.pop(source_id, None) is not None

    def _enforce_limit(self) -> None:
        """Удалить самые неактуальные при переполнении."""
        if len(self._entries) <= self._max_entries:
            return
        entries = sorted(
            self._entries.values(), key=lambda e: e.combined_score,
        )
        to_remove = entries[: len(entries) - self._max_entries]
        for e in to_remove:
            del self._entries[e.source_id]

    @property
    def count(self) -> int:
        return len(self._entries)

    def get_stats(self) -> dict:
        if not self._entries:
            return {"count": 0, "stale_count": 0}
        scores = [e.freshness_score for e in self._entries.values()]
        return {
            "count": self.count,
            "avg_freshness": round(sum(scores) / len(scores), 3),
            "stale_count": len(self.get_stale()),
            "max_entries": self._max_entries,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# FACADE: TimeRelevanceEngine
# ═══════════════════════════════════════════════════════════════════════════════


class TimeRelevanceEngine:
    """
    Фасад для работы с временем и релевантностью.

    Использование:
        engine = TimeRelevanceEngine()

        # Оценить свежесть текста
        report = engine.check_freshness("По данным за 2023 год...")

        # Отследить источник
        engine.track_source("wiki_1", "Wikipedia", relevance=0.8)

        # Получить рекомендацию
        freshness = engine.get_freshness_label("Данные за Q1 2022")
    """

    def __init__(self):
        self.extractor = TemporalExtractor()
        self.freshness_scorer = FreshnessScorer(self.extractor)
        self.decay = TimeDecayCalculator()
        self.relevance_tracker = RelevanceTracker()

    def check_freshness(self, text: str) -> FreshnessReport:
        """Проверить свежесть текста."""
        return self.freshness_scorer.score_text(text)

    def extract_dates(self, text: str) -> list[TemporalMarker]:
        """Извлечь даты из текста."""
        return self.extractor.extract(text)

    def get_freshness_label(self, text: str) -> str:
        """Краткий лейбл свежести: «🟢 Fresh» / «🔴 Stale»."""
        report = self.freshness_scorer.score_text(text)
        return f"{report.grade.emoji} {report.grade.value.capitalize()}"

    def apply_time_decay(
        self,
        score: float,
        age_days: float,
        method: str = "exponential",
    ) -> float:
        """Применить затухание к скору."""
        return self.decay.weighted_score(
            score, age_days, decay_type=method,
        )

    def track_source(
        self,
        source_id: str,
        name: str = "",
        relevance: float = 0.5,
    ) -> RelevanceEntry:
        """Отследить источник."""
        return self.relevance_tracker.track(source_id, name, relevance)

    def get_stale_sources(self) -> list[dict]:
        """Получить устаревшие источники."""
        stale = self.relevance_tracker.get_stale()
        return [e.to_dict() for e in stale]

    def get_stats(self) -> dict:
        return {
            "sources": self.relevance_tracker.get_stats(),
        }


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

time_relevance = TimeRelevanceEngine()
