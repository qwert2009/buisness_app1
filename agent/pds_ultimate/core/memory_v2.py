"""
PDS-Ultimate Memory v2 (Part 8)
==================================
Память нового поколения — стратегическая, адаптивная, обучающаяся.

Дополняет существующие memory.py и advanced_memory_manager.py:

1. Strategic Memory — агент учится стратегически, выделяя паттерны
2. Failure-Driven Learning v2 — обучение на ошибках с классификацией
3. Embedding-ready Memory — подготовлена для vector search
4. Memory Consolidation — объединение похожих воспоминаний
5. Adaptive Recall — релевантность зависит от контекста и времени
6. Memory Pruning v2 — умное удаление с учётом важности
7. Cross-session Learning — обучение между сессиями
8. Emotional Memory Tags — воспоминания с эмоциональной окраской
9. Skill Library — сохранение и переиспользование успешных стратегий
10. Context Window Optimizer — оптимальное использование контекста LLM
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pds_ultimate.config import logger

# ═══════════════════════════════════════════════════════════════════════════════
# SKILL LIBRARY — Сохранение успешных стратегий
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class Skill:
    """
    Навык/стратегия, которую агент выучил.

    Пример:
    - Навык: "Конвертация валют TMT → USD"
    - Паттерн: "конверт|курс|TMT|манат"
    - Стратегия: "Использовать exchange_rates с from=TMT, to=USD"
    - Успешность: 95% (19/20 успешных применений)
    """
    id: str = ""
    name: str = ""
    description: str = ""
    pattern: str = ""              # Regex паттерн для активации
    strategy: str = ""             # Описание стратегии
    tools_used: list[str] = field(default_factory=list)
    success_count: int = 0
    failure_count: int = 0
    last_used: datetime = field(default_factory=datetime.utcnow)
    created_at: datetime = field(default_factory=datetime.utcnow)
    tags: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total

    @property
    def total_uses(self) -> int:
        return self.success_count + self.failure_count

    def matches(self, text: str) -> bool:
        """Проверить, подходит ли навык для текста."""
        if not self.pattern:
            return False
        try:
            return bool(re.search(self.pattern, text.lower()))
        except re.error:
            return False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "strategy": self.strategy,
            "success_rate": f"{self.success_rate:.0%}",
            "total_uses": self.total_uses,
            "tools": self.tools_used,
            "tags": self.tags,
        }


class SkillLibrary:
    """Библиотека навыков агента."""

    def __init__(self):
        self._skills: dict[str, Skill] = {}
        self._skill_counter: int = 0

    def add_skill(
        self,
        name: str,
        description: str = "",
        pattern: str = "",
        strategy: str = "",
        tools_used: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Skill:
        """Добавить навык."""
        self._skill_counter += 1
        skill_id = f"skill_{self._skill_counter}"

        skill = Skill(
            id=skill_id,
            name=name,
            description=description,
            pattern=pattern,
            strategy=strategy,
            tools_used=tools_used or [],
            tags=tags or [],
        )

        self._skills[skill_id] = skill
        logger.debug(f"Skill added: {name} (pattern={pattern})")
        return skill

    def find_matching(self, text: str, min_success_rate: float = 0.5) -> list[Skill]:
        """Найти подходящие навыки для текста."""
        matches = []
        for skill in self._skills.values():
            if skill.matches(text) and skill.success_rate >= min_success_rate:
                matches.append(skill)

        # Сортируем по успешности
        return sorted(matches, key=lambda s: s.success_rate, reverse=True)

    def record_usage(self, skill_id: str, success: bool) -> None:
        """Записать использование навыка."""
        skill = self._skills.get(skill_id)
        if not skill:
            return

        if success:
            skill.success_count += 1
        else:
            skill.failure_count += 1
        skill.last_used = datetime.utcnow()

    def get_skill(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def remove_skill(self, skill_id: str) -> bool:
        return self._skills.pop(skill_id, None) is not None

    @property
    def count(self) -> int:
        return len(self._skills)

    def get_top_skills(self, limit: int = 10) -> list[Skill]:
        """Самые успешные навыки."""
        skills = list(self._skills.values())
        return sorted(
            skills,
            key=lambda s: (s.success_rate, s.total_uses),
            reverse=True,
        )[:limit]

    def to_context(self, text: str, max_skills: int = 5) -> str:
        """Сформировать контекст навыков для LLM."""
        matching = self.find_matching(text)[:max_skills]
        if not matching:
            return ""

        lines = ["🎓 РЕЛЕВАНТНЫЕ НАВЫКИ (используй их):"]
        for skill in matching:
            lines.append(
                f"  • {skill.name} (успех {skill.success_rate:.0%}): "
                f"{skill.strategy}"
            )

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# FAILURE LEARNING v2 — Продвинутое обучение на ошибках
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class FailureRecord:
    """Запись об ошибке для обучения."""
    id: str = ""
    error_type: str = ""           # classification: tool_error, logic_error, data_error
    query: str = ""                # Запрос, который привёл к ошибке
    error_message: str = ""
    context: str = ""              # Контекст ошибки
    correction: str = ""           # Правильное действие
    severity: str = "medium"       # low, medium, high, critical
    tool_involved: str = ""        # Какой инструмент сломался
    timestamp: datetime = field(default_factory=datetime.utcnow)
    applied_count: int = 0         # Сколько раз урок применён

    def to_dict(self) -> dict:
        return {
            "error_type": self.error_type,
            "query": self.query[:100],
            "error": self.error_message[:200],
            "correction": self.correction[:200],
            "severity": self.severity,
            "tool": self.tool_involved,
            "applied": self.applied_count,
        }


class FailureLearningEngine:
    """
    Движок обучения на ошибках.

    Процесс:
    1. Ошибка произошла → классифицируем
    2. Определяем коррекцию
    3. Сохраняем в base
    4. При похожем запросе → подгружаем уроки
    5. Отслеживаем: помог ли урок?
    """

    # Классификация ошибок по паттернам
    ERROR_PATTERNS: dict[str, str] = {
        r"timeout|timed out": "timeout_error",
        r"not found|404|не найден": "not_found_error",
        r"permission|403|запрещен": "permission_error",
        r"rate.?limit|429|слишком.?часто": "rate_limit_error",
        r"parse|json|syntax": "parse_error",
        r"network|connection|connect": "network_error",
        r"memory|overflow|out.?of": "resource_error",
        r"invalid|validation|невалидн": "validation_error",
    }

    def __init__(self):
        self._failures: list[FailureRecord] = []
        self._failure_counter: int = 0

    def record_failure(
        self,
        query: str,
        error_message: str,
        context: str = "",
        correction: str = "",
        tool_involved: str = "",
        severity: str = "medium",
    ) -> FailureRecord:
        """Записать ошибку."""
        self._failure_counter += 1

        # Автоклассификация
        error_type = self._classify_error(error_message)

        record = FailureRecord(
            id=f"fail_{self._failure_counter}",
            error_type=error_type,
            query=query,
            error_message=error_message,
            context=context,
            correction=correction,
            severity=severity,
            tool_involved=tool_involved,
        )

        self._failures.append(record)

        # Ограничиваем размер
        if len(self._failures) > 500:
            # Удаляем старые низкоприоритетные
            self._failures = sorted(
                self._failures,
                key=lambda f: (
                    f.severity == "critical",
                    f.severity == "high",
                    f.applied_count > 0,
                    f.timestamp,
                ),
                reverse=True,
            )[:300]

        logger.debug(f"Failure recorded: {error_type} for «{query[:50]}»")
        return record

    def get_relevant_lessons(
        self,
        query: str,
        tool: str = "",
        limit: int = 3,
    ) -> list[FailureRecord]:
        """Получить релевантные уроки для текущего запроса."""
        if not self._failures:
            return []

        scored: list[tuple[float, FailureRecord]] = []

        query_words = set(re.findall(r'\w{3,}', query.lower()))

        for record in self._failures:
            score = 0.0

            # Совпадение инструмента
            if tool and record.tool_involved == tool:
                score += 0.4

            # Совпадение слов запроса
            record_words = set(re.findall(r'\w{3,}', record.query.lower()))
            if query_words and record_words:
                overlap = len(query_words & record_words) / \
                    max(len(query_words), 1)
                score += overlap * 0.3

            # Тип ошибки (частые ошибки важнее)
            type_counts = Counter(f.error_type for f in self._failures)
            type_freq = type_counts.get(
                record.error_type, 0) / len(self._failures)
            score += type_freq * 0.2

            # Severity
            severity_weights = {"critical": 0.3,
                                "high": 0.2, "medium": 0.1, "low": 0.05}
            score += severity_weights.get(record.severity, 0.1)

            # Наличие коррекции
            if record.correction:
                score += 0.2

            if score > 0.2:
                scored.append((score, record))

        # Сортируем по релевантности
        scored.sort(key=lambda x: x[0], reverse=True)

        results = [record for _, record in scored[:limit]]

        # Обновляем applied_count
        for r in results:
            r.applied_count += 1

        return results

    def to_context(self, query: str, tool: str = "") -> str:
        """Сформировать контекст уроков для LLM."""
        lessons = self.get_relevant_lessons(query, tool)
        if not lessons:
            return ""

        lines = ["⚠️ УРОКИ ИЗ ПРОШЛЫХ ОШИБОК (НЕ ПОВТОРЯЙ):"]
        for lesson in lessons:
            lines.append(
                f"  • [{lesson.error_type}] {lesson.error_message[:100]}")
            if lesson.correction:
                lines.append(f"    → Правильно: {lesson.correction[:100]}")

        return "\n".join(lines)

    def _classify_error(self, error_message: str) -> str:
        """Классифицировать ошибку."""
        lower = error_message.lower()
        for pattern, error_type in self.ERROR_PATTERNS.items():
            if re.search(pattern, lower):
                return error_type
        return "unknown_error"

    @property
    def total_failures(self) -> int:
        return len(self._failures)

    def get_stats(self) -> dict[str, Any]:
        """Статистика ошибок."""
        if not self._failures:
            return {"total": 0, "by_type": {}, "by_severity": {}}

        return {
            "total": len(self._failures),
            "by_type": dict(Counter(f.error_type for f in self._failures)),
            "by_severity": dict(Counter(f.severity for f in self._failures)),
            "with_correction": sum(1 for f in self._failures if f.correction),
            "applied": sum(1 for f in self._failures if f.applied_count > 0),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# STRATEGIC MEMORY — Паттерны и стратегическое мышление
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class StrategicPattern:
    """Стратегический паттерн, выявленный агентом."""
    id: str = ""
    name: str = ""
    description: str = ""
    evidence: list[str] = field(default_factory=list)  # Примеры
    confidence: float = 0.5
    category: str = ""  # user_preference, business_pattern, workflow
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "confidence": round(self.confidence, 2),
            "category": self.category,
            "evidence_count": len(self.evidence),
        }


class StrategicMemory:
    """
    Стратегическая память — выявление и хранение паттернов.

    Агент учится:
    - Предпочтения пользователя (всегда выбирает X)
    - Бизнес-паттерны (заказы обычно на сумму Y)
    - Workflow (после X всегда делает Y)
    - Временные паттерны (по понедельникам всегда Z)
    """

    def __init__(self):
        self._patterns: dict[str, StrategicPattern] = {}
        self._observations: list[dict[str, Any]] = []
        self._pattern_counter: int = 0

    def add_observation(
        self,
        action: str,
        context: str = "",
        result: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Записать наблюдение для анализа паттернов."""
        self._observations.append({
            "action": action,
            "context": context,
            "result": result,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Ограничиваем
        if len(self._observations) > 1000:
            self._observations = self._observations[-500:]

    def extract_patterns(self, min_occurrences: int = 3) -> list[StrategicPattern]:
        """
        Извлечь паттерны из накопленных наблюдений.

        Простая эвристика: группируем по action + ищем повторы.
        """
        if len(self._observations) < min_occurrences:
            return []

        # Группируем по действиям
        action_groups: dict[str, list[dict]] = defaultdict(list)
        for obs in self._observations:
            action_groups[obs["action"]].append(obs)

        new_patterns: list[StrategicPattern] = []

        for action, group in action_groups.items():
            if len(group) >= min_occurrences:
                # Проверяем, нет ли уже такого паттерна
                existing = self._find_pattern_by_action(action)
                if existing:
                    existing.evidence.append(
                        f"Повторено x{len(group)}"
                    )
                    existing.confidence = min(1.0, existing.confidence + 0.05)
                    existing.updated_at = datetime.utcnow()
                else:
                    self._pattern_counter += 1
                    pattern = StrategicPattern(
                        id=f"pat_{self._pattern_counter}",
                        name=f"Паттерн: {action}",
                        description=f"Действие '{action}' повторяется {len(group)} раз",
                        evidence=[obs.get("context", "")[:100]
                                  for obs in group[:5]],
                        confidence=min(1.0, len(group) / 10),
                        category="workflow",
                    )
                    self._patterns[pattern.id] = pattern
                    new_patterns.append(pattern)

        return new_patterns

    def get_relevant_patterns(self, context: str, limit: int = 5) -> list[StrategicPattern]:
        """Получить релевантные паттерны."""
        if not self._patterns:
            return []

        context_words = set(re.findall(r'\w{3,}', context.lower()))

        scored: list[tuple[float, StrategicPattern]] = []
        for pattern in self._patterns.values():
            pattern_words = set(re.findall(
                r'\w{3,}',
                f"{pattern.name} {pattern.description}".lower()
            ))

            if not pattern_words:
                continue

            overlap = len(context_words & pattern_words) / \
                max(len(pattern_words), 1)
            score = overlap * pattern.confidence

            if score > 0.1:
                scored.append((score, pattern))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:limit]]

    def to_context(self, query: str) -> str:
        """Сформировать контекст паттернов для LLM."""
        patterns = self.get_relevant_patterns(query)
        if not patterns:
            return ""

        lines = ["📊 СТРАТЕГИЧЕСКИЕ ПАТТЕРНЫ:"]
        for p in patterns:
            lines.append(f"  • {p.name} (уверенность {p.confidence:.0%})")
            if p.description:
                lines.append(f"    {p.description[:100]}")

        return "\n".join(lines)

    def _find_pattern_by_action(self, action: str) -> StrategicPattern | None:
        """Найти паттерн по действию."""
        for p in self._patterns.values():
            if action.lower() in p.name.lower():
                return p
        return None

    @property
    def pattern_count(self) -> int:
        return len(self._patterns)


