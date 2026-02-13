"""
PDS-Ultimate Confidence & Uncertainty Tracker (Part 10 — Item 6)
==================================================================
Каждый вывод сопровождается оценкой уверенности.
Если низкая → автоматический дополнительный поиск.

Компоненты:
1. ConfidenceEstimator — оценка уверенности вывода
2. UncertaintyTracker — отслеживание и классификация неопределённости
3. AutoSearchTrigger — автоматический допоиск при низкой уверенности
4. ConfidenceCalibrator — калибровка на основе истории
5. OutputWrapper — обёртка вывода с метаданными уверенности
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS & DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class ConfidenceLevel(str, Enum):
    """Уровень уверенности."""
    VERY_HIGH = "very_high"   # > 0.9
    HIGH = "high"             # 0.7 - 0.9
    MEDIUM = "medium"         # 0.5 - 0.7
    LOW = "low"               # 0.3 - 0.5
    VERY_LOW = "very_low"     # < 0.3


class UncertaintyType(str, Enum):
    """Тип неопределённости."""
    DATA_MISSING = "data_missing"          # Нет данных
    CONFLICTING_SOURCES = "conflicting"    # Противоречивые источники
    OUTDATED_INFO = "outdated"             # Устаревшая информация
    AMBIGUOUS_QUERY = "ambiguous"          # Неоднозначный запрос
    LOW_SOURCE_TRUST = "low_trust"         # Низкое доверие к источникам
    INSUFFICIENT_EVIDENCE = "insufficient"  # Мало доказательств
    MODEL_UNCERTAINTY = "model"            # Неуверенность модели


class SearchAction(str, Enum):
    """Действие при низкой уверенности."""
    NONE = "none"
    EXPAND_QUERY = "expand_query"
    ADD_SOURCES = "add_sources"
    VERIFY_FACTS = "verify_facts"
    FULL_RESEARCH = "full_research"


@dataclass
class ConfidenceScore:
    """Оценка уверенности для конкретного вывода."""
    value: float                # 0.0 - 1.0
    level: ConfidenceLevel = ConfidenceLevel.MEDIUM
    factors: dict[str, float] = field(default_factory=dict)
    uncertainties: list[UncertaintyType] = field(default_factory=list)
    suggested_action: SearchAction = SearchAction.NONE
    explanation: str = ""
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        self.value = max(0.0, min(1.0, self.value))
        self.level = self._compute_level()
        if not self.suggested_action or self.suggested_action == SearchAction.NONE:
            self.suggested_action = self._suggest_action()

    def _compute_level(self) -> ConfidenceLevel:
        if self.value > 0.9:
            return ConfidenceLevel.VERY_HIGH
        elif self.value > 0.7:
            return ConfidenceLevel.HIGH
        elif self.value > 0.5:
            return ConfidenceLevel.MEDIUM
        elif self.value > 0.3:
            return ConfidenceLevel.LOW
        return ConfidenceLevel.VERY_LOW

    def _suggest_action(self) -> SearchAction:
        if self.value > 0.7:
            return SearchAction.NONE
        if UncertaintyType.DATA_MISSING in self.uncertainties:
            return SearchAction.FULL_RESEARCH
        if UncertaintyType.CONFLICTING_SOURCES in self.uncertainties:
            return SearchAction.VERIFY_FACTS
        if UncertaintyType.OUTDATED_INFO in self.uncertainties:
            return SearchAction.ADD_SOURCES
        if self.value < 0.3:
            return SearchAction.FULL_RESEARCH
        return SearchAction.EXPAND_QUERY

    @property
    def needs_additional_search(self) -> bool:
        return self.value < 0.7

    @property
    def emoji(self) -> str:
        emojis = {
            ConfidenceLevel.VERY_HIGH: "🟢",
            ConfidenceLevel.HIGH: "🟡",
            ConfidenceLevel.MEDIUM: "🟠",
            ConfidenceLevel.LOW: "🔴",
            ConfidenceLevel.VERY_LOW: "⚫",
        }
        return emojis.get(self.level, "❓")

    def to_dict(self) -> dict:
        return {
            "value": round(self.value, 3),
            "level": self.level.value,
            "factors": {k: round(v, 3) for k, v in self.factors.items()},
            "uncertainties": [u.value for u in self.uncertainties],
            "action": self.suggested_action.value,
            "needs_search": self.needs_additional_search,
            "explanation": self.explanation,
        }


@dataclass
class TrackedOutput:
    """Вывод агента с трекингом уверенности."""
    content: str
    confidence: ConfidenceScore
    query: str = ""
    sources_count: int = 0
    search_iterations: int = 0
    total_time_ms: float = 0.0
    metadata: dict = field(default_factory=dict)

    def format_with_confidence(self) -> str:
        """Форматировать вывод с индикатором уверенности."""
        conf = self.confidence
        lines = [self.content]
        lines.append(
            f"\n{conf.emoji} Уверенность: {conf.value:.0%} ({conf.level.value})"
        )
        if conf.uncertainties:
            labels = [u.value for u in conf.uncertainties]
            lines.append(f"⚠️ Неопределённости: {', '.join(labels)}")
        if self.sources_count:
            lines.append(f"📖 Источников: {self.sources_count}")
        if self.search_iterations > 1:
            lines.append(f"🔄 Итераций поиска: {self.search_iterations}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "content": self.content[:500],
            "confidence": self.confidence.to_dict(),
            "sources_count": self.sources_count,
            "search_iterations": self.search_iterations,
            "time_ms": round(self.total_time_ms, 1),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CONFIDENCE ESTIMATOR — Оценка уверенности
# ═══════════════════════════════════════════════════════════════════════════════


class ConfidenceEstimator:
    """
    Оценка уверенности вывода на основе множества факторов.

    Факторы:
    - source_count: количество источников
    - source_agreement: согласованность источников
    - data_freshness: свежесть данных
    - query_specificity: точность запроса
    - evidence_strength: сила доказательств
    """

    # Весa факторов
    FACTOR_WEIGHTS: dict[str, float] = {
        "source_count": 0.20,
        "source_agreement": 0.25,
        "data_freshness": 0.15,
        "query_specificity": 0.15,
        "evidence_strength": 0.25,
    }

    def estimate(
        self,
        text: str = "",
        source_count: int = 0,
        source_agreement: float = 1.0,
        data_freshness: float = 1.0,
        query_specificity: float = 0.5,
        evidence_strength: float = 0.5,
        custom_factors: dict[str, float] | None = None,
    ) -> ConfidenceScore:
        """
        Оценить уверенность.

        Args:
            text: Текст ответа
            source_count: Количество источников (0-10+)
            source_agreement: Согласованность (0-1)
            data_freshness: Свежесть данных (0-1)
            query_specificity: Точность запроса (0-1)
            evidence_strength: Сила доказательств (0-1)
        """
        factors: dict[str, float] = {}

        # Source count → normalized (0-1)
        factors["source_count"] = min(
            1.0, source_count / 5.0) if source_count > 0 else 0.1
        factors["source_agreement"] = max(0.0, min(1.0, source_agreement))
        factors["data_freshness"] = max(0.0, min(1.0, data_freshness))
        factors["query_specificity"] = max(0.0, min(1.0, query_specificity))
        factors["evidence_strength"] = max(0.0, min(1.0, evidence_strength))

        if custom_factors:
            factors.update(custom_factors)

        weighted_sum = sum(
            factors.get(k, 0.5) * w
            for k, w in self.FACTOR_WEIGHTS.items()
        )

        # Текстовый анализ — hedging words снижают уверенность
        text_penalty = self._analyze_text_confidence(text)

        final = weighted_sum * text_penalty

        # Определяем uncertainties
        uncertainties: list[UncertaintyType] = []
        if source_count == 0:
            uncertainties.append(UncertaintyType.DATA_MISSING)
        if source_agreement < 0.5:
            uncertainties.append(UncertaintyType.CONFLICTING_SOURCES)
        if data_freshness < 0.3:
            uncertainties.append(UncertaintyType.OUTDATED_INFO)
        if query_specificity < 0.3:
            uncertainties.append(UncertaintyType.AMBIGUOUS_QUERY)
        if evidence_strength < 0.3:
            uncertainties.append(UncertaintyType.INSUFFICIENT_EVIDENCE)

        explanation_parts = []
        if factors["source_count"] < 0.4:
            explanation_parts.append("мало источников")
        if factors["source_agreement"] < 0.5:
            explanation_parts.append("источники расходятся")
        if factors["data_freshness"] < 0.5:
            explanation_parts.append("данные могут быть устаревшими")
        if not explanation_parts:
            explanation_parts.append("достаточно данных")

        return ConfidenceScore(
            value=final,
            factors=factors,
            uncertainties=uncertainties,
            explanation="; ".join(explanation_parts),
        )

    @staticmethod
    def _analyze_text_confidence(text: str) -> float:
        """Анализ хеджирующих слов в тексте → penalty multiplier."""
        if not text:
            return 0.9
        text_lower = text.lower()
        hedging_words = [
            "возможно", "вероятно", "может быть", "предположительно",
            "не уверен", "perhaps", "maybe", "probably", "might",
            "uncertain", "unclear", "не ясно", "трудно сказать",
            "ориентировочно", "приблизительно", "примерно",
        ]
        strong_words = [
            "точно", "однозначно", "определённо", "exactly",
            "definitely", "certainly", "подтверждено", "verified",
            "доказано", "proved",
        ]
        hedge_count = sum(1 for w in hedging_words if w in text_lower)
        strong_count = sum(1 for w in strong_words if w in text_lower)

        penalty = 1.0 - hedge_count * 0.05 + strong_count * 0.03
        return max(0.5, min(1.1, penalty))


# ═══════════════════════════════════════════════════════════════════════════════
# 2. UNCERTAINTY TRACKER — Отслеживание неопределённости
# ═══════════════════════════════════════════════════════════════════════════════


class UncertaintyTracker:
    """
    Отслеживает неопределённости по запросам.
    Собирает статистику для калибровки.
    """

    def __init__(self, max_history: int = 1000):
        self._history: list[ConfidenceScore] = []
        self._by_type: defaultdict[str, int] = defaultdict(int)
        self._max_history = max_history
        self._action_outcomes: list[dict] = []  # {action, success}

    def track(self, score: ConfidenceScore) -> None:
        """Записать оценку уверенности."""
        self._history.append(score)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history // 2:]
        for u in score.uncertainties:
            self._by_type[u.value] += 1

    def record_outcome(
        self,
        action: SearchAction,
        success: bool,
        confidence_before: float,
        confidence_after: float,
    ) -> None:
        """Записать результат действия."""
        self._action_outcomes.append({
            "action": action.value,
            "success": success,
            "delta": confidence_after - confidence_before,
            "timestamp": time.time(),
        })

    @property
    def average_confidence(self) -> float:
        if not self._history:
            return 0.5
        return sum(s.value for s in self._history) / len(self._history)

    @property
    def low_confidence_rate(self) -> float:
        if not self._history:
            return 0.0
        low = sum(1 for s in self._history if s.value < 0.5)
        return low / len(self._history)

    def get_most_common_uncertainties(self, top_n: int = 5) -> list[tuple[str, int]]:
        """Наиболее частые типы неопределённости."""
        return sorted(
            self._by_type.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:top_n]

    def get_action_effectiveness(self) -> dict[str, dict]:
        """Эффективность каждого действия."""
        by_action: defaultdict[str, list] = defaultdict(list)
        for outcome in self._action_outcomes:
            by_action[outcome["action"]].append(outcome)

        result = {}
        for action, outcomes in by_action.items():
            successes = sum(1 for o in outcomes if o["success"])
            avg_delta = sum(o["delta"] for o in outcomes) / \
                len(outcomes) if outcomes else 0
            result[action] = {
                "count": len(outcomes),
                "success_rate": round(successes / len(outcomes), 2) if outcomes else 0,
                "avg_improvement": round(avg_delta, 3),
            }
        return result

    def get_stats(self) -> dict:
        return {
            "total_tracked": len(self._history),
            "average_confidence": round(self.average_confidence, 3),
            "low_confidence_rate": round(self.low_confidence_rate, 3),
            "uncertainties": dict(self._by_type),
            "action_outcomes": len(self._action_outcomes),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. AUTO-SEARCH TRIGGER — Авто-допоиск при низкой уверенности
# ═══════════════════════════════════════════════════════════════════════════════


class AutoSearchTrigger:
    """
    Автоматический триггер дополнительного поиска.

    Правила:
    - confidence < 0.5 → full_research
    - confidence < 0.7 → expand_query
    - conflicting_sources → verify_facts
    - outdated_info → add_sources
    """

    def __init__(self, threshold: float = 0.7, max_iterations: int = 3):
        self._threshold = threshold
        self._max_iterations = max_iterations
        self._triggers_fired = 0

    def should_search(self, score: ConfidenceScore) -> bool:
        """Нужен ли дополнительный поиск?"""
        return score.value < self._threshold

    def get_search_plan(
        self,
        score: ConfidenceScore,
        iteration: int = 0,
    ) -> dict | None:
        """
        Получить план дополнительного поиска.

        Returns: {action, params} или None
        """
        if iteration >= self._max_iterations:
            return None
        if not self.should_search(score):
            return None

        self._triggers_fired += 1
        action = score.suggested_action

        plan: dict[str, Any] = {
            "action": action.value, "iteration": iteration + 1}

        if action == SearchAction.FULL_RESEARCH:
            plan["max_sources"] = 5 + iteration * 2
            plan["expand_queries"] = True
        elif action == SearchAction.ADD_SOURCES:
            plan["max_sources"] = 3 + iteration
            plan["prefer_recent"] = True
        elif action == SearchAction.VERIFY_FACTS:
            plan["verify_mode"] = True
            plan["min_trust"] = 0.7
        elif action == SearchAction.EXPAND_QUERY:
            plan["expansions"] = 2 + iteration

        return plan

    @property
    def threshold(self) -> float:
        return self._threshold

    @threshold.setter
    def threshold(self, value: float) -> None:
        self._threshold = max(0.1, min(0.95, value))

    def get_stats(self) -> dict:
        return {
            "threshold": self._threshold,
            "max_iterations": self._max_iterations,
            "triggers_fired": self._triggers_fired,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. CONFIDENCE CALIBRATOR — Калибровка на истории
# ═══════════════════════════════════════════════════════════════════════════════


class ConfidenceCalibrator:
    """
    Калибрует оценки уверенности на основе исторических данных.

    Если система систематически переоценивает/недооценивает →
    корректируем.
    """

    def __init__(self):
        # (predicted, actual_correct)
        self._predictions: list[tuple[float, bool]] = []
        self._calibration_factor: float = 1.0

    def record(self, predicted_confidence: float, was_correct: bool) -> None:
        """Записать предсказание и реальный результат."""
        self._predictions.append((predicted_confidence, was_correct))
        if len(self._predictions) > 500:
            self._predictions = self._predictions[-250:]
        self._update_calibration()

    def calibrate(self, raw_confidence: float) -> float:
        """Откалибровать оценку."""
        return max(0.0, min(1.0, raw_confidence * self._calibration_factor))

    def _update_calibration(self) -> None:
        """Обновить коэффициент калибровки."""
        if len(self._predictions) < 10:
            return

        bins: defaultdict[int, list[bool]] = defaultdict(list)
        for pred, actual in self._predictions:
            bin_idx = int(pred * 10)
            bins[bin_idx].append(actual)

        predicted_avg = sum(p for p, _ in self._predictions) / \
            len(self._predictions)
        actual_avg = sum(1 for _, a in self._predictions if a) / \
            len(self._predictions)

        if predicted_avg > 0:
            self._calibration_factor = actual_avg / predicted_avg
            self._calibration_factor = max(
                0.5, min(1.5, self._calibration_factor))

    @property
    def is_overconfident(self) -> bool:
        return self._calibration_factor < 0.9

    @property
    def is_underconfident(self) -> bool:
        return self._calibration_factor > 1.1

    def get_stats(self) -> dict:
        total = len(self._predictions)
        correct = sum(1 for _, a in self._predictions if a)
        return {
            "total_predictions": total,
            "accuracy": round(correct / total, 3) if total > 0 else 0.0,
            "calibration_factor": round(self._calibration_factor, 3),
            "overconfident": self.is_overconfident,
            "underconfident": self.is_underconfident,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# FACADE: ConfidenceTracker
# ═══════════════════════════════════════════════════════════════════════════════


class ConfidenceTracker:
    """
    Фасад для confidence & uncertainty tracking.

    Использование:
        tracker = ConfidenceTracker()

        # Оценить уверенность
        score = tracker.estimate("Ответ на вопрос", source_count=3)

        # Проверить, нужен ли допоиск
        if tracker.needs_search(score):
            plan = tracker.get_search_plan(score)

        # Обернуть вывод
        output = tracker.wrap_output("Ответ", score, query="вопрос")
    """

    def __init__(self, auto_search_threshold: float = 0.7):
        self.estimator = ConfidenceEstimator()
        self.uncertainty_tracker = UncertaintyTracker()
        self.auto_search = AutoSearchTrigger(threshold=auto_search_threshold)
        self.calibrator = ConfidenceCalibrator()

    def estimate(
        self,
        text: str = "",
        source_count: int = 0,
        source_agreement: float = 1.0,
        data_freshness: float = 1.0,
        evidence_strength: float = 0.5,
        **kwargs,
    ) -> ConfidenceScore:
        """Оценить уверенность вывода."""
        score = self.estimator.estimate(
            text=text,
            source_count=source_count,
            source_agreement=source_agreement,
            data_freshness=data_freshness,
            evidence_strength=evidence_strength,
            **kwargs,
        )

        calibrated_value = self.calibrator.calibrate(score.value)
        score.value = calibrated_value
        score.level = score._compute_level()

        self.uncertainty_tracker.track(score)
        return score

    def needs_search(self, score: ConfidenceScore) -> bool:
        """Нужен ли дополнительный поиск?"""
        return self.auto_search.should_search(score)

    def get_search_plan(
        self,
        score: ConfidenceScore,
        iteration: int = 0,
    ) -> dict | None:
        """План допоиска."""
        return self.auto_search.get_search_plan(score, iteration)

    def wrap_output(
        self,
        content: str,
        confidence: ConfidenceScore,
        query: str = "",
        sources_count: int = 0,
    ) -> TrackedOutput:
        """Обернуть вывод с метаданными уверенности."""
        return TrackedOutput(
            content=content,
            confidence=confidence,
            query=query,
            sources_count=sources_count,
        )

    def record_feedback(self, predicted: float, was_correct: bool) -> None:
        """Записать обратную связь для калибровки."""
        self.calibrator.record(predicted, was_correct)

    def get_stats(self) -> dict:
        return {
            "uncertainty": self.uncertainty_tracker.get_stats(),
            "auto_search": self.auto_search.get_stats(),
            "calibrator": self.calibrator.get_stats(),
        }


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

confidence_tracker = ConfidenceTracker()
