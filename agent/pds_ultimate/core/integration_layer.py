"""
PDS-Ultimate Integration Layer (Part 11)
==========================================
Связывает все 56+ инструментов в единый умный pipeline.

Ключевые возможности:
1. ToolChain — цепочки инструментов с передачей данных между шагами
2. ToolChainRouter — автоматический выбор цепочки по типу запроса
3. FallbackManager — резервные инструменты при сбое основного
4. CircuitBreaker — защита от каскадных ошибок (N сбоев → отключение)
5. RetryPolicy — повтор с exponential backoff + jitter
6. AutoHealer — автоматическое восстановление с альтернативным подходом
7. ResultAggregator — объединение результатов из нескольких tools
8. HealthMonitor — мониторинг здоровья инструментов в реальном времени

Архитектура:
- IntegrationLayer — центральный фасад
- ToolChain вставляется МЕЖДУ agent.py и tools.py
- Не ломает существующий ReAct loop — расширяет его
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

from pds_ultimate.config import logger

# ═══════════════════════════════════════════════════════════════════════════════
# 1. DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════


class ChainStatus(str, Enum):
    """Статус выполнения цепочки."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"       # Часть шагов успешна
    FAILED = "failed"
    ABORTED = "aborted"


class ToolHealth(str, Enum):
    """Здоровье инструмента."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"     # Работает, но медленно / с ошибками
    UNHEALTHY = "unhealthy"   # Отключён circuit breaker
    UNKNOWN = "unknown"


@dataclass
class ChainStep:
    """Один шаг в цепочке инструментов."""
    tool_name: str
    params: dict[str, Any] = field(default_factory=dict)
    # Маппинг: param_name → "prev.field" (из результата предыдущего шага)
    param_mapping: dict[str, str] = field(default_factory=dict)
    # Условие выполнения: "prev.success == True"
    condition: str = ""
    # Можно ли пропустить при ошибке
    optional: bool = False
    # Таймаут для этого шага (секунды)
    timeout: float = 30.0

    def to_dict(self) -> dict:
        return {
            "tool": self.tool_name,
            "params": self.params,
            "mapping": self.param_mapping,
            "optional": self.optional,
            "timeout": self.timeout,
        }


@dataclass
class StepResult:
    """Результат одного шага цепочки."""
    step_index: int
    tool_name: str
    success: bool
    output: str = ""
    data: Any = None
    error: str = ""
    duration_ms: int = 0
    retries: int = 0
    fallback_used: str = ""

    def to_dict(self) -> dict:
        return {
            "step": self.step_index,
            "tool": self.tool_name,
            "success": self.success,
            "output": self.output[:200] if self.output else "",
            "error": self.error,
            "duration_ms": self.duration_ms,
            "retries": self.retries,
            "fallback": self.fallback_used,
        }


@dataclass
class ChainResult:
    """Результат выполнения всей цепочки."""
    chain_id: str
    chain_name: str
    status: ChainStatus
    steps: list[StepResult] = field(default_factory=list)
    total_duration_ms: int = 0
    aggregated_output: str = ""
    aggregated_data: dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if not self.steps:
            return 0.0
        ok = sum(1 for s in self.steps if s.success)
        return ok / len(self.steps)

    @property
    def failed_steps(self) -> list[StepResult]:
        return [s for s in self.steps if not s.success]

    def to_dict(self) -> dict:
        return {
            "chain_id": self.chain_id,
            "name": self.chain_name,
            "status": self.status.value,
            "success_rate": round(self.success_rate, 2),
            "total_duration_ms": self.total_duration_ms,
            "steps_total": len(self.steps),
            "steps_ok": sum(1 for s in self.steps if s.success),
            "aggregated_output": self.aggregated_output[:500],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. TOOL CHAIN — Цепочка инструментов
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ToolChain:
    """
    Определение цепочки инструментов.

    Пример:
        chain = ToolChain(
            name="research_and_summarize",
            steps=[
                ChainStep("web_search", {"query": "AI trends 2026"}),
                ChainStep("summarize_text", param_mapping={"text": "prev.output"}),
                ChainStep("knowledge_add", param_mapping={"content": "prev.output"}),
            ],
        )
    """
    name: str
    description: str = ""
    steps: list[ChainStep] = field(default_factory=list)
    # Условие прерывания: "any_fail" | "all_fail" | "never"
    abort_policy: str = "any_fail"
    # Теги для маршрутизации
    tags: list[str] = field(default_factory=list)

    def add_step(
        self,
        tool_name: str,
        params: dict | None = None,
        param_mapping: dict | None = None,
        condition: str = "",
        optional: bool = False,
        timeout: float = 30.0,
    ) -> "ToolChain":
        """Fluent API для добавления шагов."""
        self.steps.append(ChainStep(
            tool_name=tool_name,
            params=params or {},
            param_mapping=param_mapping or {},
            condition=condition,
            optional=optional,
            timeout=timeout,
        ))
        return self

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "abort_policy": self.abort_policy,
            "tags": self.tags,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. RETRY POLICY — Повтор с backoff
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class RetryPolicy:
    """Политика повторных попыток."""
    max_retries: int = 3
    base_delay: float = 0.5       # Базовая задержка (секунды)
    max_delay: float = 30.0       # Максимальная задержка
    exponential_base: float = 2.0  # Множитель экспоненциального backoff
    jitter: bool = True            # Добавить случайный jitter

    def get_delay(self, attempt: int) -> float:
        """Вычислить задержку для попытки."""
        delay = self.base_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)
        if self.jitter:
            delay *= (0.5 + random.random())
        return delay

    def to_dict(self) -> dict:
        return {
            "max_retries": self.max_retries,
            "base_delay": self.base_delay,
            "max_delay": self.max_delay,
            "exponential_base": self.exponential_base,
            "jitter": self.jitter,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. CIRCUIT BREAKER — Защита от каскадных сбоев
# ═══════════════════════════════════════════════════════════════════════════════


class CircuitBreaker:
    """
    Circuit Breaker для инструмента.

    Состояния:
    - CLOSED: нормальная работа
    - OPEN: инструмент отключён (слишком много сбоев)
    - HALF_OPEN: пробная попытка после recovery_timeout
    """

    class State(str, Enum):
        CLOSED = "closed"
        OPEN = "open"
        HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = self.State.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._total_calls = 0
        self._total_failures = 0

    @property
    def state(self) -> "CircuitBreaker.State":
        if self._state == self.State.OPEN:
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = self.State.HALF_OPEN
                self._success_count = 0
        return self._state

    @property
    def is_available(self) -> bool:
        return self.state != self.State.OPEN

    def record_success(self) -> None:
        """Зарегистрировать успешный вызов."""
        self._total_calls += 1
        self._failure_count = 0

        if self._state == self.State.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._state = self.State.CLOSED
                logger.info("CircuitBreaker: HALF_OPEN → CLOSED")

    def record_failure(self) -> None:
        """Зарегистрировать сбой."""
        self._total_calls += 1
        self._total_failures += 1
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == self.State.HALF_OPEN:
            self._state = self.State.OPEN
            logger.warning("CircuitBreaker: HALF_OPEN → OPEN")
        elif self._failure_count >= self.failure_threshold:
            self._state = self.State.OPEN
            logger.warning(
                f"CircuitBreaker: CLOSED → OPEN "
                f"(failures={self._failure_count})"
            )

    def reset(self) -> None:
        """Сбросить состояние."""
        self._state = self.State.CLOSED
        self._failure_count = 0
        self._success_count = 0

    def get_stats(self) -> dict:
        return {
            "state": self.state.value,
            "failure_count": self._failure_count,
            "total_calls": self._total_calls,
            "total_failures": self._total_failures,
            "failure_rate": (
                round(self._total_failures / self._total_calls, 2)
                if self._total_calls > 0 else 0.0
            ),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. FALLBACK MANAGER — Резервные инструменты
# ═══════════════════════════════════════════════════════════════════════════════


class FallbackManager:
    """
    Менеджер резервных инструментов.

    Если основной инструмент недоступен или сбоит → переключение на запасной.

    Примеры:
    - web_search → web_deep_search → knowledge_search
    - open_page → browser_screenshot
    - convert_currency → exchange_rate → (cached rate)
    """

    def __init__(self):
        self._fallbacks: dict[str, list[str]] = {}
        self._usage_count: dict[str, int] = defaultdict(int)

    def register(self, primary: str, fallbacks: list[str]) -> None:
        """Зарегистрировать fallback-цепочку для инструмента."""
        self._fallbacks[primary] = fallbacks

    def get_fallbacks(self, tool_name: str) -> list[str]:
        """Получить fallback-инструменты."""
        return self._fallbacks.get(tool_name, [])

    def get_next_fallback(
        self, tool_name: str, tried: set[str] | None = None,
    ) -> str | None:
        """Получить следующий не испробованный fallback."""
        tried = tried or set()
        for fb in self.get_fallbacks(tool_name):
            if fb not in tried:
                self._usage_count[fb] += 1
                return fb
        return None

    def register_defaults(self) -> None:
        """Зарегистрировать дефолтные fallback-цепочки."""
        defaults = {
            "web_search": ["web_deep_search", "knowledge_search"],
            "web_deep_search": ["web_search", "knowledge_search"],
            "open_page": ["web_search"],
            "convert_currency": ["get_financial_summary"],
            "create_order": ["save_contact_note"],
            "knowledge_search": ["web_search"],
            "expand_query": ["knowledge_search"],
        }
        for primary, fbs in defaults.items():
            self.register(primary, fbs)

    def get_stats(self) -> dict:
        return {
            "registered": len(self._fallbacks),
            "chains": {k: v for k, v in self._fallbacks.items()},
            "usage": dict(self._usage_count),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 6. HEALTH MONITOR — Мониторинг здоровья инструментов
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ToolMetrics:
    """Метрики одного инструмента."""
    tool_name: str
    total_calls: int = 0
    total_failures: int = 0
    total_duration_ms: int = 0
    last_call_time: float = 0.0
    last_error: str = ""
    response_times: deque = field(
        default_factory=lambda: deque(maxlen=100),
    )

    @property
    def avg_response_ms(self) -> float:
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)

    @property
    def failure_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_failures / self.total_calls

    @property
    def health(self) -> ToolHealth:
        if self.total_calls == 0:
            return ToolHealth.UNKNOWN
        if self.failure_rate > 0.5:
            return ToolHealth.UNHEALTHY
        if self.failure_rate > 0.2 or self.avg_response_ms > 10000:
            return ToolHealth.DEGRADED
        return ToolHealth.HEALTHY

    def record_call(self, success: bool, duration_ms: int, error: str = ""):
        self.total_calls += 1
        self.total_duration_ms += duration_ms
        self.last_call_time = time.time()
        self.response_times.append(duration_ms)
        if not success:
            self.total_failures += 1
            self.last_error = error

    def to_dict(self) -> dict:
        return {
            "tool": self.tool_name,
            "calls": self.total_calls,
            "failures": self.total_failures,
            "failure_rate": round(self.failure_rate, 3),
            "avg_ms": round(self.avg_response_ms, 1),
            "health": self.health.value,
        }


class HealthMonitor:
    """Мониторинг здоровья всех инструментов."""

    def __init__(self):
        self._metrics: dict[str, ToolMetrics] = {}

    def _ensure(self, tool_name: str) -> ToolMetrics:
        if tool_name not in self._metrics:
            self._metrics[tool_name] = ToolMetrics(tool_name=tool_name)
        return self._metrics[tool_name]

    def record(
        self, tool_name: str, success: bool,
        duration_ms: int, error: str = "",
    ) -> None:
        self._ensure(tool_name).record_call(success, duration_ms, error)

    def get_health(self, tool_name: str) -> ToolHealth:
        if tool_name not in self._metrics:
            return ToolHealth.UNKNOWN
        return self._metrics[tool_name].health

    def get_unhealthy(self) -> list[str]:
        return [
            name for name, m in self._metrics.items()
            if m.health == ToolHealth.UNHEALTHY
        ]

    def get_degraded(self) -> list[str]:
        return [
            name for name, m in self._metrics.items()
            if m.health == ToolHealth.DEGRADED
        ]

    def get_all_metrics(self) -> list[dict]:
        return [m.to_dict() for m in self._metrics.values()]

    def get_top_slow(self, n: int = 5) -> list[dict]:
        """Топ N самых медленных инструментов."""
        sorted_tools = sorted(
            self._metrics.values(),
            key=lambda m: m.avg_response_ms,
            reverse=True,
        )
        return [m.to_dict() for m in sorted_tools[:n]]

    def get_top_failing(self, n: int = 5) -> list[dict]:
        """Топ N самых ненадёжных инструментов."""
        sorted_tools = sorted(
            self._metrics.values(),
            key=lambda m: m.failure_rate,
            reverse=True,
        )
        return [m.to_dict() for m in sorted_tools[:n] if m.failure_rate > 0]

    def get_stats(self) -> dict:
        total = len(self._metrics)
        healthy = sum(
            1 for m in self._metrics.values()
            if m.health == ToolHealth.HEALTHY
        )
        return {
            "total_tools_tracked": total,
            "healthy": healthy,
            "degraded": len(self.get_degraded()),
            "unhealthy": len(self.get_unhealthy()),
            "total_calls": sum(m.total_calls for m in self._metrics.values()),
            "total_failures": sum(
                m.total_failures for m in self._metrics.values()
            ),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 7. RESULT AGGREGATOR — Объединение результатов
# ═══════════════════════════════════════════════════════════════════════════════


class ResultAggregator:
    """Объединяет результаты нескольких шагов цепочки."""

    @staticmethod
    def aggregate_text(results: list[StepResult], separator: str = "\n\n") -> str:
        """Объединить текстовые выходы."""
        parts = []
        for r in results:
            if r.success and r.output:
                parts.append(r.output)
        return separator.join(parts)

    @staticmethod
    def aggregate_data(results: list[StepResult]) -> dict[str, Any]:
        """Объединить структурированные данные."""
        merged: dict[str, Any] = {}
        for r in results:
            if r.success and r.data:
                if isinstance(r.data, dict):
                    merged[r.tool_name] = r.data
                else:
                    merged[r.tool_name] = {"value": r.data}
        return merged

    @staticmethod
    def summary(results: list[StepResult]) -> str:
        """Краткая сводка результатов."""
        total = len(results)
        ok = sum(1 for r in results if r.success)
        failed = total - ok
        lines = [f"📊 Результат: {ok}/{total} шагов успешно"]
        if failed > 0:
            for r in results:
                if not r.success:
                    lines.append(f"  ❌ {r.tool_name}: {r.error}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. TOOL CHAIN ROUTER — Маршрутизация по типу запроса
# ═══════════════════════════════════════════════════════════════════════════════


class ToolChainRouter:
    """
    Автоматический подбор цепочки по типу запроса.

    Регистрирует предопределённые цепочки и подбирает
    нужную по ключевым словам / паттернам.
    """

    def __init__(self):
        self._chains: dict[str, ToolChain] = {}
        # Маппинг: keyword → chain_name
        self._keyword_routes: dict[str, str] = {}

    def register_chain(
        self, chain: ToolChain, keywords: list[str] | None = None,
    ) -> None:
        """Зарегистрировать цепочку."""
        self._chains[chain.name] = chain
        if keywords:
            for kw in keywords:
                self._keyword_routes[kw.lower()] = chain.name

    def get_chain(self, name: str) -> ToolChain | None:
        return self._chains.get(name)

    def find_chain(self, query: str) -> ToolChain | None:
        """Найти подходящую цепочку по запросу."""
        lower = query.lower()
        best_match: str | None = None
        best_score = 0

        for keyword, chain_name in self._keyword_routes.items():
            if keyword in lower:
                score = len(keyword)
                if score > best_score:
                    best_score = score
                    best_match = chain_name

        if best_match:
            return self._chains.get(best_match)
        return None

    def list_chains(self) -> list[dict]:
        return [c.to_dict() for c in self._chains.values()]

    def register_defaults(self) -> None:
        """Зарегистрировать дефолтные цепочки."""
        # Цепочка: Исследование + Суммаризация
        research_chain = ToolChain(
            name="research_summarize",
            description="Найти информацию в интернете и суммаризировать",
            tags=["research", "web"],
        ).add_step(
            "web_search", params={},
            param_mapping={"query": "input.query"},
        ).add_step(
            "summarize_text",
            param_mapping={"text": "prev.output"},
        ).add_step(
            "knowledge_add",
            param_mapping={"content": "prev.output"},
            optional=True,
        )
        self.register_chain(research_chain, [
            "исследуй", "найди и суммаризируй", "research",
        ])

        # Цепочка: Проверка уверенности + Доп. поиск
        confidence_chain = ToolChain(
            name="confidence_check_search",
            description="Оценить уверенность и при необходимости искать",
            tags=["confidence", "search"],
        ).add_step(
            "confidence_check",
            param_mapping={"text": "input.text"},
        ).add_step(
            "expand_query",
            param_mapping={"query": "input.query"},
            condition="prev.data.needs_search == True",
            optional=True,
        )
        self.register_chain(confidence_chain, [
            "проверь уверенность", "насколько точно",
        ])

        # Цепочка: Анализ свежести + Обновление
        freshness_chain = ToolChain(
            name="freshness_update",
            description="Проверить свежесть данных и обновить",
            tags=["freshness", "update"],
        ).add_step(
            "check_freshness",
            param_mapping={"text": "input.text"},
        ).add_step(
            "web_search",
            param_mapping={"query": "input.query"},
            condition="prev.data.needs_update == True",
            optional=True,
        )
        self.register_chain(freshness_chain, [
            "проверь актуальность", "данные устарели",
        ])

        # Цепочка: Финансовый отчёт
        finance_chain = ToolChain(
            name="finance_report",
            description="Полный финансовый отчёт",
            tags=["finance"],
        ).add_step(
            "get_financial_summary",
        ).add_step(
            "summarize_text",
            param_mapping={"text": "prev.output"},
            optional=True,
        )
        self.register_chain(finance_chain, [
            "финансовый отчёт", "финансовая сводка",
        ])

    def get_stats(self) -> dict:
        return {
            "total_chains": len(self._chains),
            "keyword_routes": len(self._keyword_routes),
            "chains": list(self._chains.keys()),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 9. CHAIN EXECUTOR — Движок выполнения цепочек
# ═══════════════════════════════════════════════════════════════════════════════


class ChainExecutor:
    """
    Выполняет ToolChain: шаг за шагом с retry, fallback и circuit breaker.
    """

    def __init__(
        self,
        health_monitor: HealthMonitor,
        fallback_manager: FallbackManager,
        circuit_breakers: dict[str, CircuitBreaker] | None = None,
        default_retry: RetryPolicy | None = None,
    ):
        self._health = health_monitor
        self._fallbacks = fallback_manager
        self._breakers = circuit_breakers or {}
        self._default_retry = default_retry or RetryPolicy()
        self._executions: int = 0

    def _get_breaker(self, tool_name: str) -> CircuitBreaker:
        if tool_name not in self._breakers:
            self._breakers[tool_name] = CircuitBreaker()
        return self._breakers[tool_name]

    def _resolve_params(
        self,
        step: ChainStep,
        prev_result: StepResult | None,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Разрешить параметры с маппингом."""
        params = dict(step.params)

        for param_name, mapping in step.param_mapping.items():
            if mapping.startswith("prev.") and prev_result:
                field_name = mapping[5:]  # "prev.output" → "output"
                if field_name == "output":
                    params[param_name] = prev_result.output
                elif field_name == "data":
                    params[param_name] = prev_result.data
                elif prev_result.data and isinstance(prev_result.data, dict):
                    params[param_name] = prev_result.data.get(
                        field_name, "",
                    )
            elif mapping.startswith("input."):
                field_name = mapping[6:]  # "input.query" → "query"
                params[param_name] = input_data.get(field_name, "")

        return params

    def _check_condition(
        self, condition: str, prev_result: StepResult | None,
    ) -> bool:
        """Проверить условие выполнения шага."""
        if not condition:
            return True
        if prev_result is None:
            return True

        # Простой парсер условий
        if "prev.success" in condition:
            if "== True" in condition:
                return prev_result.success
            elif "== False" in condition:
                return not prev_result.success

        if "prev.data." in condition and prev_result.data:
            # "prev.data.needs_search == True"
            try:
                parts = condition.split("==")
                if len(parts) == 2:
                    path = parts[0].strip().replace("prev.data.", "")
                    expected = parts[1].strip()
                    if isinstance(prev_result.data, dict):
                        actual = str(prev_result.data.get(path, ""))
                        return actual == expected
            except Exception:
                pass

        return True

    async def execute_chain(
        self,
        chain: ToolChain,
        tool_executor: Callable[..., Coroutine],
        input_data: dict[str, Any] | None = None,
    ) -> ChainResult:
        """
        Выполнить всю цепочку.

        Args:
            chain: Определение цепочки
            tool_executor: Функция вызова инструмента (обычно tool_registry.execute)
            input_data: Входные данные для маппинга "input.*"

        Returns:
            ChainResult с результатами всех шагов
        """
        chain_id = uuid.uuid4().hex[:10]
        input_data = input_data or {}
        start_time = time.time()
        self._executions += 1

        step_results: list[StepResult] = []
        prev_result: StepResult | None = None
        all_ok = True

        for i, step in enumerate(chain.steps):
            # Проверяем условие
            if not self._check_condition(step.condition, prev_result):
                logger.debug(
                    f"Chain '{chain.name}' step {i} skipped (condition)")
                continue

            # Проверяем circuit breaker
            breaker = self._get_breaker(step.tool_name)
            if not breaker.is_available:
                if step.optional:
                    continue
                # Пробуем fallback
                fb = self._fallbacks.get_next_fallback(step.tool_name)
                if fb:
                    step = ChainStep(
                        tool_name=fb,
                        params=step.params,
                        param_mapping=step.param_mapping,
                        optional=step.optional,
                        timeout=step.timeout,
                    )
                else:
                    result = StepResult(
                        step_index=i,
                        tool_name=step.tool_name,
                        success=False,
                        error="Circuit breaker OPEN, no fallback",
                    )
                    step_results.append(result)
                    all_ok = False
                    if chain.abort_policy == "any_fail":
                        break
                    continue

            # Разрешаем параметры
            params = self._resolve_params(step, prev_result, input_data)

            # Выполняем с retry
            result = await self._execute_with_retry(
                i, step.tool_name, params, tool_executor, step.timeout,
            )

            # Если основной сбой → пробуем fallback
            if not result.success and not step.optional:
                tried = {step.tool_name}
                while True:
                    fb = self._fallbacks.get_next_fallback(
                        step.tool_name, tried,
                    )
                    if not fb:
                        break
                    tried.add(fb)
                    fb_result = await self._execute_with_retry(
                        i, fb, params, tool_executor, step.timeout,
                    )
                    if fb_result.success:
                        fb_result.fallback_used = fb
                        result = fb_result
                        break

            step_results.append(result)
            prev_result = result

            if not result.success:
                all_ok = False
                if chain.abort_policy == "any_fail" and not step.optional:
                    break

        # Агрегация
        total_ms = int((time.time() - start_time) * 1000)

        if all_ok:
            status = ChainStatus.COMPLETED
        elif any(r.success for r in step_results):
            status = ChainStatus.PARTIAL
        else:
            status = ChainStatus.FAILED

        return ChainResult(
            chain_id=chain_id,
            chain_name=chain.name,
            status=status,
            steps=step_results,
            total_duration_ms=total_ms,
            aggregated_output=ResultAggregator.aggregate_text(step_results),
            aggregated_data=ResultAggregator.aggregate_data(step_results),
        )

    async def _execute_with_retry(
        self,
        step_index: int,
        tool_name: str,
        params: dict,
        executor: Callable[..., Coroutine],
        timeout: float,
    ) -> StepResult:
        """Выполнить инструмент с retry и записью метрик."""
        breaker = self._get_breaker(tool_name)
        retries = 0

        for attempt in range(self._default_retry.max_retries + 1):
            step_start = time.time()
            try:
                result = await asyncio.wait_for(
                    executor(tool_name, params),
                    timeout=timeout,
                )
                duration_ms = int((time.time() - step_start) * 1000)

                success = getattr(result, "success", True)
                output = getattr(result, "output", str(result))
                data = getattr(result, "data", None)
                error = getattr(result, "error", "") or ""

                self._health.record(tool_name, success, duration_ms, error)

                if success:
                    breaker.record_success()
                    return StepResult(
                        step_index=step_index,
                        tool_name=tool_name,
                        success=True,
                        output=output,
                        data=data,
                        duration_ms=duration_ms,
                        retries=retries,
                    )
                else:
                    breaker.record_failure()
                    retries += 1
                    if attempt < self._default_retry.max_retries:
                        delay = self._default_retry.get_delay(attempt)
                        await asyncio.sleep(delay)
                    else:
                        return StepResult(
                            step_index=step_index,
                            tool_name=tool_name,
                            success=False,
                            error=error,
                            duration_ms=duration_ms,
                            retries=retries,
                        )

            except asyncio.TimeoutError:
                duration_ms = int((time.time() - step_start) * 1000)
                self._health.record(
                    tool_name, False, duration_ms, "timeout")
                breaker.record_failure()
                retries += 1
                if attempt < self._default_retry.max_retries:
                    delay = self._default_retry.get_delay(attempt)
                    await asyncio.sleep(delay)
                else:
                    return StepResult(
                        step_index=step_index,
                        tool_name=tool_name,
                        success=False,
                        error=f"Timeout after {timeout}s",
                        duration_ms=duration_ms,
                        retries=retries,
                    )

            except Exception as e:
                duration_ms = int((time.time() - step_start) * 1000)
                err = f"{type(e).__name__}: {e}"
                self._health.record(tool_name, False, duration_ms, err)
                breaker.record_failure()
                return StepResult(
                    step_index=step_index,
                    tool_name=tool_name,
                    success=False,
                    error=err,
                    duration_ms=duration_ms,
                    retries=retries,
                )

        # Shouldn't reach here
        return StepResult(
            step_index=step_index,
            tool_name=tool_name,
            success=False,
            error="Max retries exhausted",
            retries=retries,
        )

    def get_stats(self) -> dict:
        return {
            "total_executions": self._executions,
            "breakers": {
                name: b.get_stats()
                for name, b in self._breakers.items()
            },
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 10. AUTO HEALER — Автоматическое восстановление
# ═══════════════════════════════════════════════════════════════════════════════


class AutoHealer:
    """
    Автоматическое восстановление после сбоев.

    Стратегии:
    1. Parameter Refinement — упрощение параметров
    2. Alternative Tool — переключение на другой инструмент
    3. Decompose — разбить на более простые вызовы
    4. Cache Fallback — вернуть кэшированный результат
    """

    class Strategy(str, Enum):
        REFINE_PARAMS = "refine_params"
        ALTERNATIVE = "alternative"
        DECOMPOSE = "decompose"
        CACHE_FALLBACK = "cache_fallback"
        GIVE_UP = "give_up"

    # Ошибка → стратегия
    ERROR_MAP: dict[str, "AutoHealer.Strategy"] = {
        "timeout": Strategy.REFINE_PARAMS,
        "rate_limit": Strategy.CACHE_FALLBACK,
        "rate limit": Strategy.CACHE_FALLBACK,
        "ratelimit": Strategy.CACHE_FALLBACK,
        "validation": Strategy.REFINE_PARAMS,
        "not_found": Strategy.ALTERNATIVE,
        "not found": Strategy.ALTERNATIVE,
        "network": Strategy.CACHE_FALLBACK,
        "permission": Strategy.GIVE_UP,
    }

    def __init__(self):
        self._healings: int = 0
        self._successful_healings: int = 0
        self._cache: dict[str, Any] = {}

    def diagnose(self, tool_name: str, error: str) -> "AutoHealer.Strategy":
        """Диагностировать ошибку и выбрать стратегию."""
        error_lower = error.lower()
        for keyword, strategy in self.ERROR_MAP.items():
            if keyword in error_lower:
                return strategy
        return self.Strategy.ALTERNATIVE

    def refine_params(self, params: dict[str, Any], error: str) -> dict[str, Any]:
        """Упростить параметры для повторной попытки."""
        refined = dict(params)

        error_lower = error.lower()

        # Timeout → уменьшить объём данных
        if "timeout" in error_lower:
            for k, v in refined.items():
                if isinstance(v, str) and len(v) > 200:
                    refined[k] = v[:200]

        # Validation → очистить спецсимволы
        if "validation" in error_lower:
            for k, v in refined.items():
                if isinstance(v, str):
                    refined[k] = "".join(
                        c for c in v if c.isalnum() or c.isspace()
                    )

        return refined

    def cache_result(self, key: str, result: Any) -> None:
        """Сохранить результат в кэш."""
        cache_key = hashlib.md5(key.encode()).hexdigest()[:12]
        self._cache[cache_key] = {
            "result": result,
            "time": time.time(),
        }

    def get_cached(self, key: str, max_age: float = 3600) -> Any | None:
        """Получить кэшированный результат."""
        cache_key = hashlib.md5(key.encode()).hexdigest()[:12]
        entry = self._cache.get(cache_key)
        if entry and (time.time() - entry["time"]) < max_age:
            return entry["result"]
        return None

    def record_healing(self, success: bool) -> None:
        self._healings += 1
        if success:
            self._successful_healings += 1

    def get_stats(self) -> dict:
        return {
            "total_healings": self._healings,
            "successful": self._successful_healings,
            "success_rate": (
                round(self._successful_healings / self._healings, 2)
                if self._healings > 0 else 0.0
            ),
            "cache_size": len(self._cache),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 11. INTEGRATION LAYER — Центральный фасад
# ═══════════════════════════════════════════════════════════════════════════════


class IntegrationLayer:
    """
    Центральный фасад Integration Layer.

    Связывает все компоненты:
    - ToolChainRouter для маршрутизации
    - ChainExecutor для выполнения
    - FallbackManager для резервов
    - HealthMonitor для мониторинга
    - AutoHealer для восстановления
    - CircuitBreaker для защиты

    Использование:
        layer = IntegrationLayer()
        layer.initialize()

        # Выполнить цепочку
        result = await layer.execute_chain("research_summarize", {
            "query": "AI trends 2026",
        })

        # Или авто-маршрутизация
        result = await layer.auto_route("исследуй тренды AI", {
            "query": "AI trends 2026",
        })

        # Или одиночный вызов с retry+fallback+monitoring
        result = await layer.execute_safe("web_search", {"query": "test"})
    """

    def __init__(self):
        self.health_monitor = HealthMonitor()
        self.fallback_manager = FallbackManager()
        self.router = ToolChainRouter()
        self.auto_healer = AutoHealer()
        self._retry_policy = RetryPolicy()

        self._executor = ChainExecutor(
            health_monitor=self.health_monitor,
            fallback_manager=self.fallback_manager,
            default_retry=self._retry_policy,
        )
        self._tool_executor: Callable | None = None
        self._initialized = False

    def initialize(
        self,
        tool_executor: Callable[..., Coroutine] | None = None,
    ) -> None:
        """
        Инициализировать Integration Layer.

        Args:
            tool_executor: Функция для вызова инструментов
                          (по умолчанию tool_registry.execute)
        """
        if tool_executor:
            self._tool_executor = tool_executor
        else:
            from pds_ultimate.core.tools import tool_registry
            self._tool_executor = tool_registry.execute

        self.fallback_manager.register_defaults()
        self.router.register_defaults()
        self._initialized = True
        logger.info("IntegrationLayer инициализирован")

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    # ─── Основные методы ─────────────────────────────────────────────

    async def execute_chain(
        self,
        chain_name: str,
        input_data: dict[str, Any] | None = None,
    ) -> ChainResult:
        """Выполнить именованную цепочку."""
        chain = self.router.get_chain(chain_name)
        if not chain:
            return ChainResult(
                chain_id="error",
                chain_name=chain_name,
                status=ChainStatus.FAILED,
                aggregated_output=f"Цепочка '{chain_name}' не найдена",
            )

        return await self._executor.execute_chain(
            chain, self._tool_executor, input_data,
        )

    async def auto_route(
        self,
        query: str,
        input_data: dict[str, Any] | None = None,
    ) -> ChainResult | None:
        """Автоматически найти и выполнить подходящую цепочку."""
        chain = self.router.find_chain(query)
        if not chain:
            return None

        input_data = input_data or {}
        if "query" not in input_data:
            input_data["query"] = query

        return await self._executor.execute_chain(
            chain, self._tool_executor, input_data,
        )

    async def execute_safe(
        self,
        tool_name: str,
        params: dict[str, Any] | None = None,
        db_session: Any = None,
    ) -> StepResult:
        """
        Выполнить один инструмент с retry, fallback, circuit breaker.

        Это обёртка для единичного вызова — используется вместо
        прямого tool_registry.execute() когда нужна устойчивость.
        """
        params = params or {}
        chain = ToolChain(
            name=f"safe_{tool_name}",
            steps=[ChainStep(tool_name=tool_name, params=params)],
            abort_policy="any_fail",
        )

        async def executor(name: str, p: dict) -> Any:
            return await self._tool_executor(name, p, db_session)

        result = await self._executor.execute_chain(
            chain, executor, {},
        )
        if result.steps:
            return result.steps[0]
        return StepResult(
            step_index=0,
            tool_name=tool_name,
            success=False,
            error="No steps executed",
        )

    async def execute_parallel(
        self,
        tool_calls: list[tuple[str, dict]],
        max_concurrent: int = 5,
    ) -> list[StepResult]:
        """
        Выполнить несколько инструментов параллельно.

        Args:
            tool_calls: Список (tool_name, params)
            max_concurrent: Максимум параллельных вызовов

        Returns:
            Список результатов (в том же порядке)
        """
        sem = asyncio.Semaphore(max_concurrent)

        async def run_one(idx: int, name: str, params: dict) -> StepResult:
            async with sem:
                return await self.execute_safe(name, params)

        tasks = [
            run_one(i, name, params)
            for i, (name, params) in enumerate(tool_calls)
        ]
        return list(await asyncio.gather(*tasks))

    # ─── Custom chains ───────────────────────────────────────────────

    def register_chain(
        self, chain: ToolChain, keywords: list[str] | None = None,
    ) -> None:
        """Зарегистрировать пользовательскую цепочку."""
        self.router.register_chain(chain, keywords)

    def create_chain(self, name: str, description: str = "") -> ToolChain:
        """Создать новую пустую цепочку (fluent API)."""
        return ToolChain(name=name, description=description)

    # ─── Диагностика ─────────────────────────────────────────────────

    def get_health_report(self) -> dict:
        """Отчёт о здоровье всех инструментов."""
        return {
            "monitor": self.health_monitor.get_stats(),
            "unhealthy_tools": self.health_monitor.get_unhealthy(),
            "degraded_tools": self.health_monitor.get_degraded(),
            "top_slow": self.health_monitor.get_top_slow(3),
            "top_failing": self.health_monitor.get_top_failing(3),
        }

    def get_stats(self) -> dict:
        return {
            "initialized": self._initialized,
            "health": self.health_monitor.get_stats(),
            "fallbacks": self.fallback_manager.get_stats(),
            "router": self.router.get_stats(),
            "executor": self._executor.get_stats(),
            "healer": self.auto_healer.get_stats(),
        }


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

integration_layer = IntegrationLayer()