# ═══════════════════════════════════════════════════════════════════════════════
# CONTEXT WINDOW OPTIMIZER — Оптимальное использование контекста LLM
# ═══════════════════════════════════════════════════════════════════════════════


class ContextWindowOptimizer:
    """
    Оптимизатор контекстного окна LLM.

    Задача: уместить максимум полезной информации
    в ограниченное контекстное окно.

    Приоритеты:
    1. System prompt + tools (неизменно)
    2. Текущий запрос пользователя
    3. Релевантные навыки и уроки
    4. Недавняя память (последние сообщения)
    5. Стратегические паттерны
    6. Общие знания
    """

    # Бюджет символов для каждого блока (примерно)
    DEFAULT_BUDGET: dict[str, int] = {
        "system": 3000,
        "tools": 2000,
        "query": 500,
        "skills": 500,
        "failures": 500,
        "memory": 1500,
        "patterns": 300,
        "history": 2000,
    }

    def __init__(self, max_tokens: int = 8000):
        self.max_chars = max_tokens * 3  # Примерно 3 символа на токен
        self.budget = dict(self.DEFAULT_BUDGET)

    def optimize(
        self,
        blocks: dict[str, str],
        priorities: dict[str, int] | None = None,
    ) -> dict[str, str]:
        """
        Оптимизировать блоки контекста.

        Args:
            blocks: {"system": "...", "memory": "...", ...}
            priorities: {"system": 10, "memory": 5, ...}

        Returns:
            Оптимизированные блоки (обрезанные при необходимости)
        """
        priorities = priorities or {
            "system": 10,
            "tools": 9,
            "query": 8,
            "skills": 7,
            "failures": 6,
            "memory": 5,
            "patterns": 4,
            "history": 3,
        }

        # Общий размер
        total = sum(len(v) for v in blocks.values())

        if total <= self.max_chars:
            return blocks  # Всё помещается

        # Нужно урезать — начинаем с низкоприоритетных
        sorted_blocks = sorted(
            blocks.items(),
            key=lambda x: priorities.get(x[0], 0),
        )

        remaining = self.max_chars
        result: dict[str, str] = {}

        # Сначала выделяем место для высокоприоритетных
        for name, content in reversed(sorted_blocks):
            budget = self.budget.get(name, 500)
            actual = min(len(content), budget)
            remaining -= actual

        # Теперь распределяем
        remaining = self.max_chars
        for name, content in reversed(sorted_blocks):
            budget = self.budget.get(name, 500)

            if remaining <= 0:
                result[name] = ""
                continue

            if len(content) <= budget:
                result[name] = content
                remaining -= len(content)
            else:
                # Обрезаем
                result[name] = content[:min(budget, remaining)] + "..."
                remaining -= min(budget, remaining)

        return result

    def estimate_tokens(self, text: str) -> int:
        """Примерная оценка токенов."""
        # Простая эвристика: ~3 символа на токен для русского
        return len(text) // 3


