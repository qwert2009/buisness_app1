"""
PDS-Ultimate Cognitive Engine (Part 3)
========================================
Когнитивный движок мирового уровня.

Реализует высшие мыслительные функции агента:

1. DAG Planner — нелинейное планирование (граф зависимостей, параллельные задачи)
2. Task Manager — множественные задачи с приоритетами и дедлайнами
3. Multi-step Self-Correction — если шаг не удался → пересмотр плана
4. Metacognition — агент следит за собственным мышлением
5. Confidence & Uncertainty — оценка уверенности, допоиск при низкой
6. Goal Integrity — «я всё ещё решаю исходную цель?»
7. Dynamic Role Switching — Critic / Strategist / Summarizer / Executor
8. Self-Query Expansion — уточнение запросов на основе промежуточных результатов
9. Intermediate Goal Generation — декомпозиция сложных целей
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from pds_ultimate.config import logger

# ═══════════════════════════════════════════════════════════════════════════════
# 1. DAG PLANNER — Directed Acyclic Graph Planning
# ═══════════════════════════════════════════════════════════════════════════════


class NodeStatus(str, Enum):
    """Статус узла DAG."""
    PENDING = "pending"
    READY = "ready"        # Все зависимости выполнены → готов к запуску
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"     # Пропущен (зависимость провалилась)


@dataclass
class DAGNode:
    """
    Узел в DAG — одна задача/шаг плана.

    Поддерживает:
    - Зависимости (depends_on) — не выполняется пока не завершены все зависимости
    - Приоритет — при равных условиях, выполняется первым
    - Retry — автоматическая повторная попытка
    - Timeout — ограничение по времени
    """
    id: str                           # Уникальный ID узла
    description: str                  # Описание задачи
    depends_on: list[str] = field(default_factory=list)
    priority: int = 0                 # 0=normal, выше=приоритетнее
    status: NodeStatus = NodeStatus.PENDING
    result: str | None = None
    error: str | None = None
    tool_name: str | None = None      # Инструмент для выполнения
    tool_params: dict | None = None
    retry_count: int = 0
    max_retries: int = 2
    timeout_seconds: int = 60
    started_at: float | None = None
    completed_at: float | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def duration_ms(self) -> int:
        """Время выполнения в мс."""
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at) * 1000)
        return 0

    @property
    def is_terminal(self) -> bool:
        """Узел завершён (успешно или нет)."""
        return self.status in (
            NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.SKIPPED
        )

    def can_retry(self) -> bool:
        """Можно ли повторить."""
        return self.retry_count < self.max_retries


class DAGPlan:
    """
    DAG-план — направленный ациклический граф задач.

    Преимущества перед линейным планом:
    - Параллельное выполнение независимых задач
    - Автоматическое определение зависимостей
    - Self-correction: если узел провалился → пересмотр
    - Визуализация прогресса
    """

    def __init__(self, goal: str):
        self.goal = goal
        self.nodes: dict[str, DAGNode] = {}
        self.created_at = time.time()
        self._execution_order: list[str] = []
        self._revision_count: int = 0

    def add_node(
        self,
        node_id: str,
        description: str,
        depends_on: list[str] | None = None,
        priority: int = 0,
        tool_name: str | None = None,
        tool_params: dict | None = None,
        max_retries: int = 2,
        timeout_seconds: int = 60,
    ) -> DAGNode:
        """Добавить узел в граф."""
        # Валидация: зависимости должны существовать
        deps = depends_on or []
        for dep in deps:
            if dep not in self.nodes and dep != node_id:
                # Зависимость ещё не добавлена — допускаем (добавится позже)
                pass

        node = DAGNode(
            id=node_id,
            description=description,
            depends_on=deps,
            priority=priority,
            tool_name=tool_name,
            tool_params=tool_params,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
        )
        self.nodes[node_id] = node
        return node

    def remove_node(self, node_id: str) -> None:
        """Удалить узел и его зависимости."""
        if node_id in self.nodes:
            del self.nodes[node_id]
            # Удаляем из зависимостей других узлов
            for node in self.nodes.values():
                if node_id in node.depends_on:
                    node.depends_on.remove(node_id)

    def get_ready_nodes(self) -> list[DAGNode]:
        """
        Получить все узлы, готовые к выполнению.

        Узел готов если:
        1. Статус PENDING или READY
        2. Все зависимости COMPLETED

        НЕ мутирует статус — это делает mark_running().
        """
        ready = []
        for node in self.nodes.values():
            if node.status not in (NodeStatus.PENDING, NodeStatus.READY):
                continue

            deps_done = all(
                self.nodes.get(dep_id, DAGNode(
                    id=dep_id, description="")).status
                == NodeStatus.COMPLETED
                for dep_id in node.depends_on
            )

            if deps_done:
                ready.append(node)

        # Сортируем по приоритету (высокий → первый)
        ready.sort(key=lambda n: n.priority, reverse=True)
        return ready

    def mark_running(self, node_id: str) -> None:
        """Отметить узел как запущенный."""
        if node_id in self.nodes:
            node = self.nodes[node_id]
            node.status = NodeStatus.RUNNING
            node.started_at = time.time()

    def topological_sort(self) -> list[str]:
        """
        Топологическая сортировка DAG.

        Возвращает порядок выполнения с учётом зависимостей.
        Если граф имеет цикл — возвращает partial order.
        """
        in_degree: dict[str, int] = {nid: 0 for nid in self.nodes}
        for node in self.nodes.values():
            for dep in node.depends_on:
                if dep in in_degree:
                    in_degree[node.id] = in_degree.get(node.id, 0) + 1

        # Очередь: узлы без входящих рёбер
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        queue.sort(key=lambda nid: self.nodes[nid].priority, reverse=True)

        result = []
        while queue:
            nid = queue.pop(0)
            result.append(nid)
            # Уменьшаем in_degree для зависимых узлов
            for node in self.nodes.values():
                if nid in node.depends_on:
                    in_degree[node.id] -= 1
                    if in_degree[node.id] == 0:
                        queue.append(node.id)
            queue.sort(key=lambda nid: self.nodes[nid].priority, reverse=True)

        return result

    def get_parallel_groups(self) -> list[list[str]]:
        """
        Разбить план на группы параллельно выполняемых шагов.

        Returns:
            Список групп: [["step_1", "step_2"], ["step_3"], ...]
        """
        groups: list[list[str]] = []
        completed: set[str] = set()
        remaining = set(self.nodes.keys())

        while remaining:
            # Найти все узлы, чьи зависимости выполнены
            group = []
            for nid in list(remaining):
                node = self.nodes[nid]
                if all(d in completed for d in node.depends_on):
                    group.append(nid)

            if not group:
                break  # Цикл или ошибка

            group.sort(key=lambda nid: self.nodes[nid].priority, reverse=True)
            groups.append(group)
            for nid in group:
                remaining.discard(nid)
                completed.add(nid)

        return groups

    def complete_node(self, node_id: str, result: str) -> None:
        """Отметить узел как завершённый."""
        if node_id in self.nodes:
            node = self.nodes[node_id]
            node.status = NodeStatus.COMPLETED
            node.result = result
            node.completed_at = time.time()

    def fail_node(self, node_id: str, error: str) -> bool:
        """
        Отметить узел как проваленный.

        Returns:
            True если можно retry, False если исчерпаны попытки.
        """
        if node_id not in self.nodes:
            return False

        node = self.nodes[node_id]
        node.retry_count += 1

        if node.can_retry():
            # Сброс для повторной попытки
            node.status = NodeStatus.PENDING
            node.error = error
            logger.info(
                f"DAG node '{node_id}' retry {node.retry_count}/"
                f"{node.max_retries}: {error}"
            )
            return True
        else:
            node.status = NodeStatus.FAILED
            node.error = error
            node.completed_at = time.time()
            # Пропускаем зависимые узлы
            self._skip_dependents(node_id)
            return False

    def _skip_dependents(self, failed_node_id: str) -> None:
        """Пропустить узлы, зависящие от проваленного."""
        for node in self.nodes.values():
            if (failed_node_id in node.depends_on
                    and node.status == NodeStatus.PENDING):
                node.status = NodeStatus.SKIPPED
                node.error = f"Зависимость '{failed_node_id}' провалена"
                self._skip_dependents(node.id)

    def has_cycle(self) -> bool:
        """Проверка на циклы в графе (DAG не должен иметь циклов)."""
        visited: set[str] = set()
        path: set[str] = set()

        def _dfs(node_id: str) -> bool:
            if node_id in path:
                return True  # Цикл!
            if node_id in visited:
                return False

            visited.add(node_id)
            path.add(node_id)

            node = self.nodes.get(node_id)
            if node:
                for dep in node.depends_on:
                    if _dfs(dep):
                        return True

            path.discard(node_id)
            return False

        for nid in self.nodes:
            if _dfs(nid):
                return True
        return False

    @property
    def is_complete(self) -> bool:
        """Все узлы завершены."""
        return all(n.is_terminal for n in self.nodes.values())

    @property
    def progress(self) -> float:
        """Прогресс выполнения (0.0 - 1.0)."""
        if not self.nodes:
            return 1.0
        done = sum(1 for n in self.nodes.values() if n.is_terminal)
        return done / len(self.nodes)

    @property
    def has_failures(self) -> bool:
        """Есть ли проваленные узлы."""
        return any(
            n.status == NodeStatus.FAILED for n in self.nodes.values()
        )

    def get_summary(self) -> str:
        """Текстовое описание плана с прогрессом."""
        if not self.nodes:
            return "Пустой план."

        lines = [f"🎯 ЦЕЛЬ: {self.goal}"]
        lines.append(f"📊 Прогресс: {self.progress:.0%} "
                     f"({len(self.nodes)} узлов)")

        if self._revision_count > 0:
            lines.append(f"🔄 Ревизий плана: {self._revision_count}")

        icons = {
            NodeStatus.PENDING: "⏳",
            NodeStatus.READY: "🟡",
            NodeStatus.RUNNING: "🔵",
            NodeStatus.COMPLETED: "✅",
            NodeStatus.FAILED: "❌",
            NodeStatus.SKIPPED: "⏭️",
        }

        for node in self.nodes.values():
            icon = icons.get(node.status, "?")
            deps = ""
            if node.depends_on:
                deps = f" [← {', '.join(node.depends_on)}]"
            result_str = ""
            if node.result:
                result_str = f"\n     → {node.result[:80]}"
            elif node.error:
                result_str = f"\n     ⚠ {node.error[:80]}"

            lines.append(f"  {icon} {node.id}: {node.description}"
                         f"{deps}{result_str}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Сериализация для LLM / DB."""
        return {
            "goal": self.goal,
            "progress": self.progress,
            "revision_count": self._revision_count,
            "nodes": {
                nid: {
                    "description": n.description,
                    "status": n.status.value,
                    "depends_on": n.depends_on,
                    "priority": n.priority,
                    "result": n.result,
                    "error": n.error,
                    "tool_name": n.tool_name,
                    "retry_count": n.retry_count,
                }
                for nid, n in self.nodes.items()
            },
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. TASK MANAGER — Multiple Tasks with Priorities
# ═══════════════════════════════════════════════════════════════════════════════


class TaskPriority(str, Enum):
    """Приоритеты задач."""
    CRITICAL = "critical"    # Выполнить немедленно
    HIGH = "high"            # Выполнить как можно скорее
    NORMAL = "normal"        # Обычный приоритет
    LOW = "low"              # Когда будет время
    BACKGROUND = "background"  # Фоновая задача

    @property
    def weight(self) -> int:
        return {
            "critical": 100,
            "high": 75,
            "normal": 50,
            "low": 25,
            "background": 10,
        }[self.value]


@dataclass
class ManagedTask:
    """
    Управляемая задача (Task Manager).

    Задача может содержать DAG-план и выполняться параллельно с другими.
    """
    id: str
    description: str
    priority: TaskPriority = TaskPriority.NORMAL
    deadline: datetime | None = None
    plan: DAGPlan | None = None
    status: str = "pending"        # pending, active, completed, failed, paused
    chat_id: int | None = None
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    result: str | None = None
    error: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def is_overdue(self) -> bool:
        """Задача просрочена."""
        if self.deadline and self.status not in ("completed", "failed"):
            return datetime.utcnow() > self.deadline
        return False

    @property
    def urgency_score(self) -> float:
        """
        Оценка срочности (для приоритизации).

        Учитывает: приоритет + дедлайн + время в очереди.
        """
        score = float(self.priority.weight)

        # Дедлайн boost
        if self.deadline:
            remaining = (self.deadline - datetime.utcnow()).total_seconds()
            if remaining <= 0:
                score += 200  # Просрочена!
            elif remaining < 3600:
                score += 100  # < 1 часа
            elif remaining < 86400:
                score += 50   # < 1 дня
            elif remaining < 604800:
                score += 20   # < 1 недели

        # Время в очереди (чем дольше ждёт, тем срочнее)
        age_hours = (time.time() - self.created_at) / 3600
        score += min(30, age_hours * 2)

        return score


class TaskManager:
    """
    Менеджер задач — ведёт несколько задач одновременно.

    Возможности:
    - Приоритизация (critical > high > normal > low > background)
    - Дедлайны с отслеживанием просрочки
    - Параллельное ведение нескольких задач
    - Auto-scheduling: выбирает следующую задачу по urgency_score
    """

    MAX_ACTIVE_TASKS = 10

    def __init__(self):
        self._tasks: dict[str, ManagedTask] = {}
        self._next_id = 1

    def create_task(
        self,
        description: str,
        priority: TaskPriority | str = TaskPriority.NORMAL,
        deadline: datetime | None = None,
        chat_id: int | None = None,
        tags: list[str] | None = None,
    ) -> ManagedTask:
        """Создать новую задачу."""
        if isinstance(priority, str):
            try:
                priority = TaskPriority(priority)
            except ValueError:
                priority = TaskPriority.NORMAL

        task_id = f"task_{self._next_id}"
        self._next_id += 1

        task = ManagedTask(
            id=task_id,
            description=description,
            priority=priority,
            deadline=deadline,
            chat_id=chat_id,
            tags=tags or [],
        )
        self._tasks[task_id] = task
        logger.debug(
            f"Task created: {task_id} [{priority.value}] {description[:60]}")
        return task

    def get_task(self, task_id: str) -> ManagedTask | None:
        """Получить задачу по ID."""
        return self._tasks.get(task_id)

    def complete_task(self, task_id: str, result: str) -> None:
        """Завершить задачу."""
        task = self._tasks.get(task_id)
        if task:
            task.status = "completed"
            task.result = result
            task.completed_at = time.time()

    def fail_task(self, task_id: str, error: str) -> None:
        """Провалить задачу."""
        task = self._tasks.get(task_id)
        if task:
            task.status = "failed"
            task.error = error
            task.completed_at = time.time()

    def pause_task(self, task_id: str) -> None:
        """Поставить задачу на паузу."""
        task = self._tasks.get(task_id)
        if task and task.status == "active":
            task.status = "paused"

    def resume_task(self, task_id: str) -> None:
        """Возобновить задачу."""
        task = self._tasks.get(task_id)
        if task and task.status == "paused":
            task.status = "pending"

    def get_next_task(self) -> ManagedTask | None:
        """
        Получить следующую задачу для выполнения.

        Выбирает по urgency_score (приоритет + дедлайн + время ожидания).
        """
        pending = [
            t for t in self._tasks.values()
            if t.status in ("pending", "paused")
        ]
        if not pending:
            return None

        # Сортируем по urgency_score (убывание)
        pending.sort(key=lambda t: t.urgency_score, reverse=True)
        return pending[0]

    def get_active_tasks(self, chat_id: int | None = None) -> list[ManagedTask]:
        """Получить активные задачи."""
        tasks = [
            t for t in self._tasks.values()
            if t.status in ("pending", "active", "paused")
        ]
        if chat_id is not None:
            tasks = [t for t in tasks if t.chat_id == chat_id]
        tasks.sort(key=lambda t: t.urgency_score, reverse=True)
        return tasks

    def get_overdue_tasks(self) -> list[ManagedTask]:
        """Просроченные задачи."""
        return [t for t in self._tasks.values() if t.is_overdue]

    def get_completed_tasks(
        self, limit: int = 10
    ) -> list[ManagedTask]:
        """Последние завершённые задачи."""
        completed = [
            t for t in self._tasks.values()
            if t.status == "completed"
        ]
        completed.sort(key=lambda t: t.completed_at or 0, reverse=True)
        return completed[:limit]

    @property
    def stats(self) -> dict:
        """Статистика задач."""
        statuses: dict[str, int] = {}
        for t in self._tasks.values():
            statuses[t.status] = statuses.get(t.status, 0) + 1
        return {
            "total": len(self._tasks),
            "by_status": statuses,
            "overdue": len(self.get_overdue_tasks()),
        }

    def get_summary(self, chat_id: int | None = None) -> str:
        """Текстовое описание активных задач."""
        active = self.get_active_tasks(chat_id)
        if not active:
            return "Нет активных задач."

        overdue = self.get_overdue_tasks()

        lines = [f"📋 ЗАДАЧИ ({len(active)} активных):"]

        if overdue:
            lines.append(f"⚠️ Просрочено: {len(overdue)}")

        icons = {
            "pending": "⏳",
            "active": "🔵",
            "paused": "⏸️",
        }

        for task in active[:10]:
            icon = icons.get(task.status, "?")
            priority_icon = {
                TaskPriority.CRITICAL: "🔴",
                TaskPriority.HIGH: "🟠",
                TaskPriority.NORMAL: "🟡",
                TaskPriority.LOW: "🟢",
                TaskPriority.BACKGROUND: "⚪",
            }.get(task.priority, "")

            deadline_str = ""
            if task.deadline:
                remaining = task.deadline - datetime.utcnow()
                if remaining.total_seconds() < 0:
                    deadline_str = " ⏰ПРОСРОЧЕНО"
                elif remaining.total_seconds() < 3600:
                    deadline_str = f" ⏰{remaining.seconds // 60}мин"
                elif remaining.total_seconds() < 86400:
                    deadline_str = f" ⏰{remaining.seconds // 3600}ч"
                else:
                    deadline_str = f" ⏰{remaining.days}дн"

            lines.append(
                f"  {icon}{priority_icon} {task.description[:60]}"
                f"{deadline_str}"
            )

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. DYNAMIC ROLES — Critic / Strategist / Summarizer / Executor
# ═══════════════════════════════════════════════════════════════════════════════


class AgentRole(str, Enum):
    """Динамические роли агента (один API — разные «шляпы»)."""
    EXECUTOR = "executor"         # Выполняет задачу
    CRITIC = "critic"             # Оценивает качество
    STRATEGIST = "strategist"     # Строит стратегию
    SUMMARIZER = "summarizer"     # Сжимает информацию
    ANALYST = "analyst"           # Анализирует данные
    PLANNER = "planner"           # Планирует DAG
    RESEARCHER = "researcher"     # Ищет информацию
    VERIFIER = "verifier"         # Проверяет факты


# System prompts для каждой роли
ROLE_PROMPTS: dict[str, str] = {
    AgentRole.EXECUTOR: (
        "Ты — Executor. Твоя задача: ВЫПОЛНИТЬ конкретное действие точно и эффективно. "
        "Не рассуждай лишнего — делай. Используй инструменты. "
        "Верни результат в JSON: {{\"result\": \"...\", \"success\": true/false}}"
    ),
    AgentRole.CRITIC: (
        "Ты — Critic. Твоя задача: ОЦЕНИТЬ качество ответа/решения. "
        "Найди слабые места, ошибки, пропуски. Будь строгим и объективным. "
        "Верни JSON: {{\"quality\": 0.0-1.0, \"issues\": [...], "
        "\"improvements\": [...], \"critical_flaws\": true/false}}"
    ),
    AgentRole.STRATEGIST: (
        "Ты — Strategist. Твоя задача: разработать СТРАТЕГИЮ решения задачи. "
        "Определи цели, ресурсы, риски, альтернативы. Думай на 3 шага вперёд. "
        "Верни JSON: {{\"strategy\": \"...\", \"steps\": [...], "
        "\"risks\": [...], \"alternatives\": [...]}}"
    ),
    AgentRole.SUMMARIZER: (
        "Ты — Summarizer. Сожми информацию в краткое структурированное саммари. "
        "Ничего не пропусти — каждый факт важен. Удали воду. "
        "Верни JSON: {{\"summary\": \"...\", \"key_facts\": [...], "
        "\"action_items\": [...]}}"
    ),
    AgentRole.ANALYST: (
        "Ты — Analyst. Проанализируй данные, найди паттерны, аномалии, тренды. "
        "Сделай выводы на основе фактов, не предположений. "
        "Верни JSON: {{\"analysis\": \"...\", \"findings\": [...], "
        "\"confidence\": 0.0-1.0}}"
    ),
    AgentRole.PLANNER: (
        "Ты — Planner. Построй DAG-план выполнения задачи. "
        "Определи шаги, зависимости, что можно выполнять параллельно. "
        "Верни JSON: {{\"nodes\": [{{\"id\": \"step_N\", \"description\": \"...\", "
        "\"depends_on\": [\"step_X\"], \"priority\": 0-10, "
        "\"tool\": \"tool_name_or_null\"}}]}}"
    ),
    AgentRole.RESEARCHER: (
        "Ты — Researcher. Найди максимум информации по теме. "
        "Формулируй поисковые запросы, проверяй источники, сравнивай данные. "
        "Верни JSON: {{\"findings\": [...], \"sources\": [...], "
        "\"confidence\": 0.0-1.0, \"gaps\": [...]}}"
    ),
    AgentRole.VERIFIER: (
        "Ты — Verifier. Проверь факты и утверждения на корректность. "
        "Ищи противоречия, устаревшие данные, ошибки. "
        "Верни JSON: {{\"verified\": true/false, \"issues\": [...], "
        "\"corrections\": [...]}}"
    ),
}


class RoleManager:
    """
    Менеджер динамических ролей.

    Один DeepSeek API → разные роли (через system prompt).
    Роли вызываются только при необходимости.
    Per-chat роли: каждый пользователь может иметь свою активную роль.
    """

    def __init__(self):
        self._active_role: AgentRole = AgentRole.EXECUTOR
        self._per_chat_roles: dict[int, AgentRole] = {}
        self._role_history: list[dict[str, Any]] = []

    @property
    def active_role(self) -> AgentRole:
        return self._active_role

    def get_role_prompt(self, role: AgentRole | str) -> str:
        """Получить system prompt для роли."""
        if isinstance(role, str):
            try:
                role = AgentRole(role)
            except ValueError:
                return ROLE_PROMPTS.get(AgentRole.EXECUTOR, "")
        return ROLE_PROMPTS.get(role, "")

    def switch_role(self, role: AgentRole | str) -> str:
        """
        Переключить роль. Возвращает system prompt для новой роли.
        """
        if isinstance(role, str):
            try:
                role = AgentRole(role)
            except ValueError:
                logger.warning(
                    f"Unknown role: {role}, keeping {self._active_role}")
                return self.get_role_prompt(self._active_role)

        old_role = self._active_role
        self._active_role = role
        self._role_history.append({
            "from": old_role.value,
            "to": role.value,
            "timestamp": time.time(),
        })
        logger.debug(f"Role switch: {old_role.value} → {role.value}")
        return self.get_role_prompt(role)

    def suggest_role(self, task_type: str) -> AgentRole:
        """
        Определить лучшую роль для типа задачи.
        """
        role_map = {
            "execute": AgentRole.EXECUTOR,
            "do": AgentRole.EXECUTOR,
            "critique": AgentRole.CRITIC,
            "evaluate": AgentRole.CRITIC,
            "review": AgentRole.CRITIC,
            "plan": AgentRole.PLANNER,
            "schedule": AgentRole.PLANNER,
            "organize": AgentRole.PLANNER,
            "search": AgentRole.RESEARCHER,
            "find": AgentRole.RESEARCHER,
            "research": AgentRole.RESEARCHER,
            "analyze": AgentRole.ANALYST,
            "compare": AgentRole.ANALYST,
            "summarize": AgentRole.SUMMARIZER,
            "compress": AgentRole.SUMMARIZER,
            "brief": AgentRole.SUMMARIZER,
            "verify": AgentRole.VERIFIER,
            "check": AgentRole.VERIFIER,
            "fact-check": AgentRole.VERIFIER,
            "strategy": AgentRole.STRATEGIST,
            "decide": AgentRole.STRATEGIST,
        }

        task_lower = task_type.lower()
        for keyword, role in role_map.items():
            if keyword in task_lower:
                return role

        return AgentRole.EXECUTOR

    def get_chat_role(self, chat_id: int) -> AgentRole:
        """Получить роль для конкретного чата."""
        return self._per_chat_roles.get(chat_id, self._active_role)

    def set_chat_role(self, chat_id: int, role: AgentRole | str) -> str:
        """Установить роль для конкретного чата."""
        if isinstance(role, str):
            try:
                role = AgentRole(role)
            except ValueError:
                return self.get_role_prompt(self.get_chat_role(chat_id))
        self._per_chat_roles[chat_id] = role
        return self.get_role_prompt(role)

    @property
    def history(self) -> list[dict]:
        return self._role_history[-20:]


# ═══════════════════════════════════════════════════════════════════════════════
# 4. COGNITIVE ENGINE — Metacognition + Confidence + Goal Integrity
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ConfidenceAssessment:
    """Оценка уверенности в выводе/решении."""
    score: float              # 0.0-1.0
    reasoning: str            # Почему такой score
    gaps: list[str]           # Что нехватает
    should_search_more: bool  # Нужен ли допоиск
    suggested_queries: list[str]  # Уточняющие запросы

    @property
    def is_low(self) -> bool:
        return self.score < 0.5

    @property
    def is_medium(self) -> bool:
        return 0.5 <= self.score < 0.75

    @property
    def is_high(self) -> bool:
        return self.score >= 0.75


@dataclass
class GoalIntegrityCheck:
    """Результат проверки целостности цели."""
    aligned: bool             # Мы всё ещё решаем исходную цель?
    original_goal: str
    current_focus: str
    drift_reason: str | None  # Причина отклонения (если есть)
    recommendation: str       # Что делать дальше


@dataclass
class MetacognitiveState:
    """
    Метакогнитивное состояние — агент следит за своим мышлением.

    Отслеживает:
    - Сколько времени уже тратится на задачу
    - Прогресс к цели
    - Качество промежуточных результатов
    - Уровень уверенности
    - Наличие зацикливания
    """
    thinking_time_seconds: float = 0.0
    iterations_used: int = 0
    quality_scores: list[float] = field(default_factory=list)
    confidence_history: list[float] = field(default_factory=list)
    repeated_actions: list[str] = field(default_factory=list)
    goal_checks: list[GoalIntegrityCheck] = field(default_factory=list)

    @property
    def avg_quality(self) -> float:
        if not self.quality_scores:
            return 0.0
        return sum(self.quality_scores) / len(self.quality_scores)

    @property
    def avg_confidence(self) -> float:
        if not self.confidence_history:
            return 0.0
        return sum(self.confidence_history) / len(self.confidence_history)

    @property
    def is_stuck(self) -> bool:
        """Определить зацикливание."""
        if len(self.repeated_actions) < 3:
            return False
        # Если последние 3 действия одинаковые
        last3 = self.repeated_actions[-3:]
        return len(set(last3)) == 1

    @property
    def is_declining(self) -> bool:
        """
        Уверенность снижается — агент всё менее уверен.

        Если последние 3 оценки уверенности снижаются → тревога.
        """
        if len(self.confidence_history) < 3:
            return False
        last3 = self.confidence_history[-3:]
        return last3[0] > last3[1] > last3[2]

    @property
    def low_confidence_streak(self) -> int:
        """Количество подряд идущих низких оценок уверенности (< 0.5)."""
        streak = 0
        for c in reversed(self.confidence_history):
            if c < 0.5:
                streak += 1
            else:
                break
        return streak

    @property
    def is_taking_too_long(self) -> bool:
        """Слишком долго на одной задаче."""
        return self.thinking_time_seconds > 120  # > 2 мин

    @property
    def should_abort(self) -> bool:
        """Пора ли прекращать попытки."""
        if self.is_stuck:
            return True
        if self.iterations_used > 15:
            return True
        if self.thinking_time_seconds > 300:  # > 5 мин
            return True
        if self.low_confidence_streak >= 4:
            return True  # 4+ раза подряд низкая уверенность
        return False


class CognitiveEngine:
    """
    Когнитивный движок — высшие мыслительные функции.

    Объединяет:
    - DAG Planning
    - Task Management
    - Role Switching
    - Metacognition & Self-Reflection
    - Confidence Tracking
    - Goal Integrity
    - Self-Query Expansion
    - Intermediate Goal Generation
    """

    # Промпты для когнитивных операций
    PLAN_GENERATION_PROMPT = (
        "Ты — DAG Planner. Разбей задачу на шаги (граф зависимостей).\n\n"
        "ЗАДАЧА: {goal}\n\n"
        "ДОСТУПНЫЕ ИНСТРУМЕНТЫ: {tools}\n\n"
        "Верни JSON:\n"
        '{{"nodes": [{{"id": "step_1", "description": "...", '
        '"depends_on": [], "priority": 5, "tool": null}}, ...]}}\n\n'
        "ПРАВИЛА:\n"
        "- Шаги без зависимостей можно выполнять параллельно\n"
        "- depends_on — список ID шагов, которые должны завершиться ДО этого\n"
        "- priority: 0-10 (10=самый важный)\n"
        "- tool: имя инструмента или null если LLM сам"
    )

    CONFIDENCE_PROMPT = (
        "Оцени уверенность в следующем выводе/ответе.\n\n"
        "ЗАПРОС: {query}\n"
        "ОТВЕТ: {answer}\n"
        "КОНТЕКСТ: {context}\n\n"
        "Верни JSON:\n"
        '{{"score": 0.0-1.0, "reasoning": "почему", '
        '"gaps": ["чего не хватает"], '
        '"should_search_more": true/false, '
        '"suggested_queries": ["уточняющий запрос"]}}'
    )

    GOAL_INTEGRITY_PROMPT = (
        "Проверь: мы всё ещё решаем исходную цель?\n\n"
        "ИСХОДНАЯ ЦЕЛЬ: {original_goal}\n"
        "ТЕКУЩИЙ ФОКУС: {current_focus}\n"
        "ВЫПОЛНЕННЫЕ ШАГИ: {completed_steps}\n\n"
        "Верни JSON:\n"
        '{{"aligned": true/false, "drift_reason": "причина отклонения или null", '
        '"recommendation": "что делать дальше"}}'
    )

    QUERY_EXPANSION_PROMPT = (
        "Расширь поисковый запрос для более полных результатов.\n\n"
        "ИСХОДНЫЙ ЗАПРОС: {query}\n"
        "ПРОМЕЖУТОЧНЫЕ РЕЗУЛЬТАТЫ: {intermediate}\n"
        "ЧЕГО НЕ ХВАТАЕТ: {gaps}\n\n"
        "Верни JSON:\n"
        '{{"expanded_queries": ["запрос1", "запрос2", "запрос3"], '
        '"reasoning": "почему эти запросы лучше"}}'
    )

    DECOMPOSITION_PROMPT = (
        "Декомпозируй сложную цель на промежуточные подцели.\n\n"
        "ЦЕЛЬ: {goal}\n"
        "КОНТЕКСТ: {context}\n\n"
        "Верни JSON:\n"
        '{{"sub_goals": [{{"goal": "подцель", "priority": 0-10, '
        '"estimated_steps": 1-5}}, ...], '
        '"reasoning": "почему именно такая декомпозиция"}}'
    )

    SELF_CORRECTION_PROMPT = (
        "Шаг плана провалился. Исправь план.\n\n"
        "ЦЕЛЬ: {goal}\n"
        "ПРОВАЛЕННЫЙ ШАГ: {failed_step}\n"
        "ОШИБКА: {error}\n"
        "ТЕКУЩИЙ ПЛАН: {current_plan}\n\n"
        "Верни JSON:\n"
        '{{"correction": "описание исправления", '
        '"new_nodes": [{{"id": "fix_1", "description": "...", '
        '"depends_on": [], "priority": 8}}], '
        '"remove_nodes": ["node_id_to_remove"], '
        '"reasoning": "почему это исправит проблему"}}'
    )

    def __init__(self):
        self._task_manager = TaskManager()
        self._role_manager = RoleManager()
        self._metacog: dict[int, MetacognitiveState] = {}  # per chat_id
        self._active_plans: dict[int, DAGPlan] = {}  # per chat_id

    # ─── Properties ──────────────────────────────────────────────────────

    @property
    def task_manager(self) -> TaskManager:
        return self._task_manager

    @property
    def role_manager(self) -> RoleManager:
        return self._role_manager

    # ─── Metacognition ───────────────────────────────────────────────────

    def get_metacog(self, chat_id: int) -> MetacognitiveState:
        """Получить метакогнитивное состояние для чата."""
        if chat_id not in self._metacog:
            self._metacog[chat_id] = MetacognitiveState()
        return self._metacog[chat_id]

    def reset_metacog(self, chat_id: int) -> None:
        """Сбросить метакогнитивное состояние."""
        self._metacog[chat_id] = MetacognitiveState()

    def record_action(self, chat_id: int, action_type: str,
                      duration_s: float = 0) -> None:
        """Записать действие для отслеживания зацикливания."""
        mc = self.get_metacog(chat_id)
        mc.repeated_actions.append(action_type)
        mc.iterations_used += 1
        mc.thinking_time_seconds += duration_s

        # Ограничиваем историю
        if len(mc.repeated_actions) > 50:
            mc.repeated_actions = mc.repeated_actions[-50:]

    def record_confidence(self, chat_id: int, score: float) -> None:
        """Записать оценку уверенности."""
        mc = self.get_metacog(chat_id)
        mc.confidence_history.append(max(0.0, min(1.0, score)))

    def record_quality(self, chat_id: int, score: float) -> None:
        """Записать оценку качества."""
        mc = self.get_metacog(chat_id)
        mc.quality_scores.append(max(0.0, min(1.0, score)))

    # ─── DAG Planning ────────────────────────────────────────────────────

    def create_plan(self, chat_id: int, goal: str) -> DAGPlan:
        """Создать новый DAG-план для чата."""
        plan = DAGPlan(goal=goal)
        self._active_plans[chat_id] = plan
        return plan

    def get_plan(self, chat_id: int) -> DAGPlan | None:
        """Получить текущий план."""
        return self._active_plans.get(chat_id)

    def clear_plan(self, chat_id: int) -> None:
        """Удалить план."""
        self._active_plans.pop(chat_id, None)

    async def generate_plan(
        self,
        goal: str,
        tools_description: str,
        llm_engine=None,
    ) -> DAGPlan:
        """
        Сгенерировать DAG-план через LLM.

        Агент-планировщик анализирует цель и создаёт
        граф задач с зависимостями.
        """
        if not llm_engine:
            from pds_ultimate.core.llm_engine import llm_engine as _engine
            llm_engine = _engine

        prompt = self.PLAN_GENERATION_PROMPT.format(
            goal=goal,
            tools=tools_description[:2000],
        )

        try:
            role_prompt = self._role_manager.switch_role(AgentRole.PLANNER)

            response = await llm_engine.chat(
                message=prompt,
                system_prompt=role_prompt,
                task_type="parse_order",
                temperature=0.3,
                json_mode=True,
            )

            data = json.loads(response)
            plan = DAGPlan(goal=goal)

            nodes = data.get("nodes", [])
            for node_data in nodes:
                if not isinstance(node_data, dict):
                    continue
                plan.add_node(
                    node_id=node_data.get("id", f"step_{len(plan.nodes)+1}"),
                    description=node_data.get("description", ""),
                    depends_on=node_data.get("depends_on", []),
                    priority=int(node_data.get("priority", 5)),
                    tool_name=node_data.get("tool"),
                )

            # Проверка на циклы
            if plan.has_cycle():
                logger.warning(
                    "DAG plan has cycle — removing problematic deps")
                # Fallback: убираем все зависимости
                for node in plan.nodes.values():
                    node.depends_on = []

            return plan

        except Exception as e:
            logger.warning(f"Plan generation error: {e}")
            # Fallback: один шаг
            plan = DAGPlan(goal=goal)
            plan.add_node("step_1", goal, priority=5)
            return plan

    # ─── Self-Correction ─────────────────────────────────────────────────

    async def self_correct_plan(
        self,
        plan: DAGPlan,
        failed_node_id: str,
        error: str,
        llm_engine=None,
    ) -> DAGPlan:
        """
        Multi-step self-correction: пересмотреть план после неудачи.

        Агент анализирует ошибку и предлагает альтернативный путь.
        """
        if not llm_engine:
            from pds_ultimate.core.llm_engine import llm_engine as _engine
            llm_engine = _engine

        failed_node = plan.nodes.get(failed_node_id)
        if not failed_node:
            return plan

        prompt = self.SELF_CORRECTION_PROMPT.format(
            goal=plan.goal,
            failed_step=f"{failed_node.id}: {failed_node.description}",
            error=error[:500],
            current_plan=json.dumps(plan.to_dict(), ensure_ascii=False)[:2000],
        )

        try:
            role_prompt = self._role_manager.switch_role(AgentRole.STRATEGIST)

            response = await llm_engine.chat(
                message=prompt,
                system_prompt=role_prompt,
                task_type="parse_order",
                temperature=0.3,
                json_mode=True,
            )

            data = json.loads(response)
            plan._revision_count += 1

            # Удаляем указанные узлы
            for node_id in data.get("remove_nodes", []):
                plan.remove_node(node_id)

            # Добавляем новые
            for new_node in data.get("new_nodes", []):
                if isinstance(new_node, dict):
                    plan.add_node(
                        node_id=new_node.get("id", f"fix_{len(plan.nodes)+1}"),
                        description=new_node.get("description", ""),
                        depends_on=new_node.get("depends_on", []),
                        priority=int(new_node.get("priority", 8)),
                        tool_name=new_node.get("tool"),
                    )

            logger.info(
                f"Plan self-corrected (rev {plan._revision_count}): "
                f"{data.get('correction', 'unknown correction')[:100]}"
            )
            return plan

        except Exception as e:
            logger.warning(f"Self-correction error: {e}")
            return plan

    # ─── Confidence Assessment ───────────────────────────────────────────

    async def assess_confidence(
        self,
        query: str,
        answer: str,
        context: str = "",
        llm_engine=None,
    ) -> ConfidenceAssessment:
        """
        Оценить уверенность в ответе.

        Если низкая → suggest queries для допоиска.
        """
        if not llm_engine:
            from pds_ultimate.core.llm_engine import llm_engine as _engine
            llm_engine = _engine

        prompt = self.CONFIDENCE_PROMPT.format(
            query=query[:500],
            answer=answer[:1000],
            context=context[:500],
        )

        try:
            response = await llm_engine.chat(
                message=prompt,
                system_prompt=self._role_manager.get_role_prompt(
                    AgentRole.ANALYST),
                task_type="parse_order",
                temperature=0.2,
                json_mode=True,
            )

            data = json.loads(response)
            return ConfidenceAssessment(
                score=float(data.get("score", 0.5)),
                reasoning=data.get("reasoning", ""),
                gaps=data.get("gaps", []),
                should_search_more=data.get("should_search_more", False),
                suggested_queries=data.get("suggested_queries", []),
            )

        except Exception as e:
            logger.warning(f"Confidence assessment error: {e}")
            return ConfidenceAssessment(
                score=0.5,
                reasoning=f"Ошибка оценки: {e}",
                gaps=[],
                should_search_more=False,
                suggested_queries=[],
            )

    # ─── Goal Integrity ──────────────────────────────────────────────────

    async def check_goal_integrity(
        self,
        original_goal: str,
        current_focus: str,
        completed_steps: list[str],
        llm_engine=None,
    ) -> GoalIntegrityCheck:
        """
        Goal Integrity Check: «я всё ещё решаю исходную цель?»

        Каждый N шагов агент проверяет, не отклонился ли от цели.
        """
        if not llm_engine:
            from pds_ultimate.core.llm_engine import llm_engine as _engine
            llm_engine = _engine

        prompt = self.GOAL_INTEGRITY_PROMPT.format(
            original_goal=original_goal[:300],
            current_focus=current_focus[:300],
            completed_steps=json.dumps(
                completed_steps[-10:], ensure_ascii=False)[:500],
        )

        try:
            response = await llm_engine.chat(
                message=prompt,
                system_prompt=self._role_manager.get_role_prompt(
                    AgentRole.VERIFIER),
                task_type="parse_order",
                temperature=0.2,
                json_mode=True,
            )

            data = json.loads(response)
            return GoalIntegrityCheck(
                aligned=data.get("aligned", True),
                original_goal=original_goal,
                current_focus=current_focus,
                drift_reason=data.get("drift_reason"),
                recommendation=data.get("recommendation", "Продолжай"),
            )

        except Exception as e:
            logger.warning(f"Goal integrity check error: {e}")
            return GoalIntegrityCheck(
                aligned=True,
                original_goal=original_goal,
                current_focus=current_focus,
                drift_reason=None,
                recommendation="Продолжай (проверка не удалась)",
            )

    # ─── Self-Query Expansion ────────────────────────────────────────────

    async def expand_query(
        self,
        query: str,
        intermediate_results: str = "",
        gaps: list[str] | None = None,
        llm_engine=None,
    ) -> list[str]:
        """
        Self-Query Expansion: агент уточняет запрос на основе
        промежуточных результатов.

        Не тупо ищет 1 раз → генерирует 2-3 уточнённых запроса.
        """
        if not llm_engine:
            from pds_ultimate.core.llm_engine import llm_engine as _engine
            llm_engine = _engine

        prompt = self.QUERY_EXPANSION_PROMPT.format(
            query=query[:300],
            intermediate=intermediate_results[:1000],
            gaps=json.dumps(gaps or [], ensure_ascii=False),
        )

        try:
            response = await llm_engine.chat(
                message=prompt,
                system_prompt=self._role_manager.get_role_prompt(
                    AgentRole.RESEARCHER),
                task_type="parse_order",
                temperature=0.4,
                json_mode=True,
            )

            data = json.loads(response)
            queries = data.get("expanded_queries", [])
            if queries and isinstance(queries, list):
                return [q for q in queries if isinstance(q, str)][:5]
            return [query]

        except Exception as e:
            logger.warning(f"Query expansion error: {e}")
            return [query]

    # ─── Intermediate Goal Generation ────────────────────────────────────

    async def decompose_goal(
        self,
        goal: str,
        context: str = "",
        llm_engine=None,
    ) -> list[dict[str, Any]]:
        """
        Декомпозиция сложной цели на промежуточные подцели.

        Если цель слишком сложная / долгосрочная → разбить на
        manageable sub-goals.
        """
        if not llm_engine:
            from pds_ultimate.core.llm_engine import llm_engine as _engine
            llm_engine = _engine

        prompt = self.DECOMPOSITION_PROMPT.format(
            goal=goal[:500],
            context=context[:500],
        )

        try:
            response = await llm_engine.chat(
                message=prompt,
                system_prompt=self._role_manager.get_role_prompt(
                    AgentRole.STRATEGIST),
                task_type="parse_order",
                temperature=0.3,
                json_mode=True,
            )

            data = json.loads(response)
            sub_goals = data.get("sub_goals", [])
            if isinstance(sub_goals, list):
                return [
                    sg for sg in sub_goals
                    if isinstance(sg, dict) and "goal" in sg
                ]
            return [{"goal": goal, "priority": 5, "estimated_steps": 1}]

        except Exception as e:
            logger.warning(f"Goal decomposition error: {e}")
            return [{"goal": goal, "priority": 5, "estimated_steps": 1}]

    # ─── Critique (Dynamic Role) ─────────────────────────────────────────

    async def critique_answer(
        self,
        query: str,
        answer: str,
        llm_engine=None,
    ) -> dict:
        """
        Роль Critic: оценить качество ответа.

        Returns:
            {"quality": 0.0-1.0, "issues": [...], "improvements": [...]}
        """
        if not llm_engine:
            from pds_ultimate.core.llm_engine import llm_engine as _engine
            llm_engine = _engine

        prompt = (
            f"ЗАПРОС ПОЛЬЗОВАТЕЛЯ: {query[:500]}\n\n"
            f"ОТВЕТ АГЕНТА: {answer[:1500]}\n\n"
            "Оцени качество этого ответа."
        )

        try:
            role_prompt = self._role_manager.switch_role(AgentRole.CRITIC)

            response = await llm_engine.chat(
                message=prompt,
                system_prompt=role_prompt,
                task_type="parse_order",
                temperature=0.2,
                json_mode=True,
            )

            data = json.loads(response)
            return {
                "quality": float(data.get("quality", 0.5)),
                "issues": data.get("issues", []),
                "improvements": data.get("improvements", []),
                "critical_flaws": data.get("critical_flaws", False),
            }

        except Exception as e:
            logger.warning(f"Critique error: {e}")
            return {
                "quality": 0.5,
                "issues": [f"Не удалось выполнить критику: {e}"],
                "improvements": [],
                "critical_flaws": False,
            }

    # ─── Get Full Cognitive Context ──────────────────────────────────────

    def get_cognitive_context(self, chat_id: int) -> str:
        """
        Получить полный когнитивный контекст для system prompt.

        Включает: план, задачи, метакогницию, роль.
        """
        parts = []

        # Текущий план
        plan = self.get_plan(chat_id)
        if plan and not plan.is_complete:
            parts.append(plan.get_summary())

        # Активные задачи
        active_tasks = self._task_manager.get_active_tasks(chat_id)
        if active_tasks:
            parts.append(self._task_manager.get_summary(chat_id))

        # Метакогнитивное состояние
        mc = self.get_metacog(chat_id)
        if mc.iterations_used > 0:
            mc_lines = [
                "🧠 МЕТАКОГНИЦИЯ:",
                f"  Итераций: {mc.iterations_used}",
                f"  Время: {mc.thinking_time_seconds:.1f}с",
            ]
            if mc.avg_confidence > 0:
                mc_lines.append(
                    f"  Ср. уверенность: {mc.avg_confidence:.0%}")
            if mc.is_stuck:
                mc_lines.append("  ⚠️ ЗАЦИКЛИВАНИЕ ОБНАРУЖЕНО")
            if mc.is_declining:
                mc_lines.append(
                    "  📉 УВЕРЕННОСТЬ СНИЖАЕТСЯ — смени стратегию")
            if mc.low_confidence_streak >= 2:
                mc_lines.append(
                    f"  ⚠️ Низкая уверенность {mc.low_confidence_streak}x подряд")
            if mc.is_taking_too_long:
                mc_lines.append("  ⏰ СЛИШКОМ ДОЛГО — ускорь решение")
            parts.append("\n".join(mc_lines))

        # Текущая роль
        role = self._role_manager.active_role
        if role != AgentRole.EXECUTOR:
            parts.append(f"🎭 АКТИВНАЯ РОЛЬ: {role.value}")

        return "\n\n".join(parts) if parts else ""

    # ─── Stats ───────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Статистика когнитивного движка."""
        return {
            "active_plans": len(self._active_plans),
            "tasks": self._task_manager.stats,
            "active_role": self._role_manager.active_role.value,
            "metacog_sessions": len(self._metacog),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР
# ═══════════════════════════════════════════════════════════════════════════════

cognitive_engine = CognitiveEngine()
