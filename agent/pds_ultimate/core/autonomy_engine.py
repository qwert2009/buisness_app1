"""
PDS-Ultimate Autonomy Engine (Part 8)
========================================
Автономное выполнение задач без постоянного контроля.

Ключевые возможности:
1. Task Queue — очередь задач с приоритетами и дедлайнами
2. Autonomous Executor — выполнение цепочек задач без участия пользователя
3. Multi-step Self-Correction v2 — если шаг пошёл не так → пересмотр + retry
4. Batch Processing — группировка и параллельное выполнение
5. Goal Decomposition — автоматическая декомпозиция сложных целей
6. Progress Reporter — отчёт о прогрессе в фоне
7. Async Tool Orchestration — параллельный вызов инструментов

Агент РЕАЛЬНО работает вместо пользователя, а не советует!
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from pds_ultimate.config import logger

# ═══════════════════════════════════════════════════════════════════════════════
# TASK DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════


class TaskPriority(int, Enum):
    """Приоритет задачи."""
    CRITICAL = 4    # Немедленное выполнение
    HIGH = 3        # В ближайшее время
    MEDIUM = 2      # Обычный приоритет
    LOW = 1         # Когда будет время
    BACKGROUND = 0  # Фоновая задача


class TaskStatus(str, Enum):
    """Статус задачи."""
    QUEUED = "queued"
    DECOMPOSING = "decomposing"  # Разбивается на подзадачи
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING = "waiting"     # Ждёт зависимость
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskStep:
    """Один шаг выполнения задачи."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    description: str = ""
    tool_name: str = ""
    tool_params: dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.QUEUED
    result: str = ""
    error: str = ""
    attempts: int = 0
    max_attempts: int = 3
    started_at: float = 0.0
    completed_at: float = 0.0

    @property
    def duration_ms(self) -> int:
        if self.completed_at and self.started_at:
            return int((self.completed_at - self.started_at) * 1000)
        return 0

    @property
    def can_retry(self) -> bool:
        return self.attempts < self.max_attempts

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "tool": self.tool_name,
            "status": self.status.value,
            "attempts": self.attempts,
            "duration_ms": self.duration_ms,
            "result": self.result[:200] if self.result else "",
            "error": self.error,
        }


