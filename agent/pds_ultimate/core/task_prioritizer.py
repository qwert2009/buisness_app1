"""
PDS-Ultimate Task Prioritizer & Batch Engine (Part 10 — Item 8)
================================================================
Интеллектуальная расстановка приоритетов и батч-выполнение задач.

Компоненты:
1. PriorityLevel / TaskItem — модель задачи с приоритетом
2. PriorityQueue — очередь задач с приоритетами
3. TaskBatcher — группировка задач в батчи по типу/приоритету
4. TaskScheduler — планировщик: deadlines, зависимости, ресурсы
5. TaskPrioritizer — фасад
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from pds_ultimate.config import logger

# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS & DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class PriorityLevel(IntEnum):
    """Уровень приоритета (0 = highest)."""
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    BACKGROUND = 4


class TaskStatus(str):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BATCHED = "batched"


@dataclass
class TaskItem:
    """Элемент задачи."""
    id: str
    name: str
    priority: PriorityLevel = PriorityLevel.MEDIUM
    task_type: str = "general"
    payload: dict = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    deadline: float | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    status: str = TaskStatus.PENDING
    result: Any = None
    error: str | None = None
    estimated_duration: float = 1.0  # seconds
    tags: list[str] = field(default_factory=list)

    @property
    def age(self) -> float:
        """Возраст задачи в секундах."""
        return time.time() - self.created_at

    @property
    def time_to_deadline(self) -> float | None:
        """Время до deadline в секундах."""
        if self.deadline is None:
            return None
        return self.deadline - time.time()

    @property
    def is_overdue(self) -> bool:
        """Просрочена ли задача."""
        return self.time_to_deadline is not None and self.time_to_deadline < 0

    @property
    def effective_priority(self) -> float:
        """
        Эффективный приоритет (0 = наивысший).
        Учитывает: base priority, deadline proximity, age.
        """
        base = float(self.priority)
        # Deadline boost: ближе к дедлайну → выше приоритет
        if self.time_to_deadline is not None:
            ttd = self.time_to_deadline
            if ttd <= 0:
                base -= 2.0  # Overdue → critical boost
            elif ttd < 60:
                base -= 1.0  # < 1 min
            elif ttd < 300:
                base -= 0.5  # < 5 min
        # Age boost: старые задачи поднимаются (anti-starvation)
        age_bonus = min(self.age / 600, 1.0)  # max 1.0 at 10 min
        base -= age_bonus * 0.5
        return base

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "priority": self.priority.name,
            "type": self.task_type,
            "status": self.status,
            "effective_priority": round(self.effective_priority, 2),
            "age_sec": round(self.age, 1),
        }


@dataclass
class TaskBatch:
    """Пакет задач для параллельного выполнения."""
    id: str
    task_type: str
    tasks: list[TaskItem] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @property
    def size(self) -> int:
        return len(self.tasks)

    @property
    def total_estimated_duration(self) -> float:
        return sum(t.estimated_duration for t in self.tasks)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.task_type,
            "size": self.size,
            "tasks": [t.id for t in self.tasks],
            "estimated_duration_sec": round(self.total_estimated_duration, 1),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. PRIORITY QUEUE — Очередь с приоритетами
# ═══════════════════════════════════════════════════════════════════════════════


class PriorityQueue:
    """
    Очередь задач с приоритетами и anti-starvation.

    Задачи упорядочиваются по effective_priority (lower = higher priority).
    """

    def __init__(self, max_size: int = 1000):
        self._tasks: dict[str, TaskItem] = {}
        self._max_size = max_size

    def add(self, task: TaskItem) -> bool:
        """Добавить задачу."""
        if len(self._tasks) >= self._max_size:
            logger.warning(f"PriorityQueue full ({self._max_size})")
            return False
        self._tasks[task.id] = task
        return True

    def pop(self) -> TaskItem | None:
        """Извлечь задачу с наивысшим приоритетом."""
        pending = [
            t for t in self._tasks.values() if t.status == TaskStatus.PENDING
        ]
        if not pending:
            return None
        best = min(pending, key=lambda t: t.effective_priority)
        best.status = TaskStatus.RUNNING
        best.started_at = time.time()
        return best

    def peek(self) -> TaskItem | None:
        """Посмотреть задачу с наивысшим приоритетом без извлечения."""
        pending = [
            t for t in self._tasks.values() if t.status == TaskStatus.PENDING
        ]
        if not pending:
            return None
        return min(pending, key=lambda t: t.effective_priority)

    def complete(self, task_id: str, result: Any = None) -> bool:
        """Завершить задачу."""
        task = self._tasks.get(task_id)
        if task is None:
            return False
        task.status = TaskStatus.COMPLETED
        task.completed_at = time.time()
        task.result = result
        return True

    def fail(self, task_id: str, error: str = "") -> bool:
        """Пометить задачу как неудачную."""
        task = self._tasks.get(task_id)
        if task is None:
            return False
        task.status = TaskStatus.FAILED
        task.completed_at = time.time()
        task.error = error
        return True

    def cancel(self, task_id: str) -> bool:
        """Отменить задачу."""
        task = self._tasks.get(task_id)
        if task is None:
            return False
        task.status = TaskStatus.CANCELLED
        return True

    def get(self, task_id: str) -> TaskItem | None:
        return self._tasks.get(task_id)

    def get_by_status(self, status: str) -> list[TaskItem]:
        return [t for t in self._tasks.values() if t.status == status]

    def get_overdue(self) -> list[TaskItem]:
        return [
            t for t in self._tasks.values()
            if t.status == TaskStatus.PENDING and t.is_overdue
        ]

    @property
    def pending_count(self) -> int:
        return sum(
            1 for t in self._tasks.values() if t.status == TaskStatus.PENDING
        )

    @property
    def total_count(self) -> int:
        return len(self._tasks)

    def clear_completed(self) -> int:
        """Удалить завершённые задачи."""
        to_remove = [
            tid for tid, t in self._tasks.items()
            if t.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)
        ]
        for tid in to_remove:
            del self._tasks[tid]
        return len(to_remove)

    def get_stats(self) -> dict:
        counts: dict[str, int] = defaultdict(int)
        for t in self._tasks.values():
            counts[t.status] += 1
        return {
            "total": self.total_count,
            "pending": counts.get(TaskStatus.PENDING, 0),
            "running": counts.get(TaskStatus.RUNNING, 0),
            "completed": counts.get(TaskStatus.COMPLETED, 0),
            "failed": counts.get(TaskStatus.FAILED, 0),
            "overdue": len(self.get_overdue()),
            "max_size": self._max_size,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. TASK BATCHER — Группировка задач в батчи
# ═══════════════════════════════════════════════════════════════════════════════


class TaskBatcher:
    """
    Группирует однотипные задачи в батчи для эффективного выполнения.

    Пример: 5 API-запросов к одному сервису → 1 batch.
    """

    def __init__(
        self,
        max_batch_size: int = 10,
        batch_timeout: float = 5.0,
    ):
        self._max_batch_size = max_batch_size
        self._batch_timeout = batch_timeout
        self._batches: dict[str, TaskBatch] = {}
        self._batch_counter = 0

    def create_batches(
        self, tasks: list[TaskItem]
    ) -> list[TaskBatch]:
        """
        Сгруппировать задачи по task_type в батчи.
        """
        groups: dict[str, list[TaskItem]] = defaultdict(list)
        for task in tasks:
            groups[task.task_type].append(task)

        batches: list[TaskBatch] = []
        for task_type, group in groups.items():
            group.sort(key=lambda t: t.effective_priority)
            for i in range(0, len(group), self._max_batch_size):
                chunk = group[i: i + self._max_batch_size]
                self._batch_counter += 1
                batch = TaskBatch(
                    id=f"batch_{self._batch_counter}",
                    task_type=task_type,
                    tasks=chunk,
                )
                batches.append(batch)
                self._batches[batch.id] = batch
                for t in chunk:
                    t.status = TaskStatus.BATCHED

        batches.sort(
            key=lambda b: min(
                t.effective_priority for t in b.tasks
            ) if b.tasks else 99
        )
        return batches

    def get_batch(self, batch_id: str) -> TaskBatch | None:
        return self._batches.get(batch_id)

    def get_stats(self) -> dict:
        return {
            "total_batches": len(self._batches),
            "avg_batch_size": (
                sum(b.size for b in self._batches.values()) / len(self._batches)
                if self._batches else 0
            ),
            "max_batch_size": self._max_batch_size,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. TASK SCHEDULER — Планировщик
# ═══════════════════════════════════════════════════════════════════════════════


class TaskScheduler:
    """
    Планировщик задач с учётом зависимостей.

    - Топологическая сортировка задач
    - Определение параллельно выполнимых задач
    - Учёт зависимостей
    """

    def get_ready_tasks(self, tasks: list[TaskItem]) -> list[TaskItem]:
        """
        Вернуть задачи, готовые к выполнению.

        Задача готова, если:
        - Статус PENDING
        - Все зависимости завершены
        """
        completed_ids = {
            t.id for t in tasks if t.status == TaskStatus.COMPLETED
        }
        ready = []
        for t in tasks:
            if t.status != TaskStatus.PENDING:
                continue
            deps_met = all(d in completed_ids for d in t.dependencies)
            if deps_met:
                ready.append(t)
        ready.sort(key=lambda t: t.effective_priority)
        return ready

    def get_execution_plan(
        self, tasks: list[TaskItem]
    ) -> list[list[TaskItem]]:
        """
        Вернуть план выполнения: группы параллельных задач.

        Returns:
            Список волн: [[task1, task2], [task3], [task4, task5]]
        """
        remaining = {t.id: t for t in tasks if t.status == TaskStatus.PENDING}
        completed: set[str] = {
            t.id for t in tasks if t.status == TaskStatus.COMPLETED
        }
        waves: list[list[TaskItem]] = []

        max_iter = len(remaining) + 1
        for _ in range(max_iter):
            if not remaining:
                break
            wave = []
            for tid, t in remaining.items():
                deps_met = all(d in completed for d in t.dependencies)
                if deps_met:
                    wave.append(t)
            if not wave:
                # Circular dependency or all blocked
                wave = list(remaining.values())[:1]  # Force one
            wave.sort(key=lambda t: t.effective_priority)
            waves.append(wave)
            for t in wave:
                completed.add(t.id)
                remaining.pop(t.id, None)

        return waves

    def estimate_total_time(
        self,
        tasks: list[TaskItem],
        parallelism: int = 3,
    ) -> float:
        """Оценить общее время выполнения."""
        waves = self.get_execution_plan(tasks)
        total = 0.0
        for wave in waves:
            durations = sorted(
                [t.estimated_duration for t in wave], reverse=True
            )
            # С параллельностью: берём top-ceil(len/parallelism)
            parallel_groups = max(1, len(durations) // parallelism)
            wave_time = sum(durations[:parallel_groups + 1])
            total += wave_time
        return total


# ═══════════════════════════════════════════════════════════════════════════════
# FACADE: TaskPrioritizer
# ═══════════════════════════════════════════════════════════════════════════════


class TaskPrioritizer:
    """
    Фасад для управления приоритетами и батчингом задач.

    Использование:
        prioritizer = TaskPrioritizer()

        # Добавить задачи
        prioritizer.add_task("t1", "Search API", priority="high", task_type="api")
        prioritizer.add_task("t2", "Process data", priority="low", dependencies=["t1"])

        # Получить следующую задачу
        task = prioritizer.next_task()

        # Получить план
        plan = prioritizer.get_plan()
    """

    PRIORITY_MAP = {
        "critical": PriorityLevel.CRITICAL,
        "high": PriorityLevel.HIGH,
        "medium": PriorityLevel.MEDIUM,
        "low": PriorityLevel.LOW,
        "background": PriorityLevel.BACKGROUND,
    }

    def __init__(self):
        self.queue = PriorityQueue()
        self.batcher = TaskBatcher()
        self.scheduler = TaskScheduler()
        self._task_counter = 0

    def add_task(
        self,
        task_id: str | None = None,
        name: str = "",
        priority: str = "medium",
        task_type: str = "general",
        payload: dict | None = None,
        dependencies: list[str] | None = None,
        deadline_sec: float | None = None,
        estimated_duration: float = 1.0,
        tags: list[str] | None = None,
    ) -> TaskItem:
        """Добавить задачу."""
        if task_id is None:
            self._task_counter += 1
            task_id = f"task_{self._task_counter}"

        prio = self.PRIORITY_MAP.get(priority, PriorityLevel.MEDIUM)
        deadline = time.time() + deadline_sec if deadline_sec else None

        task = TaskItem(
            id=task_id,
            name=name or task_id,
            priority=prio,
            task_type=task_type,
            payload=payload or {},
            dependencies=dependencies or [],
            deadline=deadline,
            estimated_duration=estimated_duration,
            tags=tags or [],
        )
        self.queue.add(task)
        return task

    def next_task(self) -> TaskItem | None:
        """Получить задачу с наивысшим приоритетом."""
        return self.queue.pop()

    def complete_task(self, task_id: str, result: Any = None) -> bool:
        return self.queue.complete(task_id, result)

    def fail_task(self, task_id: str, error: str = "") -> bool:
        return self.queue.fail(task_id, error)

    def get_plan(self) -> list[list[dict]]:
        """Получить план выполнения."""
        pending = self.queue.get_by_status(TaskStatus.PENDING)
        waves = self.scheduler.get_execution_plan(pending)
        return [[t.to_dict() for t in wave] for wave in waves]

    def create_batches(self) -> list[TaskBatch]:
        """Создать батчи из pending задач."""
        pending = self.queue.get_by_status(TaskStatus.PENDING)
        return self.batcher.create_batches(pending)

    def get_overdue(self) -> list[TaskItem]:
        return self.queue.get_overdue()

    def estimate_time(self) -> float:
        """Оценить общее время выполнения."""
        pending = self.queue.get_by_status(TaskStatus.PENDING)
        return self.scheduler.estimate_total_time(pending)

    def get_stats(self) -> dict:
        return {
            "queue": self.queue.get_stats(),
            "batcher": self.batcher.get_stats(),
        }


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

task_prioritizer = TaskPrioritizer()