# ═══════════════════════════════════════════════════════════════════════════════
# MEMORY V2 ENGINE — Объединение
# ═══════════════════════════════════════════════════════════════════════════════


class MemoryV2Engine:
    """
    Память нового поколения.

    Объединяет:
    - Skill Library (навыки)
    - Failure Learning (уроки ошибок)
    - Strategic Memory (паттерны)
    - Context Optimizer (оптимизация окна)
    """

    def __init__(self):
        self.skills = SkillLibrary()
        self.failures = FailureLearningEngine()
        self.strategic = StrategicMemory()
        self.optimizer = ContextWindowOptimizer()

    def get_full_context(self, query: str, tool: str = "") -> str:
        """
        Получить полный контекст памяти для запроса.

        Включает: навыки + уроки + паттерны.
        """
        parts = []

        skills_ctx = self.skills.to_context(query)
        if skills_ctx:
            parts.append(skills_ctx)

        failures_ctx = self.failures.to_context(query, tool)
        if failures_ctx:
            parts.append(failures_ctx)

        patterns_ctx = self.strategic.to_context(query)
        if patterns_ctx:
            parts.append(patterns_ctx)

        return "\n\n".join(parts)

    def record_success(
        self,
        query: str,
        tools_used: list[str],
        strategy: str = "",
    ) -> None:
        """Записать успешное выполнение."""
        # Обновляем навыки
        for skill in self.skills.find_matching(query):
            self.skills.record_usage(skill.id, success=True)

        # Наблюдение для стратегической памяти
        self.strategic.add_observation(
            action=f"success:{','.join(tools_used)}",
            context=query,
            result="success",
        )

    def record_failure(
        self,
        query: str,
        error: str,
        tool: str = "",
        correction: str = "",
    ) -> None:
        """Записать ошибку."""
        self.failures.record_failure(
            query=query,
            error_message=error,
            tool_involved=tool,
            correction=correction,
        )

        # Обновляем навыки
        for skill in self.skills.find_matching(query):
            self.skills.record_usage(skill.id, success=False)

    def learn_skill(
        self,
        name: str,
        pattern: str,
        strategy: str,
        tools: list[str] | None = None,
    ) -> Skill:
        """Добавить новый навык."""
        return self.skills.add_skill(
            name=name,
            pattern=pattern,
            strategy=strategy,
            tools_used=tools or [],
        )

    def analyze_patterns(self) -> list[StrategicPattern]:
        """Запустить анализ стратегических паттернов."""
        return self.strategic.extract_patterns()

    def get_stats(self) -> dict[str, Any]:
        """Статистика памяти v2."""
        return {
            "skills": self.skills.count,
            "failures": self.failures.total_failures,
            "patterns": self.strategic.pattern_count,
            "failure_stats": self.failures.get_stats(),
            "top_skills": [
                s.to_dict() for s in self.skills.get_top_skills(5)
            ],
        }


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

memory_v2 = MemoryV2Engine()