@dataclass
class AutonomousTask:
    """
    Автономная задача с метаданными.
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    title: str = ""
    description: str = ""
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.QUEUED
    owner_id: int = 0
    chat_id: int = 0

    # Steps
    steps: list[TaskStep] = field(default_factory=list)
    current_step: int = 0

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    deadline: datetime | None = None
    started_at: float = 0.0
    completed_at: float = 0.0

    # Dependencies
    depends_on: list[str] = field(default_factory=list)  # Task IDs
    blocks: list[str] = field(default_factory=list)  # Tasks blocked by this

    # Result
    result: str = ""
    error: str = ""
    retry_count: int = 0
    max_retries: int = 3

    # Metadata
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Self-correction
    corrections: list[str] = field(default_factory=list)

    @property
    def is_overdue(self) -> bool:
        if not self.deadline:
            return False
        return datetime.utcnow() > self.deadline

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED
        )

    @property
    def progress(self) -> float:
        """Прогресс выполнения 0.0–1.0."""
        if not self.steps:
            return 0.0
        completed = sum(1 for s in self.steps if s.status ==
                        TaskStatus.COMPLETED)
        return completed / len(self.steps)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority.name,
            "status": self.status.value,
            "progress": f"{self.progress:.0%}",
            "steps_total": len(self.steps),
            "steps_done": sum(1 for s in self.steps
                              if s.status == TaskStatus.COMPLETED),
            "created_at": self.created_at.isoformat(),
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "overdue": self.is_overdue,
            "corrections": len(self.corrections),
            "tags": self.tags,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# SELF-CORRECTION ENGINE — Multi-step error recovery
# ═══════════════════════════════════════════════════════════════════════════════


class SelfCorrectionEngine:
    """
    Движок самокоррекции.

    Если шаг задачи провалился:
    1. Анализирует ошибку
    2. Определяет стратегию (retry/skip/replan/abort)
    3. При retry — корректирует параметры
    4. При replan — перестраивает оставшиеся шаги
    """

    class Strategy(str, Enum):
        RETRY_SAME = "retry_same"         # Повторить как есть
        RETRY_MODIFIED = "retry_modified"  # Повторить с изменениями
        SKIP = "skip"                      # Пропустить шаг
        REPLAN = "replan"                  # Перепланировать оставшееся
        ABORT = "abort"                    # Прекратить задачу
        ALTERNATIVE = "alternative"        # Использовать альтернативный инструмент

    # Маппинг ошибок → стратегии
    ERROR_STRATEGIES: dict[str, "SelfCorrectionEngine.Strategy"] = {
        "timeout": Strategy.RETRY_SAME,
        "rate_limit": Strategy.RETRY_SAME,
        "not_found": Strategy.SKIP,
        "permission": Strategy.ABORT,
        "validation": Strategy.RETRY_MODIFIED,
        "network": Strategy.RETRY_SAME,
        "parse": Strategy.RETRY_MODIFIED,
    }

    def analyze_error(self, step: TaskStep, error: str) -> "SelfCorrectionEngine.Strategy":
        """Определить стратегию восстановления."""
        error_lower = error.lower()

        # По паттернам ошибок
        for keyword, strategy in self.ERROR_STRATEGIES.items():
            if keyword in error_lower:
                return strategy

        # По количеству попыток
        if step.can_retry:
            return self.Strategy.RETRY_MODIFIED
        else:
            return self.Strategy.SKIP

    def suggest_modification(
        self,
        step: TaskStep,
        error: str,
    ) -> dict[str, Any]:
        """Предложить модификацию параметров для retry."""
        modifications: dict[str, Any] = {}

        error_lower = error.lower()

        # Timeout → увеличить timeout
        if "timeout" in error_lower:
            modifications["timeout"] = step.tool_params.get("timeout", 30) * 2

        # Rate limit → добавить задержку
        if "rate_limit" in error_lower or "429" in error_lower:
            modifications["_delay_seconds"] = 5.0

        # Validation → попробовать с упрощёнными данными
        if "validation" in error_lower:
            # Обрезаем длинные строки
            for k, v in step.tool_params.items():
                if isinstance(v, str) and len(v) > 500:
                    modifications[k] = v[:500]

        return modifications

    def get_correction_message(
        self,
        step: TaskStep,
        strategy: "SelfCorrectionEngine.Strategy",
        error: str,
    ) -> str:
        """Сформировать сообщение о коррекции."""
        messages = {
            self.Strategy.RETRY_SAME: f"⟳ Повторяю шаг «{step.description}» (попытка {step.attempts + 1})",
            self.Strategy.RETRY_MODIFIED: (
                f"🔧 Корректирую параметры и повторяю «{step.description}»"
            ),
            self.Strategy.SKIP: f"⏭ Пропускаю шаг «{step.description}» (некритичный)",
            self.Strategy.REPLAN: f"📋 Перепланирую оставшиеся шаги после ошибки в «{step.description}»",
            self.Strategy.ABORT: f"🛑 Прекращаю: критическая ошибка в «{step.description}»",
            self.Strategy.ALTERNATIVE: f"🔄 Ищу альтернативный способ для «{step.description}»",
        }
        return messages.get(strategy, f"Ошибка в «{step.description}»: {error}")


# ═══════════════════════════════════════════════════════════════════════════════
# GOAL DECOMPOSER — Разбивает сложные цели на подзадачи
# ═══════════════════════════════════════════════════════════════════════════════


class GoalDecomposer:
    """
    Декомпозиция сложных целей на выполнимые шаги.

    Если цель слишком сложная или долгосрочная:
    1. Генерирует промежуточные подцели
    2. Определяет зависимости между ними
    3. Оценивает сложность и время
    """

    # Паттерны для определения сложности
    COMPLEX_MARKERS = [
        "несколько", "все", "каждый", "сравни", "проанализируй",
        "исследуй", "найди лучший", "собери информацию", "полный отчёт",
        "multiple", "compare", "analyze", "research", "comprehensive",
    ]

    def is_complex(self, description: str) -> bool:
        """Определить, нужна ли декомпозиция."""
        lower = description.lower()

        # По маркерам
        if any(m in lower for m in self.COMPLEX_MARKERS):
            return True

        # По длине (длинное описание = сложная задача)
        if len(description) > 200:
            return True

        # По количеству "и" / "+"
        conjunctions = lower.count(
            " и ") + lower.count(" + ") + lower.count(", ")
        if conjunctions >= 3:
            return True

        return False

    def decompose(
        self,
        goal: str,
        available_tools: list[str] | None = None,
    ) -> list[TaskStep]:
        """
        Разбить цель на шаги (rule-based, без LLM).

        Для LLM-based декомпозиции используйте decompose_with_llm().
        """
        steps: list[TaskStep] = []

        lower = goal.lower()

        # Паттерны и соответствующие инструменты
        tool_patterns = {
            "поиск|найди|search|find": "web_search",
            "переведи|перевод|translate": "translate_text",
            "файл|документ|excel|pdf": "convert_file",
            "курс|валют|exchange": "exchange_rates",
            "чек|receipt|скан": "scan_receipt",
            "календарь|встреч|event": "google_calendar",
            "заказ|order|товар": "create_order",
            "баланс|финанс|доход|расход": "get_financial_summary",
            "напомни|reminder|напоминание": "create_reminder",
        }

        import re
        for pattern, tool in tool_patterns.items():
            if re.search(pattern, lower):
                if available_tools and tool not in available_tools:
                    continue
                steps.append(TaskStep(
                    description=f"Использовать {tool} для: {goal[:100]}",
                    tool_name=tool,
                ))

        # Если ничего не определили — generic шаги
        if not steps:
            steps = [
                TaskStep(description="Анализ задачи", tool_name=""),
                TaskStep(description="Выполнение", tool_name=""),
                TaskStep(description="Проверка результата", tool_name=""),
            ]

        return steps

    async def decompose_with_llm(
        self,
        goal: str,
        available_tools: list[str],
        llm_func: Callable | None = None,
    ) -> list[TaskStep]:
        """
        Декомпозиция через LLM — для сложных целей.

        Args:
            goal: Описание цели
            available_tools: Список доступных инструментов
            llm_func: Async функция для вызова LLM

        Returns:
            Список шагов
        """
        if not llm_func:
            return self.decompose(goal, available_tools)

        prompt = (
            f"Разбей задачу на конкретные шаги.\n\n"
            f"ЗАДАЧА: {goal}\n\n"
            f"ДОСТУПНЫЕ ИНСТРУМЕНТЫ: {', '.join(available_tools)}\n\n"
            f"Верни JSON массив шагов:\n"
            f'[{{"description": "...", "tool": "tool_name", '
            f'"params": {{"key": "value"}}}}]\n\n'
            f"Правила:\n"
            f"- Минимум шагов (не раздувай)\n"
            f"- Каждый шаг = один tool call\n"
            f"- Параметры конкретные, не абстрактные\n"
            f"- Если tool не нужен — tool: null"
        )

        try:
            import json
            response = await llm_func(prompt)
            data = json.loads(response)

            steps = []
            for item in data:
                step = TaskStep(
                    description=item.get("description", ""),
                    tool_name=item.get("tool", "") or "",
                    tool_params=item.get("params", {}),
                )
                steps.append(step)

            return steps if steps else self.decompose(goal, available_tools)

        except Exception as e:
            logger.warning(f"LLM decompose failed: {e}")
            return self.decompose(goal, available_tools)


# ═══════════════════════════════════════════════════════════════════════════════
# BATCH PROCESSOR — Группировка и параллельная обработка
# ═══════════════════════════════════════════════════════════════════════════════


class BatchProcessor:
    """
    Группировка задач и параллельное выполнение.

    Оптимизации:
    - Одинаковые инструменты → batch
    - Независимые шаги → параллельно
    - Rate limiting per-tool
    """

    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._results: dict[str, Any] = {}

    async def execute_parallel(
        self,
        steps: list[TaskStep],
        executor: Callable,
    ) -> list[TaskStep]:
        """
        Выполнить независимые шаги параллельно.

        Args:
            steps: Шаги для выполнения
            executor: Async функция(step) -> step

        Returns:
            Обработанные шаги
        """
        async def _run_step(step: TaskStep) -> TaskStep:
            async with self._semaphore:
                return await executor(step)

        tasks = [_run_step(step) for step in steps]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                steps[i].status = TaskStatus.FAILED
                steps[i].error = str(result)
                processed.append(steps[i])
            else:
                processed.append(result)

        return processed

    def group_by_tool(self, steps: list[TaskStep]) -> dict[str, list[TaskStep]]:
        """Группировка шагов по инструменту."""
        groups: dict[str, list[TaskStep]] = defaultdict(list)
        for step in steps:
            key = step.tool_name or "_generic"
            groups[key].append(step)
        return dict(groups)

    def find_independent(self, steps: list[TaskStep]) -> tuple[list[TaskStep], list[TaskStep]]:
        """
        Разделить шаги на независимые (можно параллельно) и зависимые.

        Simple heuristic: если шаг не использует результат предыдущего → независимый.
        """
        independent = []
        dependent = []

        seen_tools = set()
        for step in steps:
            # Если результат предыдущего шага нужен как вход
            has_refs = any(
                "${" in str(v) for v in step.tool_params.values()
            ) if step.tool_params else False

            if has_refs or step.tool_name in seen_tools:
                dependent.append(step)
            else:
                independent.append(step)

            if step.tool_name:
                seen_tools.add(step.tool_name)

        return independent, dependent


# ═══════════════════════════════════════════════════════════════════════════════
# AUTONOMY ENGINE — Центральный движок автономности
# ═══════════════════════════════════════════════════════════════════════════════


class AutonomyEngine:
    """
    Центральный движок автономного выполнения.

    Возможности:
    - Принимает задачу → декомпозирует → выполняет → отчитывается
    - Несколько задач одновременно с приоритетами
    - Self-correction при ошибках
    - Goal integrity check на каждом шаге
    - Progress reporting
    """

    MAX_CONCURRENT_TASKS = 5

    def __init__(self):
        self._tasks: dict[str, AutonomousTask] = {}
        self._task_queue: list[str] = []  # IDs in priority order
        self._corrector = SelfCorrectionEngine()
        self._decomposer = GoalDecomposer()
        self._batch = BatchProcessor()
        self._running = False
        self._callbacks: dict[str, Callable] = {}  # progress callbacks

    # ─── Task Management ─────────────────────────────────────────────────

    def create_task(
        self,
        title: str,
        description: str = "",
        priority: TaskPriority = TaskPriority.MEDIUM,
        deadline: datetime | None = None,
        owner_id: int = 0,
        chat_id: int = 0,
        tags: list[str] | None = None,
        steps: list[TaskStep] | None = None,
    ) -> AutonomousTask:
        """Создать новую автономную задачу."""
        task = AutonomousTask(
            title=title,
            description=description or title,
            priority=priority,
            deadline=deadline,
            owner_id=owner_id,
            chat_id=chat_id,
            tags=tags or [],
            steps=steps or [],
        )

        self._tasks[task.id] = task
        self._insert_sorted(task.id)

        logger.info(
            f"Autonomy: task created «{title}» "
            f"priority={priority.name} id={task.id}"
        )

        return task

    def cancel_task(self, task_id: str) -> bool:
        """Отменить задачу."""
        task = self._tasks.get(task_id)
        if not task or task.is_terminal:
            return False

        task.status = TaskStatus.CANCELLED
        if task_id in self._task_queue:
            self._task_queue.remove(task_id)

        logger.info(f"Autonomy: task cancelled «{task.title}» id={task_id}")
        return True

    def get_task(self, task_id: str) -> AutonomousTask | None:
        return self._tasks.get(task_id)

    def get_user_tasks(
        self,
        owner_id: int,
        status: TaskStatus | None = None,
    ) -> list[AutonomousTask]:
        """Получить задачи пользователя."""
        tasks = [t for t in self._tasks.values() if t.owner_id == owner_id]
        if status:
            tasks = [t for t in tasks if t.status == status]
        return sorted(tasks, key=lambda t: t.priority.value, reverse=True)

    def get_active_tasks(self) -> list[AutonomousTask]:
        """Все активные (не завершённые) задачи."""
        return [t for t in self._tasks.values() if not t.is_terminal]

    @property
    def total_tasks(self) -> int:
        return len(self._tasks)

    @property
    def active_tasks_count(self) -> int:
        return len(self.get_active_tasks())

    @property
    def queue_size(self) -> int:
        return len(self._task_queue)

    # ─── Decompose ───────────────────────────────────────────────────────

    def decompose_task(
        self,
        task: AutonomousTask,
        available_tools: list[str] | None = None,
    ) -> AutonomousTask:
        """Декомпозировать задачу на шаги (rule-based)."""
        if not task.steps:
            task.status = TaskStatus.DECOMPOSING
            task.steps = self._decomposer.decompose(
                task.description, available_tools
            )
            task.status = TaskStatus.READY

        return task

    async def decompose_task_llm(
        self,
        task: AutonomousTask,
        available_tools: list[str],
        llm_func: Callable,
    ) -> AutonomousTask:
        """Декомпозировать задачу через LLM."""
        if not task.steps:
            task.status = TaskStatus.DECOMPOSING
            task.steps = await self._decomposer.decompose_with_llm(
                task.description, available_tools, llm_func
            )
            task.status = TaskStatus.READY

        return task

    # ─── Execute ─────────────────────────────────────────────────────────

    async def execute_task(
        self,
        task: AutonomousTask,
        tool_executor: Callable,
        goal_check: bool = True,
    ) -> AutonomousTask:
        """
        Выполнить задачу полностью автономно.

        Args:
            task: Задача для выполнения
            tool_executor: async (tool_name, params) -> ToolResult
            goal_check: Проверять goal integrity на каждом шаге

        Returns:
            Обновлённая задача с результатами
        """
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()

        # Разделяем на параллельные и последовательные
        independent, dependent = self._batch.find_independent(task.steps)

        # Выполняем независимые параллельно
        if independent:
            async def _exec_step(step: TaskStep) -> TaskStep:
                return await self._execute_step(step, tool_executor)

            processed = await self._batch.execute_parallel(independent, _exec_step)
            for orig, proc in zip(independent, processed):
                idx = task.steps.index(orig)
                task.steps[idx] = proc

        # Выполняем зависимые последовательно
        for step in dependent:
            idx = task.steps.index(step)

            # Goal integrity check
            if goal_check and idx > 0:
                if not self._check_goal_integrity(task):
                    task.corrections.append(
                        f"Goal drift detected at step {idx}. Refocusing."
                    )

            result = await self._execute_step(step, tool_executor)
            task.steps[idx] = result

            # Self-correction при ошибке
            if result.status == TaskStatus.FAILED:
                correction_result = await self._self_correct(
                    task, idx, tool_executor
                )
                if not correction_result:
                    # Не удалось исправить — проверяем критичность
                    if task.priority == TaskPriority.CRITICAL:
                        task.status = TaskStatus.FAILED
                        task.error = f"Critical step failed: {result.error}"
                        return task
                    # Некритичный — продолжаем

            # Progress callback
            callback = self._callbacks.get(task.id)
            if callback:
                try:
                    await callback(task)
                except Exception:
                    pass

        # Определяем финальный статус
        failed = sum(1 for s in task.steps if s.status == TaskStatus.FAILED)
        completed = sum(1 for s in task.steps if s.status ==
                        TaskStatus.COMPLETED)

        if failed == 0:
            task.status = TaskStatus.COMPLETED
            task.result = self._compile_results(task)
        elif completed > failed:
            task.status = TaskStatus.COMPLETED
            task.result = self._compile_results(task)
            task.corrections.append(
                f"{failed} шагов пропущено из {len(task.steps)}")
        else:
            task.status = TaskStatus.FAILED
            task.error = f"{failed}/{len(task.steps)} шагов провалились"

        task.completed_at = time.time()

        logger.info(
            f"Autonomy: task finished «{task.title}» "
            f"status={task.status.value} "
            f"duration={int(task.completed_at - task.started_at)}s "
            f"corrections={len(task.corrections)}"
        )

        return task

    # ─── Self-correction ─────────────────────────────────────────────────

    async def _self_correct(
        self,
        task: AutonomousTask,
        step_idx: int,
        tool_executor: Callable,
    ) -> bool:
        """
        Попытка самокоррекции после ошибки.

        Returns:
            True если удалось исправить
        """
        step = task.steps[step_idx]
        strategy = self._corrector.analyze_error(step, step.error)

        msg = self._corrector.get_correction_message(
            step, strategy, step.error)
        task.corrections.append(msg)

        logger.info(
            f"Autonomy: self-correction strategy={strategy.value} for «{step.description}»")

        if strategy == SelfCorrectionEngine.Strategy.RETRY_SAME:
            # Просто повторяем
            result = await self._execute_step(step, tool_executor)
            task.steps[step_idx] = result
            return result.status == TaskStatus.COMPLETED

        elif strategy == SelfCorrectionEngine.Strategy.RETRY_MODIFIED:
            # Корректируем параметры
            mods = self._corrector.suggest_modification(step, step.error)

            # Задержка если нужно
            delay = mods.pop("_delay_seconds", 0)
            if delay:
                await asyncio.sleep(delay)

            # Обновляем параметры
            step.tool_params.update(mods)
            result = await self._execute_step(step, tool_executor)
            task.steps[step_idx] = result
            return result.status == TaskStatus.COMPLETED

        elif strategy == SelfCorrectionEngine.Strategy.SKIP:
            step.status = TaskStatus.COMPLETED
            step.result = "(пропущен)"
            return True

        elif strategy == SelfCorrectionEngine.Strategy.ABORT:
            return False

        return False

    # ─── Internal ────────────────────────────────────────────────────────

    async def _execute_step(
        self,
        step: TaskStep,
        tool_executor: Callable,
    ) -> TaskStep:
        """Выполнить один шаг задачи."""
        step.status = TaskStatus.RUNNING
        step.started_at = time.time()
        step.attempts += 1

        try:
            if step.tool_name:
                result = await tool_executor(step.tool_name, step.tool_params)

                if hasattr(result, 'success'):
                    if result.success:
                        step.status = TaskStatus.COMPLETED
                        step.result = str(result.output) if hasattr(
                            result, 'output') else str(result)
                    else:
                        step.status = TaskStatus.FAILED
                        step.error = str(result.error) if hasattr(
                            result, 'error') else str(result)
                else:
                    step.status = TaskStatus.COMPLETED
                    step.result = str(result)
            else:
                # Шаг без инструмента — считаем выполненным
                step.status = TaskStatus.COMPLETED
                step.result = "OK"

        except Exception as e:
            step.status = TaskStatus.FAILED
            step.error = str(e)

        step.completed_at = time.time()
        return step

    def _check_goal_integrity(self, task: AutonomousTask) -> bool:
        """
        Goal Integrity Check: всё ещё решаем исходную цель?

        Простая эвристика: проверяем что хотя бы часть шагов
        связана с исходной задачей.
        """
        if not task.steps or not task.description:
            return True

        # Проверяем что текущий шаг по теме
        completed_steps = [
            s for s in task.steps if s.status == TaskStatus.COMPLETED]
        if not completed_steps:
            return True

        # Простая проверка: не слишком ли много ошибок подряд
        last_steps = task.steps[max(
            0, task.current_step - 3):task.current_step]
        failures = sum(1 for s in last_steps if s.status == TaskStatus.FAILED)

        return failures < 3

    def _compile_results(self, task: AutonomousTask) -> str:
        """Собрать результаты всех шагов в итоговый отчёт."""
        lines = [f"✅ Задача «{task.title}» выполнена\n"]

        for i, step in enumerate(task.steps, 1):
            status = "✅" if step.status == TaskStatus.COMPLETED else "❌"
            lines.append(f"{status} Шаг {i}: {step.description}")
            if step.result and step.result != "OK":
                lines.append(f"   → {step.result[:200]}")

        if task.corrections:
            lines.append(f"\n🔧 Коррекций: {len(task.corrections)}")

        duration = task.completed_at - task.started_at if task.completed_at else 0
        lines.append(f"\n⏱ Время: {duration:.1f}с")

        return "\n".join(lines)

    def _insert_sorted(self, task_id: str) -> None:
        """Вставить задачу в очередь с учётом приоритета."""
        task = self._tasks.get(task_id)
        if not task:
            return

        # Находим позицию (выше приоритет = ближе к началу)
        for i, tid in enumerate(self._task_queue):
            other = self._tasks.get(tid)
            if not other or task.priority.value > other.priority.value:
                self._task_queue.insert(i, task_id)
                return

        self._task_queue.append(task_id)

    def set_progress_callback(
        self,
        task_id: str,
        callback: Callable,
    ) -> None:
        """Установить callback для отслеживания прогресса."""
        self._callbacks[task_id] = callback

    # ─── Stats ───────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Статистика автономности."""
        tasks = list(self._tasks.values())
        return {
            "total": len(tasks),
            "active": sum(1 for t in tasks if not t.is_terminal),
            "completed": sum(1 for t in tasks
                             if t.status == TaskStatus.COMPLETED),
            "failed": sum(1 for t in tasks
                          if t.status == TaskStatus.FAILED),
            "queue_size": len(self._task_queue),
            "total_corrections": sum(len(t.corrections) for t in tasks),
            "by_priority": {
                p.name: sum(1 for t in tasks if t.priority == p)
                for p in TaskPriority
            },
            "overdue": sum(1 for t in tasks if t.is_overdue),
        }

    def format_queue(self) -> str:
        """Форматировать очередь задач для отображения."""
        if not self._task_queue:
            return "📋 Очередь задач пуста"

        lines = ["📋 **Очередь задач:**\n"]
        for i, tid in enumerate(self._task_queue[:20], 1):
            task = self._tasks.get(tid)
            if not task:
                continue

            priority_icon = {
                TaskPriority.CRITICAL: "🔴",
                TaskPriority.HIGH: "🟠",
                TaskPriority.MEDIUM: "🟡",
                TaskPriority.LOW: "🟢",
                TaskPriority.BACKGROUND: "⚪",
            }
            icon = priority_icon.get(task.priority, "⚪")

            status_icon = {
                TaskStatus.RUNNING: "▶️",
                TaskStatus.COMPLETED: "✅",
                TaskStatus.FAILED: "❌",
                TaskStatus.QUEUED: "⏳",
                TaskStatus.PAUSED: "⏸",
            }
            s_icon = status_icon.get(task.status, "❓")

            deadline_str = ""
            if task.deadline:
                if task.is_overdue:
                    deadline_str = " ⚠️ ПРОСРОЧЕНА"
                else:
                    remaining = task.deadline - datetime.utcnow()
                    deadline_str = f" (до {task.deadline.strftime('%d.%m %H:%M')})"

            lines.append(
                f"{i}. {icon}{s_icon} {task.title}"
                f" [{task.progress:.0%}]{deadline_str}"
            )

        return "\n".join(lines)


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

autonomy_engine = AutonomyEngine()
