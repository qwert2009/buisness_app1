"""
PDS-Ultimate Adaptive Query Expansion (Part 10 — Item 7)
==========================================================
Агент улучшает запросы на основе промежуточных результатов:
«Чего мне не хватает?» → уточнённый поиск.

Цикл: generate → search → refine → search → refine → ...

Компоненты:
1. QueryExpander — расширение запроса синонимами/терминами
2. GapAnalyzer — «Чего не хватает в ответе?»
3. RefinementLoop — цикл уточнения запросов
4. ExpansionHistory — история расширений для отладки
5. QueryOptimizer — оптимальная формулировка запроса
"""

from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS & DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class ExpansionStrategy(str, Enum):
    """Стратегия расширения запроса."""
    SYNONYM = "synonym"           # Синонимы
    RELATED = "related"           # Связанные термины
    SPECIFIC = "specific"         # Уточнение (narrowing)
    BROAD = "broad"               # Расширение (broadening)
    TEMPORAL = "temporal"         # Добавление времени
    CONTEXTUAL = "contextual"     # На основе контекста


class GapType(str, Enum):
    """Тип пробела в информации."""
    MISSING_DATA = "missing_data"        # Нет данных
    INCOMPLETE = "incomplete"            # Частичный ответ
    NO_NUMBERS = "no_numbers"            # Нет числовых данных
    NO_SOURCE = "no_source"              # Нет подтверждения
    VAGUE = "vague"                      # Размытый ответ
    OUTDATED = "outdated"                # Устаревший ответ


@dataclass
class ExpandedQuery:
    """Расширенный запрос."""
    original: str
    expanded: str
    strategy: ExpansionStrategy
    added_terms: list[str] = field(default_factory=list)
    removed_terms: list[str] = field(default_factory=list)
    confidence: float = 0.5
    iteration: int = 0

    def to_dict(self) -> dict:
        return {
            "original": self.original,
            "expanded": self.expanded,
            "strategy": self.strategy.value,
            "added_terms": self.added_terms,
            "confidence": round(self.confidence, 3),
            "iteration": self.iteration,
        }


@dataclass
class InformationGap:
    """Обнаруженный пробел в информации."""
    gap_type: GapType
    description: str
    suggested_query: str = ""
    priority: float = 0.5  # 0-1, выше = важнее

    def to_dict(self) -> dict:
        return {
            "type": self.gap_type.value,
            "description": self.description,
            "suggested_query": self.suggested_query,
            "priority": round(self.priority, 2),
        }


@dataclass
class RefinementStep:
    """Шаг цикла уточнения."""
    iteration: int
    query: str
    results_summary: str = ""
    gaps_found: list[InformationGap] = field(default_factory=list)
    confidence_before: float = 0.0
    confidence_after: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "query": self.query,
            "gaps": [g.to_dict() for g in self.gaps_found],
            "confidence_delta": round(
                self.confidence_after - self.confidence_before, 3
            ),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. QUERY EXPANDER — Расширение запроса
# ═══════════════════════════════════════════════════════════════════════════════


