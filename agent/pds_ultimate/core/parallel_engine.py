"""
PDS-Ultimate Parallel Execution Engine
=========================================
Параллельное выполнение задач и проверка гипотез.

Компоненты:
1. ParallelDAGExecutor — параллельное выполнение узлов DAG
2. ParallelHypothesisChecker — одновременная проверка нескольких гипотез
3. ConcurrencyManager — управление параллелизмом и semaphore
4. TaskBatchQueue — batch-очередь для группировки похожих задач

Использует asyncio.gather + Semaphore для контроля нагрузки.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

from pds_ultimate.config import logger

# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class HypothesisStatus(str, Enum):
    """Статус гипотезы."""
    PENDING = "pending"
    CHECKING = "checking"
    CONFIRMED = "confirmed"
    REFUTED = "refuted"
    UNCERTAIN = "uncertain"
    ERROR = "error"


@dataclass
class Hypothesis:
    """Гипотеза для параллельной проверки."""
    id: str
    statement: str
    sources: list[str] = field(default_factory=list)
    status: HypothesisStatus = HypothesisStatus.PENDING
    confidence: float = 0.0
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)
    check_result: str | None = None
    checked_at: float | None = None

    @property
    def is_checked(self) -> bool:
        return self.status not in (
            HypothesisStatus.PENDING, HypothesisStatus.CHECKING
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "statement": self.statement,
            "status": self.status.value,
            "confidence": round(self.confidence, 2),
            "evidence_for": len(self.evidence_for),
            "evidence_against": len(self.evidence_against),
        }


@dataclass
class ParallelResult:
    """Результат параллельного выполнения."""
    task_id: str
    success: bool
    result: Any = None
    error: str | None = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "duration_ms": round(self.duration_ms, 1),
            "error": self.error,
        }


@dataclass
class BatchTask:
    """Задача в batch-очереди."""
    id: str
    category: str
    coro_factory: Callable[[], Coroutine]
    priority: int = 0
    created_at: float = field(default_factory=time.time)
    future: asyncio.Future | None = None


@dataclass
class ExecutionStats:
    """Статистика параллельного исполнения."""
    total_tasks: int = 0
    parallel_tasks: int = 0
    sequential_tasks: int = 0
    total_time_saved_ms: float = 0.0
    max_concurrency_reached: int = 0
    batch_runs: int = 0

    def to_dict(self) -> dict:
        return {
            "total_tasks": self.total_tasks,
            "parallel_tasks": self.parallel_tasks,
            "sequential_tasks": self.sequential_tasks,
            "time_saved_ms": round(self.total_time_saved_ms, 1),
            "max_concurrency": self.max_concurrency_reached,
            "batch_runs": self.batch_runs,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CONCURRENCY MANAGER
# ═══════════════════════════════════════════════════════════════════════════════


class ConcurrencyManager:
    """
    Управление параллелизмом через Semaphore.

    Контролирует:
    - Макс. количество одновременных задач
    - Макс. одновременных LLM запросов
    - Макс. одновременных browser сессий
    """

    def __init__(
        self,
        max_concurrent: int = 10,
        max_llm_concurrent: int = 5,
        max_browser_concurrent: int = 3,
    ):
        self._max_concurrent = max_concurrent
        self._general_sem = asyncio.Semaphore(max_concurrent)
        self._llm_sem = asyncio.Semaphore(max_llm_concurrent)
        self._browser_sem = asyncio.Semaphore(max_browser_concurrent)
        self._active_count = 0
        self._peak_count = 0

    @property
    def active_count(self) -> int:
        return self._active_count

    @property
    def peak_count(self) -> int:
        return self._peak_count

    async def acquire(self, category: str = "general") -> None:
        """Запросить слот для выполнения."""
        if category == "llm":
            await self._llm_sem.acquire()
        elif category == "browser":
            await self._browser_sem.acquire()
        await self._general_sem.acquire()
        self._active_count += 1
        self._peak_count = max(self._peak_count, self._active_count)

    def release(self, category: str = "general") -> None:
        """Освободить слот."""
        self._general_sem.release()
        if category == "llm":
            self._llm_sem.release()
        elif category == "browser":
            self._browser_sem.release()
        self._active_count = max(0, self._active_count - 1)

    async def run_limited(
        self,
        coro: Coroutine,
        category: str = "general",
    ) -> Any:
        """Выполнить coroutine с ограничением параллелизма."""
        await self.acquire(category)
        try:
            return await coro
        finally:
            self.release(category)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. PARALLEL DAG EXECUTOR
# ═══════════════════════════════════════════════════════════════════════════════


class ParallelDAGExecutor:
    """
    Параллельное выполнение узлов DAG.

    Алгоритм:
    1. Получить ready nodes (все зависимости выполнены)
    2. Запустить их ПАРАЛЛЕЛЬНО через asyncio.gather
    3. По завершении — обновить статусы и найти новые ready
    4. Повторять до завершения всех узлов

    Экономит время: вместо последовательного A→B→C→D,
    выполняет параллельно [A,B] → [C] → [D] если A,B независимы.
    """

    def __init__(
        self,
        concurrency: ConcurrencyManager | None = None,
        max_parallel: int = 5,
    ):
        self._concurrency = concurrency or ConcurrencyManager(
            max_concurrent=max_parallel
        )
        self._stats = ExecutionStats()

    async def execute_dag(
        self,
        plan,  # DAGPlan
        executor: Callable[[str, str | None, dict | None], Coroutine],
    ) -> list[ParallelResult]:
        """
        Выполнить DAG-план параллельно.

        Args:
            plan: DAGPlan из cognitive_engine
            executor: async func(node_id, tool_name, tool_params) → result

        Returns:
            Список ParallelResult для всех узлов
        """
        all_results: list[ParallelResult] = []
        start_time = time.time()

        while not plan.is_complete:
            ready = plan.get_ready_nodes()
            if not ready:
                # Нет ready — возможно цикл или все завершены
                break

            # Параллельный запуск всех ready узлов
            if len(ready) > 1:
                self._stats.parallel_tasks += len(ready)
                logger.debug(
                    f"DAG parallel: запуск {len(ready)} узлов: "
                    f"{[n.id for n in ready]}"
                )

                # Помечаем все как running
                for node in ready:
                    plan.mark_running(node.id)

                # Параллельное выполнение
                tasks = [
                    self._execute_node(plan, node, executor)
                    for node in ready
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for r in results:
                    if isinstance(r, ParallelResult):
                        all_results.append(r)
                    elif isinstance(r, Exception):
                        logger.error(f"DAG parallel error: {r}")
            else:
                # Один узел — последовательно
                self._stats.sequential_tasks += 1
                node = ready[0]
                plan.mark_running(node.id)
                result = await self._execute_node(plan, node, executor)
                all_results.append(result)

            self._stats.total_tasks = len(all_results)

        # Считаем экономию времени
        total_sequential = sum(r.duration_ms for r in all_results)
        actual_time = (time.time() - start_time) * 1000
        self._stats.total_time_saved_ms += max(0,
                                               total_sequential - actual_time)
        self._stats.max_concurrency_reached = max(
            self._stats.max_concurrency_reached,
            self._concurrency.peak_count,
        )

        return all_results

    async def _execute_node(
        self,
        plan,
        node,
        executor: Callable,
    ) -> ParallelResult:
        """Выполнить один узел DAG."""
        start = time.time()

        try:
            result = await self._concurrency.run_limited(
                executor(node.id, node.tool_name, node.tool_params),
                category="llm" if not node.tool_name else "general",
            )

            duration = (time.time() - start) * 1000
            plan.complete_node(node.id, str(result))

            return ParallelResult(
                task_id=node.id,
                success=True,
                result=result,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            error_msg = f"{type(e).__name__}: {e}"

            can_retry = plan.fail_node(node.id, error_msg)
            if can_retry:
                logger.info(f"DAG node '{node.id}' retry scheduled")

            return ParallelResult(
                task_id=node.id,
                success=False,
                error=error_msg,
                duration_ms=duration,
            )

    @property
    def stats(self) -> ExecutionStats:
        return self._stats


# ═══════════════════════════════════════════════════════════════════════════════
# 3. PARALLEL HYPOTHESIS CHECKER
# ═══════════════════════════════════════════════════════════════════════════════


class ParallelHypothesisChecker:
    """
    Параллельная проверка нескольких гипотез.

    Вместо последовательной проверки H1 → H2 → H3,
    проверяем [H1, H2, H3] одновременно через asyncio.gather.

    Используется в InternetReasoningEngine для fact-checking.
    """

    def __init__(
        self,
        concurrency: ConcurrencyManager | None = None,
        max_parallel: int = 5,
    ):
        self._concurrency = concurrency or ConcurrencyManager(
            max_concurrent=max_parallel, max_llm_concurrent=max_parallel
        )
        self._checked_count = 0

    async def check_hypotheses(
        self,
        hypotheses: list[Hypothesis],
        checker: Callable[[Hypothesis], Coroutine[Any, Any, Hypothesis]],
    ) -> list[Hypothesis]:
        """
        Проверить все гипотезы параллельно.

        Args:
            hypotheses: Список гипотез
            checker: async func(hypothesis) → updated hypothesis

        Returns:
            Обновлённый список гипотез с результатами
        """
        if not hypotheses:
            return []

        # Помечаем все как checking
        for h in hypotheses:
            h.status = HypothesisStatus.CHECKING

        logger.debug(
            f"Checking {len(hypotheses)} hypotheses in parallel"
        )

        tasks = [
            self._check_one(h, checker) for h in hypotheses
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        checked: list[Hypothesis] = []
        for i, result in enumerate(results):
            if isinstance(result, Hypothesis):
                checked.append(result)
            elif isinstance(result, Exception):
                h = hypotheses[i]
                h.status = HypothesisStatus.ERROR
                h.check_result = str(result)
                checked.append(h)
            else:
                checked.append(hypotheses[i])

        self._checked_count += len(checked)
        return checked

    async def _check_one(
        self,
        hypothesis: Hypothesis,
        checker: Callable,
    ) -> Hypothesis:
        """Проверить одну гипотезу."""
        start = time.time()

        try:
            result = await self._concurrency.run_limited(
                checker(hypothesis),
                category="llm",
            )
            result.checked_at = time.time()
            return result
        except Exception as e:
            hypothesis.status = HypothesisStatus.ERROR
            hypothesis.check_result = f"{type(e).__name__}: {e}"
            hypothesis.checked_at = time.time()
            return hypothesis

    def generate_hypotheses(
        self,
        claims: list[str],
        sources: list[str] | None = None,
    ) -> list[Hypothesis]:
        """
        Сгенерировать гипотезы из утверждений.

        Args:
            claims: Утверждения для проверки
            sources: Источники утверждений

        Returns:
            Список Hypothesis объектов
        """
        return [
            Hypothesis(
                id=f"h_{i+1}",
                statement=claim,
                sources=sources or [],
            )
            for i, claim in enumerate(claims)
        ]

    def summarize_results(
        self,
        hypotheses: list[Hypothesis],
    ) -> dict:
        """Суммировать результаты проверки гипотез."""
        confirmed = [h for h in hypotheses if h.status ==
                     HypothesisStatus.CONFIRMED]
        refuted = [h for h in hypotheses if h.status ==
                   HypothesisStatus.REFUTED]
        uncertain = [h for h in hypotheses if h.status ==
                     HypothesisStatus.UNCERTAIN]
        errors = [h for h in hypotheses if h.status == HypothesisStatus.ERROR]

        avg_confidence = (
            sum(h.confidence for h in hypotheses) / len(hypotheses)
            if hypotheses else 0.0
        )

        return {
            "total": len(hypotheses),
            "confirmed": len(confirmed),
            "refuted": len(refuted),
            "uncertain": len(uncertain),
            "errors": len(errors),
            "avg_confidence": round(avg_confidence, 2),
            "details": [h.to_dict() for h in hypotheses],
        }

    @property
    def checked_count(self) -> int:
        return self._checked_count


# ═══════════════════════════════════════════════════════════════════════════════
# 4. TASK BATCH QUEUE
# ═══════════════════════════════════════════════════════════════════════════════


class TaskBatchQueue:
    """
    Batch-очередь для группировки и выполнения похожих задач.

    Задачи одной категории группируются и выполняются вместе.
    Например: несколько переводов → один batch.

    Поддерживает:
    - Категории задач
    - Приоритеты
    - Flush по таймеру или по размеру
    - Параллельное выполнение batch
    """

    def __init__(
        self,
        max_batch_size: int = 5,
        flush_interval_ms: float = 200,
    ):
        self._max_batch_size = max_batch_size
        self._flush_interval_ms = flush_interval_ms
        self._queues: dict[str, list[BatchTask]] = {}
        self._lock = asyncio.Lock()
        self._running = False
        self._processor_task: asyncio.Task | None = None
        self._stats = ExecutionStats()

    async def start(self) -> None:
        """Запустить фоновый процессор."""
        self._running = True
        self._processor_task = asyncio.create_task(self._process_loop())
        logger.info("TaskBatchQueue запущен")

    async def stop(self) -> None:
        """Остановить процессор."""
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        # Flush оставшиеся
        for category in list(self._queues.keys()):
            await self._flush_category(category)
        logger.info("TaskBatchQueue остановлен")

    async def submit(
        self,
        task_id: str,
        category: str,
        coro_factory: Callable[[], Coroutine],
        priority: int = 0,
    ) -> Any:
        """
        Отправить задачу в batch-очередь.

        Args:
            task_id: Уникальный ID задачи
            category: Категория (для группировки)
            coro_factory: Фабрика coroutine
            priority: Приоритет (выше = первый)

        Returns:
            Результат выполнения
        """
        loop = asyncio.get_event_loop()
        future = loop.create_future()

        task = BatchTask(
            id=task_id,
            category=category,
            coro_factory=coro_factory,
            priority=priority,
            future=future,
        )

        async with self._lock:
            if category not in self._queues:
                self._queues[category] = []
            self._queues[category].append(task)

            # Если batch полный — flush
            if len(self._queues[category]) >= self._max_batch_size:
                await self._flush_category(category)

        return await future

    async def _process_loop(self) -> None:
        """Фоновый цикл: flush по таймеру."""
        while self._running:
            await asyncio.sleep(self._flush_interval_ms / 1000)
            for category in list(self._queues.keys()):
                if self._queues.get(category):
                    await self._flush_category(category)

    async def _flush_category(self, category: str) -> None:
        """Выполнить batch для категории."""
        async with self._lock:
            tasks = self._queues.pop(category, [])

        if not tasks:
            return

        # Сортируем по приоритету
        tasks.sort(key=lambda t: t.priority, reverse=True)

        self._stats.batch_runs += 1
        self._stats.total_tasks += len(tasks)

        if len(tasks) > 1:
            self._stats.parallel_tasks += len(tasks)
        else:
            self._stats.sequential_tasks += 1

        logger.debug(
            f"Batch flush [{category}]: {len(tasks)} задач"
        )

        # Параллельное выполнение
        coros = [self._execute_batch_task(t) for t in tasks]
        await asyncio.gather(*coros, return_exceptions=True)

    async def _execute_batch_task(self, task: BatchTask) -> None:
        """Выполнить одну задачу из batch."""
        try:
            result = await task.coro_factory()
            if task.future and not task.future.done():
                task.future.set_result(result)
        except Exception as e:
            if task.future and not task.future.done():
                task.future.set_exception(e)

    @property
    def queue_sizes(self) -> dict[str, int]:
        return {cat: len(tasks) for cat, tasks in self._queues.items()}

    @property
    def stats(self) -> ExecutionStats:
        return self._stats


# ═══════════════════════════════════════════════════════════════════════════════
# 5. PARALLEL ENGINE — Главный оркестратор
# ═══════════════════════════════════════════════════════════════════════════════


class ParallelEngine:
    """
    Главный оркестратор параллельного выполнения.

    Объединяет:
    - ConcurrencyManager: контроль нагрузки
    - ParallelDAGExecutor: параллельный DAG
    - ParallelHypothesisChecker: параллельные гипотезы
    - TaskBatchQueue: batch задач

    Встраивается в CognitiveEngine и InternetReasoningEngine.
    """

    def __init__(
        self,
        max_concurrent: int = 10,
        max_llm_concurrent: int = 5,
        max_browser_concurrent: int = 3,
        batch_size: int = 5,
    ):
        self._concurrency = ConcurrencyManager(
            max_concurrent=max_concurrent,
            max_llm_concurrent=max_llm_concurrent,
            max_browser_concurrent=max_browser_concurrent,
        )
        self._dag_executor = ParallelDAGExecutor(
            concurrency=self._concurrency,
        )
        self._hypothesis_checker = ParallelHypothesisChecker(
            concurrency=self._concurrency,
        )
        self._batch_queue = TaskBatchQueue(max_batch_size=batch_size)

    @property
    def concurrency(self) -> ConcurrencyManager:
        return self._concurrency

    @property
    def dag_executor(self) -> ParallelDAGExecutor:
        return self._dag_executor

    @property
    def hypothesis_checker(self) -> ParallelHypothesisChecker:
        return self._hypothesis_checker

    @property
    def batch_queue(self) -> TaskBatchQueue:
        return self._batch_queue

    async def run_parallel(
        self,
        tasks: dict[str, Callable[[], Coroutine]],
        category: str = "general",
    ) -> dict[str, ParallelResult]:
        """
        Выполнить несколько задач параллельно.

        Args:
            tasks: {"task_id": coroutine_factory, ...}
            category: Категория для семафора

        Returns:
            {"task_id": ParallelResult, ...}
        """
        if not tasks:
            return {}

        async def _run_one(task_id: str, factory: Callable) -> ParallelResult:
            start = time.time()
            try:
                result = await self._concurrency.run_limited(
                    factory(), category=category
                )
                return ParallelResult(
                    task_id=task_id,
                    success=True,
                    result=result,
                    duration_ms=(time.time() - start) * 1000,
                )
            except Exception as e:
                return ParallelResult(
                    task_id=task_id,
                    success=False,
                    error=str(e),
                    duration_ms=(time.time() - start) * 1000,
                )

        coros = [_run_one(tid, factory) for tid, factory in tasks.items()]
        results = await asyncio.gather(*coros)

        return {r.task_id: r for r in results}

    async def start(self) -> None:
        """Запустить все компоненты."""
        await self._batch_queue.start()
        logger.info("ParallelEngine запущен")

    async def stop(self) -> None:
        """Остановить все компоненты."""
        await self._batch_queue.stop()
        logger.info("ParallelEngine остановлен")

    def get_stats(self) -> dict:
        """Полная статистика."""
        return {
            "concurrency": {
                "active": self._concurrency.active_count,
                "peak": self._concurrency.peak_count,
            },
            "dag": self._dag_executor.stats.to_dict(),
            "hypothesis": {
                "checked": self._hypothesis_checker.checked_count,
            },
            "batch": self._batch_queue.stats.to_dict(),
        }


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

parallel_engine = ParallelEngine()