class QueryExpander:
    """
    Расширяет запрос для более полного поиска.

    Стратегии:
    - Синонимы (synonym map)
    - Связанные термины (co-occurrence)
    - Уточнение (добавить год, регион)
    - Расширение (убрать ограничивающие термины)
    """

    # Словарь синонимов (бизнес-контекст)
    SYNONYMS: dict[str, list[str]] = {
        "цена": ["стоимость", "прайс", "расценка"],
        "доставка": ["логистика", "транспортировка", "отгрузка"],
        "поставщик": ["продавец", "supplier", "вендор"],
        "заказ": ["ордер", "order", "закупка"],
        "оплата": ["платёж", "перевод", "payment"],
        "товар": ["продукт", "изделие", "product"],
        "клиент": ["заказчик", "покупатель", "customer"],
        "прибыль": ["профит", "доход", "revenue", "profit"],
        "расход": ["затраты", "expense", "cost"],
        "курс": ["rate", "обменный курс", "exchange rate"],
        "склад": ["warehouse", "хранилище"],
        "контракт": ["договор", "соглашение", "contract"],
        "price": ["cost", "pricing", "rate"],
        "delivery": ["shipping", "logistics", "transport"],
        "supplier": ["vendor", "provider", "seller"],
        "order": ["purchase", "procurement"],
        "payment": ["transaction", "transfer"],
    }

    # Контекстуальные расширения
    CONTEXTUAL_EXPANSIONS: dict[str, list[str]] = {
        "Туркменистан": ["TMT", "манат", "Ашхабад"],
        "Китай": ["CNY", "юань", "КНР", "China"],
        "импорт": ["таможня", "пошлина", "сертификат"],
        "экспорт": ["таможня", "лицензия", "сертификат"],
    }

    def expand(
        self,
        query: str,
        strategy: ExpansionStrategy = ExpansionStrategy.SYNONYM,
        context: str = "",
        max_expansions: int = 3,
    ) -> ExpandedQuery:
        """Расширить запрос по стратегии."""
        if strategy == ExpansionStrategy.SYNONYM:
            return self._expand_synonyms(query, max_expansions)
        elif strategy == ExpansionStrategy.CONTEXTUAL:
            return self._expand_contextual(query, context)
        elif strategy == ExpansionStrategy.TEMPORAL:
            return self._expand_temporal(query)
        elif strategy == ExpansionStrategy.SPECIFIC:
            return self._expand_specific(query, context)
        elif strategy == ExpansionStrategy.BROAD:
            return self._expand_broad(query)
        else:
            return self._expand_related(query)

    def expand_multi(
        self,
        query: str,
        strategies: list[ExpansionStrategy] | None = None,
        context: str = "",
    ) -> list[ExpandedQuery]:
        """Расширить запрос несколькими стратегиями."""
        if strategies is None:
            strategies = [
                ExpansionStrategy.SYNONYM,
                ExpansionStrategy.CONTEXTUAL,
                ExpansionStrategy.TEMPORAL,
            ]
        results = []
        for s in strategies:
            eq = self.expand(query, strategy=s, context=context)
            if eq.expanded != query:
                results.append(eq)
        return results

    def _expand_synonyms(self, query: str, max_n: int = 3) -> ExpandedQuery:
        """Добавить синонимы."""
        words = query.lower().split()
        added: list[str] = []
        for word in words:
            syns = self.SYNONYMS.get(word, [])
            for syn in syns[:max_n]:
                if syn.lower() not in query.lower():
                    added.append(syn)
                    if len(added) >= max_n:
                        break
            if len(added) >= max_n:
                break
        expanded = f"{query} {' '.join(added)}" if added else query
        return ExpandedQuery(
            original=query,
            expanded=expanded.strip(),
            strategy=ExpansionStrategy.SYNONYM,
            added_terms=added,
            confidence=0.7 if added else 0.3,
        )

    def _expand_contextual(self, query: str, context: str) -> ExpandedQuery:
        """Расширить на основе контекста."""
        added: list[str] = []
        combined = f"{query} {context}".lower()
        for trigger, expansions in self.CONTEXTUAL_EXPANSIONS.items():
            if trigger.lower() in combined:
                for exp in expansions:
                    if exp.lower() not in combined:
                        added.append(exp)
        expanded = f"{query} {' '.join(added[:3])}" if added else query
        return ExpandedQuery(
            original=query,
            expanded=expanded.strip(),
            strategy=ExpansionStrategy.CONTEXTUAL,
            added_terms=added[:3],
            confidence=0.8 if added else 0.3,
        )

    def _expand_temporal(self, query: str) -> ExpandedQuery:
        """Добавить временной контекст."""
        from datetime import datetime
        year = datetime.now().year
        has_year = any(str(y) in query for y in range(2020, year + 2))
        if has_year:
            return ExpandedQuery(
                original=query, expanded=query,
                strategy=ExpansionStrategy.TEMPORAL,
                confidence=0.5,
            )
        expanded = f"{query} {year} актуально"
        return ExpandedQuery(
            original=query,
            expanded=expanded,
            strategy=ExpansionStrategy.TEMPORAL,
            added_terms=[str(year), "актуально"],
            confidence=0.75,
        )

    def _expand_specific(self, query: str, context: str) -> ExpandedQuery:
        """Уточнить запрос."""
        specifics: list[str] = []
        if context:
            terms = re.findall(r'[а-яёa-z]{4,}', context.lower())
            from pds_ultimate.core.semantic_engine import STOP_WORDS
            terms = [
                t for t in terms if t not in STOP_WORDS and t not in query.lower()]
            specifics = list(dict.fromkeys(terms))[:3]
        expanded = f"{query} {' '.join(specifics)}" if specifics else query
        return ExpandedQuery(
            original=query,
            expanded=expanded.strip(),
            strategy=ExpansionStrategy.SPECIFIC,
            added_terms=specifics,
            confidence=0.6 if specifics else 0.3,
        )

    def _expand_broad(self, query: str) -> ExpandedQuery:
        """Расширить запрос, убрав ограничения."""
        words = query.split()
        removed: list[str] = []
        if len(words) > 4:
            removed = words[-2:]
            expanded = " ".join(words[:-2])
        else:
            expanded = query
        return ExpandedQuery(
            original=query,
            expanded=expanded,
            strategy=ExpansionStrategy.BROAD,
            removed_terms=removed,
            confidence=0.5,
        )

    def _expand_related(self, query: str) -> ExpandedQuery:
        """Связанные термины."""
        added: list[str] = []
        words = query.lower().split()
        for word in words:
            for key, syns in self.SYNONYMS.items():
                if word in syns:
                    if key not in query.lower():
                        added.append(key)
                        break
        expanded = f"{query} {' '.join(added[:2])}" if added else query
        return ExpandedQuery(
            original=query,
            expanded=expanded.strip(),
            strategy=ExpansionStrategy.RELATED,
            added_terms=added[:2],
            confidence=0.6 if added else 0.3,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. GAP ANALYZER — Анализ пробелов
# ═══════════════════════════════════════════════════════════════════════════════


class GapAnalyzer:
    """
    Анализирует ответ и определяет: чего не хватает?

    Проверяет:
    - Есть ли числовые данные (если запрос подразумевает)
    - Есть ли подтверждение из источников
    - Достаточна ли полнота ответа
    - Актуальность данных
    """

    # Паттерны запросов, требующих числовых данных
    NUMERIC_PATTERNS = [
        r"сколько|цена|стоимость|курс|rate|price|cost|количество",
        r"how much|how many|percentage|процент|прибыль|расход",
    ]

    def analyze(
        self,
        query: str,
        answer: str,
        source_count: int = 0,
        confidence: float = 0.5,
    ) -> list[InformationGap]:
        """Найти пробелы в ответе."""
        gaps: list[InformationGap] = []

        # 1. Проверка на наличие данных
        if not answer or len(answer.strip()) < 20:
            gaps.append(InformationGap(
                gap_type=GapType.MISSING_DATA,
                description="Ответ слишком короткий или пустой",
                suggested_query=query,
                priority=1.0,
            ))
            return gaps

        # 2. Числовые данные нужны?
        needs_numbers = any(
            re.search(p, query.lower()) for p in self.NUMERIC_PATTERNS
        )
        has_numbers = bool(re.search(r'\d+', answer))
        if needs_numbers and not has_numbers:
            gaps.append(InformationGap(
                gap_type=GapType.NO_NUMBERS,
                description="Запрос подразумевает числа, но их нет в ответе",
                suggested_query=f"{query} точные цифры данные",
                priority=0.8,
            ))

        # 3. Подтверждение
        if source_count == 0:
            gaps.append(InformationGap(
                gap_type=GapType.NO_SOURCE,
                description="Нет подтверждающих источников",
                suggested_query=query,
                priority=0.7,
            ))

        # 4. Полнота
        if len(answer) < 100 and len(query.split()) > 5:
            gaps.append(InformationGap(
                gap_type=GapType.INCOMPLETE,
                description="Ответ может быть неполным для сложного вопроса",
                suggested_query=f"{query} подробно детально",
                priority=0.6,
            ))

        # 5. Размытость
        vague_markers = [
            "возможно", "вероятно", "может быть", "трудно сказать",
            "зависит от", "по-разному", "maybe", "perhaps",
        ]
        vague_count = sum(
            1 for m in vague_markers if m in answer.lower()
        )
        if vague_count >= 2:
            gaps.append(InformationGap(
                gap_type=GapType.VAGUE,
                description="Ответ содержит много размытых формулировок",
                suggested_query=f"{query} конкретно точно",
                priority=0.5,
            ))

        # 6. Низкая уверенность
        if confidence < 0.5 and not any(
            g.gap_type == GapType.MISSING_DATA for g in gaps
        ):
            gaps.append(InformationGap(
                gap_type=GapType.INCOMPLETE,
                description=f"Низкая уверенность ({confidence:.0%})",
                suggested_query=f"{query} verified reliable",
                priority=0.65,
            ))

        gaps.sort(key=lambda g: g.priority, reverse=True)
        return gaps


# ═══════════════════════════════════════════════════════════════════════════════
# 3. REFINEMENT LOOP — Цикл уточнения
# ═══════════════════════════════════════════════════════════════════════════════


class RefinementLoop:
    """
    Цикл «generate → search → refine → search → ...»

    Каждая итерация:
    1. Анализирует текущий ответ
    2. Находит пробелы
    3. Расширяет запрос
    4. Возвращает уточнённый запрос

    Останавливается при:
    - Достаточной уверенности
    - Исчерпании итераций
    - Отсутствии пробелов
    """

    def __init__(
        self,
        max_iterations: int = 3,
        target_confidence: float = 0.8,
    ):
        self._max_iterations = max_iterations
        self._target_confidence = target_confidence
        self._expander = QueryExpander()
        self._gap_analyzer = GapAnalyzer()
        self._history: list[RefinementStep] = []

    def should_continue(
        self,
        iteration: int,
        confidence: float,
        gaps: list[InformationGap],
    ) -> bool:
        """Нужна ли ещё одна итерация?"""
        if iteration >= self._max_iterations:
            return False
        if confidence >= self._target_confidence:
            return False
        if not gaps:
            return False
        return True

    def refine_query(
        self,
        original_query: str,
        current_answer: str,
        confidence: float,
        iteration: int = 0,
        context: str = "",
    ) -> RefinementStep:
        """
        Одна итерация цикла уточнения.

        Returns: RefinementStep с уточнённым запросом
        """
        gaps = self._gap_analyzer.analyze(
            query=original_query,
            answer=current_answer,
            confidence=confidence,
        )

        if not gaps:
            step = RefinementStep(
                iteration=iteration,
                query=original_query,
                confidence_before=confidence,
                confidence_after=confidence,
            )
            self._history.append(step)
            return step

        top_gap = gaps[0]
        refined_query = top_gap.suggested_query or original_query

        expanded = self._expander.expand(
            refined_query,
            strategy=ExpansionStrategy.CONTEXTUAL,
            context=context,
        )
        if expanded.expanded != refined_query:
            refined_query = expanded.expanded

        step = RefinementStep(
            iteration=iteration,
            query=refined_query,
            gaps_found=gaps,
            confidence_before=confidence,
        )
        self._history.append(step)
        return step

    def get_history(self) -> list[RefinementStep]:
        return list(self._history)

    def clear_history(self) -> None:
        self._history.clear()

    def get_stats(self) -> dict:
        total = len(self._history)
        avg_gaps = (
            sum(len(s.gaps_found) for s in self._history) / total
            if total > 0 else 0
        )
        return {
            "total_refinements": total,
            "max_iterations": self._max_iterations,
            "target_confidence": self._target_confidence,
            "avg_gaps_per_step": round(avg_gaps, 1),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. QUERY OPTIMIZER — Оптимальная формулировка
# ═══════════════════════════════════════════════════════════════════════════════


class QueryOptimizer:
    """
    Оптимизирует запрос для максимальной эффективности поиска.

    - Удаляет шум
    - Выделяет ключевые термины
    - Добавляет контекстные маркеры
    """

    NOISE_WORDS = frozenset({
        "пожалуйста", "скажи", "подскажи", "расскажи",
        "мне", "нужно", "хочу", "узнать", "найти",
        "please", "tell", "find", "show", "need", "want",
        "знаешь", "можешь", "помоги", "help",
    })

    def optimize(self, query: str) -> str:
        """Оптимизировать запрос."""
        words = query.split()
        optimized = [w for w in words if w.lower() not in self.NOISE_WORDS]
        if not optimized:
            return query
        return " ".join(optimized)

    def extract_key_terms(self, query: str) -> list[str]:
        """Извлечь ключевые термины."""
        from pds_ultimate.core.semantic_engine import STOP_WORDS
        tokens = re.findall(r'[а-яёa-z0-9]{2,}', query.lower())
        filtered = [
            t for t in tokens
            if t not in STOP_WORDS and t not in self.NOISE_WORDS
        ]
        counts = Counter(filtered)
        return [w for w, _ in counts.most_common(10)]

    def suggest_alternatives(self, query: str) -> list[str]:
        """Предложить альтернативные формулировки."""
        expander = QueryExpander()
        alternatives = []
        for strategy in [
            ExpansionStrategy.SYNONYM,
            ExpansionStrategy.SPECIFIC,
            ExpansionStrategy.BROAD,
        ]:
            eq = expander.expand(query, strategy=strategy)
            if eq.expanded != query:
                alternatives.append(eq.expanded)
        return alternatives


# ═══════════════════════════════════════════════════════════════════════════════
# FACADE: AdaptiveQueryEngine
# ═══════════════════════════════════════════════════════════════════════════════


class AdaptiveQueryEngine:
    """
    Фасад для адаптивного расширения запросов.

    Использование:
        engine = AdaptiveQueryEngine()

        # Расширить запрос
        expanded = engine.expand("цена товара", context="импорт из Китая")

        # Найти пробелы
        gaps = engine.find_gaps("Какой курс?", "Курс зависит от дня")

        # Полный цикл уточнения
        step = engine.refine("вопрос", "текущий ответ", confidence=0.4)
    """

    def __init__(self):
        self.expander = QueryExpander()
        self.gap_analyzer = GapAnalyzer()
        self.refinement_loop = RefinementLoop()
        self.optimizer = QueryOptimizer()

    def expand(
        self,
        query: str,
        context: str = "",
        strategy: str = "synonym",
    ) -> ExpandedQuery:
        """Расширить запрос."""
        try:
            strat = ExpansionStrategy(strategy)
        except ValueError:
            strat = ExpansionStrategy.SYNONYM
        return self.expander.expand(query, strategy=strat, context=context)

    def expand_multi(
        self,
        query: str,
        context: str = "",
    ) -> list[ExpandedQuery]:
        """Расширить запрос множественными стратегиями."""
        return self.expander.expand_multi(query, context=context)

    def find_gaps(
        self,
        query: str,
        answer: str,
        confidence: float = 0.5,
    ) -> list[InformationGap]:
        """Найти пробелы в ответе."""
        return self.gap_analyzer.analyze(
            query=query, answer=answer, confidence=confidence,
        )

    def refine(
        self,
        query: str,
        answer: str,
        confidence: float = 0.5,
        context: str = "",
    ) -> RefinementStep:
        """Одна итерация уточнения."""
        return self.refinement_loop.refine_query(
            original_query=query,
            current_answer=answer,
            confidence=confidence,
            context=context,
        )

    def optimize(self, query: str) -> str:
        """Оптимизировать запрос."""
        return self.optimizer.optimize(query)

    def get_stats(self) -> dict:
        return {
            "refinement": self.refinement_loop.get_stats(),
            "synonyms_count": len(self.expander.SYNONYMS),
        }


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

adaptive_query = AdaptiveQueryEngine()
