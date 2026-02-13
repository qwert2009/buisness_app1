"""
PDS-Ultimate — Workflow Engine (Part 9)
=========================================
Процессные чек-листы, шаблоны заказов, реюзабельные workflow.

Функциональность:
- Шаблоны заказов (reusable order templates)
- Процессные чек-листы (supply chain, onboarding, etc.)
- Workflow автоматизация (IF → THEN цепочки)
- Template library (библиотека шаблонов)
- Checklist tracking (отслеживание прогресса)
- Workflow execution (выполнение workflow)
- History & audit trail

Архитектура:
    WorkflowEngine
    ├── TemplateLibrary — библиотека шаблонов
    ├── ChecklistManager — чек-листы
    └── WorkflowRunner — выполнение workflow
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════════


class TemplateType(str, Enum):
    """Типы шаблонов."""
    ORDER = "order"
    CHECKLIST = "checklist"
    WORKFLOW = "workflow"
    MESSAGE = "message"
    REPORT = "report"


class ChecklistStatus(str, Enum):
    """Статус чек-листа."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    """Статус шага."""
    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


class WorkflowStatus(str, Enum):
    """Статус workflow."""
    DRAFT = "draft"
    ACTIVE = "active"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class TemplateField:
    """Поле шаблона (переменная)."""
    name: str
    description: str = ""
    field_type: str = "string"      # string, number, date, boolean
    default_value: Any = None
    required: bool = False
    options: list[str] = field(default_factory=list)  # Для select

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "type": self.field_type,
            "default": self.default_value,
            "required": self.required,
            "options": self.options,
        }


@dataclass
class Template:
    """Шаблон."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    description: str = ""
    template_type: TemplateType = TemplateType.ORDER
    content: str = ""               # Текст с {переменными}
    fields: list[TemplateField] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    use_count: int = 0
    owner_id: int = 0

    def render(self, values: dict[str, Any]) -> str:
        """Рендерить шаблон с подставленными значениями."""
        result = self.content
        for f in self.fields:
            placeholder = "{" + f.name + "}"
            value = values.get(f.name, f.default_value or "")
            result = result.replace(placeholder, str(value))
        self.use_count += 1
        return result

    def validate_values(self, values: dict[str, Any]) -> list[str]:
        """Валидировать значения."""
        errors = []
        for f in self.fields:
            if f.required and f.name not in values:
                errors.append(f"Обязательное поле '{f.name}' не заполнено")
            if f.options and f.name in values:
                if str(values[f.name]) not in f.options:
                    errors.append(
                        f"Поле '{f.name}': значение должно быть одним из {f.options}"
                    )
        return errors

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "type": self.template_type.value,
            "fields": [f.to_dict() for f in self.fields],
            "tags": self.tags,
            "use_count": self.use_count,
        }


@dataclass
class ChecklistStep:
    """Шаг чек-листа."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    title: str = ""
    description: str = ""
    status: StepStatus = StepStatus.PENDING
    order: int = 0
    assignee: str = ""
    due_date: datetime | None = None
    completed_at: datetime | None = None
    notes: str = ""
    required: bool = True

    @property
    def is_done(self) -> bool:
        return self.status in (StepStatus.DONE, StepStatus.SKIPPED)

    @property
    def is_overdue(self) -> bool:
        if not self.due_date or self.is_done:
            return False
        return datetime.utcnow() > self.due_date

    def complete(self) -> None:
        """Завершить шаг."""
        self.status = StepStatus.DONE
        self.completed_at = datetime.utcnow()

    def skip(self, reason: str = "") -> None:
        """Пропустить шаг."""
        self.status = StepStatus.SKIPPED
        if reason:
            self.notes = f"Пропущен: {reason}"

    def fail(self, reason: str = "") -> None:
        """Отметить как неудавшийся."""
        self.status = StepStatus.FAILED
        if reason:
            self.notes = f"Ошибка: {reason}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status.value,
            "order": self.order,
            "is_done": self.is_done,
            "is_overdue": self.is_overdue,
            "assignee": self.assignee,
        }


@dataclass
class Checklist:
    """Чек-лист."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    description: str = ""
    status: ChecklistStatus = ChecklistStatus.NOT_STARTED
    steps: list[ChecklistStep] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    template_id: str = ""
    owner_id: int = 0
    tags: list[str] = field(default_factory=list)

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.is_done)

    @property
    def progress(self) -> float:
        if not self.steps:
            return 0.0
        return self.completed_steps / self.total_steps

    @property
    def progress_percent(self) -> float:
        return round(self.progress * 100, 1)

    @property
    def overdue_steps(self) -> list[ChecklistStep]:
        return [s for s in self.steps if s.is_overdue]

    @property
    def next_step(self) -> ChecklistStep | None:
        """Следующий невыполненный шаг."""
        for s in sorted(self.steps, key=lambda s: s.order):
            if not s.is_done:
                return s
        return None

    def complete_step(self, step_id: str) -> bool:
        """Завершить шаг."""
        for s in self.steps:
            if s.id == step_id:
                s.complete()
                self._update_status()
                return True
        return False

    def complete_step_by_order(self, order: int) -> bool:
        """Завершить шаг по порядковому номеру."""
        for s in self.steps:
            if s.order == order:
                s.complete()
                self._update_status()
                return True
        return False

    def _update_status(self) -> None:
        """Обновить статус чек-листа."""
        if all(s.is_done for s in self.steps):
            self.status = ChecklistStatus.COMPLETED
            self.completed_at = datetime.utcnow()
        elif any(s.is_done for s in self.steps):
            self.status = ChecklistStatus.IN_PROGRESS
        else:
            self.status = ChecklistStatus.NOT_STARTED

    def add_step(
        self,
        title: str,
        description: str = "",
        assignee: str = "",
        due_days: int = 0,
        required: bool = True,
    ) -> ChecklistStep:
        """Добавить шаг."""
        step = ChecklistStep(
            title=title,
            description=description,
            order=len(self.steps),
            assignee=assignee,
            required=required,
        )
        if due_days > 0:
            step.due_date = datetime.utcnow() + timedelta(days=due_days)
        self.steps.append(step)
        return step

    def format_text(self) -> str:
        """Текстовое представление."""
        lines = [
            f"📋 {self.name} [{self.progress_percent:.0f}%]",
        ]
        for s in sorted(self.steps, key=lambda s: s.order):
            icon = "✅" if s.status == StepStatus.DONE else (
                "⏭️" if s.status == StepStatus.SKIPPED else (
                    "❌" if s.status == StepStatus.FAILED else "⬜"
                )
            )
            overdue = " ⚠️" if s.is_overdue else ""
            lines.append(f"  {s.order + 1}. {icon} {s.title}{overdue}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "progress": self.progress_percent,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "overdue": len(self.overdue_steps),
            "steps": [s.to_dict() for s in self.steps],
        }


@dataclass
class WorkflowAction:
    """Действие workflow."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    action_type: str = "tool_call"  # tool_call, message, wait, condition
    config: dict = field(default_factory=dict)
    order: int = 0
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.action_type,
            "status": self.status.value,
            "order": self.order,
        }


@dataclass
class Workflow:
    """Workflow (автоматизация)."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    description: str = ""
    status: WorkflowStatus = WorkflowStatus.DRAFT
    actions: list[WorkflowAction] = field(default_factory=list)
    trigger_condition: str = ""     # Условие запуска
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_run: datetime | None = None
    run_count: int = 0
    owner_id: int = 0

    @property
    def total_actions(self) -> int:
        return len(self.actions)

    @property
    def completed_actions(self) -> int:
        return sum(
            1 for a in self.actions
            if a.status == StepStatus.DONE
        )

    @property
    def progress(self) -> float:
        if not self.actions:
            return 0.0
        return self.completed_actions / self.total_actions

    def add_action(
        self,
        name: str,
        action_type: str = "tool_call",
        config: dict | None = None,
    ) -> WorkflowAction:
        """Добавить действие."""
        action = WorkflowAction(
            name=name,
            action_type=action_type,
            config=config or {},
            order=len(self.actions),
        )
        self.actions.append(action)
        return action

    def start(self) -> None:
        """Запустить workflow."""
        self.status = WorkflowStatus.RUNNING
        self.last_run = datetime.utcnow()
        self.run_count += 1

    def complete(self) -> None:
        """Завершить."""
        self.status = WorkflowStatus.COMPLETED

    def fail(self, error: str = "") -> None:
        """Ошибка."""
        self.status = WorkflowStatus.FAILED

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "actions": self.total_actions,
            "completed": self.completed_actions,
            "run_count": self.run_count,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATE LIBRARY
# ═══════════════════════════════════════════════════════════════════════════════


class TemplateLibrary:
    """Библиотека шаблонов."""

    def __init__(self, max_templates: int = 200):
        self._templates: dict[str, Template] = {}
        self._max_templates = max_templates
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Стандартные шаблоны."""
        # Order template
        order_tpl = Template(
            name="Стандартный заказ",
            description="Базовый шаблон заказа товаров",
            template_type=TemplateType.ORDER,
            content=(
                "Заказ: {товар}\n"
                "Количество: {количество} шт\n"
                "Поставщик: {поставщик}\n"
                "Срок: {срок}\n"
                "Бюджет: ${бюджет}"
            ),
            fields=[
                TemplateField("товар", "Название товара",
                              "string", required=True),
                TemplateField("количество", "Количество", "number", "1", True),
                TemplateField("поставщик", "Имя поставщика", "string"),
                TemplateField("срок", "Срок доставки", "string", "7 дней"),
                TemplateField("бюджет", "Бюджет", "number", "0"),
            ],
            tags=["order", "default"],
        )
        self._templates[order_tpl.id] = order_tpl

        # Checklist template
        supply_tpl = Template(
            name="Чек-лист поставки",
            description="Стандартный чек-лист для отслеживания поставки",
            template_type=TemplateType.CHECKLIST,
            content=(
                "1. Подтвердить заказ у поставщика\n"
                "2. Получить трекинг-номер\n"
                "3. Отслеживать доставку\n"
                "4. Принять товар на складе\n"
                "5. Проверить качество\n"
                "6. Обновить учёт"
            ),
            fields=[
                TemplateField("поставщик", "Имя поставщика",
                              "string", required=True),
                TemplateField("заказ", "Номер заказа", "string"),
            ],
            tags=["checklist", "supply", "default"],
        )
        self._templates[supply_tpl.id] = supply_tpl

    def create_template(
        self,
        name: str,
        template_type: TemplateType | str,
        content: str,
        description: str = "",
        fields: list[TemplateField] | None = None,
        tags: list[str] | None = None,
        owner_id: int = 0,
    ) -> Template:
        """Создать шаблон."""
        if len(self._templates) >= self._max_templates:
            raise ValueError(f"Лимит шаблонов ({self._max_templates})")

        if isinstance(template_type, str):
            template_type = TemplateType(template_type.lower())

        template = Template(
            name=name,
            description=description,
            template_type=template_type,
            content=content,
            fields=fields or [],
            tags=tags or [],
            owner_id=owner_id,
        )
        self._templates[template.id] = template
        return template

    def get_template(self, template_id: str) -> Template | None:
        """Получить шаблон."""
        return self._templates.get(template_id)

    def find_by_name(self, name: str) -> Template | None:
        """Найти по имени."""
        for t in self._templates.values():
            if t.name.lower() == name.lower():
                return t
        return None

    def search(
        self,
        query: str = "",
        template_type: TemplateType | None = None,
        tags: list[str] | None = None,
    ) -> list[Template]:
        """Поиск шаблонов."""
        results = list(self._templates.values())

        if query:
            q = query.lower()
            results = [
                t for t in results
                if q in t.name.lower() or q in t.description.lower()
            ]

        if template_type:
            results = [t for t in results if t.template_type == template_type]

        if tags:
            results = [
                t for t in results
                if any(tag in t.tags for tag in tags)
            ]

        return sorted(results, key=lambda t: -t.use_count)

    def delete_template(self, template_id: str) -> bool:
        """Удалить шаблон."""
        if template_id in self._templates:
            del self._templates[template_id]
            return True
        return False

    def render_template(
        self,
        template_id: str,
        values: dict[str, Any],
    ) -> str | None:
        """Рендерить шаблон."""
        template = self._templates.get(template_id)
        if not template:
            return None
        return template.render(values)

    @property
    def count(self) -> int:
        return len(self._templates)

    def get_stats(self) -> dict:
        """Статистика."""
        templates = list(self._templates.values())
        by_type: dict[str, int] = {}
        for t in templates:
            by_type[t.template_type.value] = by_type.get(
                t.template_type.value, 0) + 1
        return {
            "total": len(templates),
            "by_type": by_type,
            "total_uses": sum(t.use_count for t in templates),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# CHECKLIST MANAGER
# ═══════════════════════════════════════════════════════════════════════════════


class ChecklistManager:
    """Менеджер чек-листов."""

    def __init__(self, max_checklists: int = 500):
        self._checklists: dict[str, Checklist] = {}
        self._max_checklists = max_checklists

    def create_checklist(
        self,
        name: str,
        steps: list[str] | None = None,
        description: str = "",
        owner_id: int = 0,
        tags: list[str] | None = None,
    ) -> Checklist:
        """Создать чек-лист."""
        if len(self._checklists) >= self._max_checklists:
            self._cleanup_completed()
            if len(self._checklists) >= self._max_checklists:
                raise ValueError(f"Лимит чек-листов ({self._max_checklists})")

        checklist = Checklist(
            name=name,
            description=description,
            owner_id=owner_id,
            tags=tags or [],
        )

        if steps:
            for i, step_title in enumerate(steps):
                checklist.add_step(
                    title=step_title,
                )

        self._checklists[checklist.id] = checklist
        return checklist

    def create_from_template(
        self,
        template: Template,
        values: dict[str, Any] | None = None,
        owner_id: int = 0,
    ) -> Checklist:
        """Создать чек-лист из шаблона."""
        # Parse steps from template content
        content = template.render(values or {})
        step_lines = [
            line.strip().lstrip("0123456789.-) ")
            for line in content.split("\n")
            if line.strip() and not line.strip().startswith("#")
        ]

        checklist = self.create_checklist(
            name=template.name,
            steps=step_lines,
            description=template.description,
            owner_id=owner_id,
        )
        checklist.template_id = template.id
        return checklist

    def get_checklist(self, checklist_id: str) -> Checklist | None:
        """Получить чек-лист."""
        return self._checklists.get(checklist_id)

    def find_by_name(self, name: str) -> list[Checklist]:
        """Найти по имени."""
        return [
            c for c in self._checklists.values()
            if name.lower() in c.name.lower()
        ]

    def get_active(self) -> list[Checklist]:
        """Активные чек-листы."""
        return [
            c for c in self._checklists.values()
            if c.status in (ChecklistStatus.NOT_STARTED, ChecklistStatus.IN_PROGRESS)
        ]

    def complete_step(
        self,
        checklist_id: str,
        step_order: int,
    ) -> Checklist | None:
        """Завершить шаг чек-листа."""
        checklist = self._checklists.get(checklist_id)
        if checklist:
            checklist.complete_step_by_order(step_order)
        return checklist

    def delete_checklist(self, checklist_id: str) -> bool:
        """Удалить чек-лист."""
        if checklist_id in self._checklists:
            del self._checklists[checklist_id]
            return True
        return False

    def _cleanup_completed(self, keep: int = 100) -> int:
        """Очистить завершённые."""
        completed = sorted(
            [c for c in self._checklists.values()
             if c.status == ChecklistStatus.COMPLETED],
            key=lambda c: c.completed_at or c.created_at,
        )
        to_remove = completed[:-keep] if len(completed) > keep else []
        for c in to_remove:
            del self._checklists[c.id]
        return len(to_remove)

    def get_stats(self) -> dict:
        """Статистика."""
        checklists = list(self._checklists.values())
        by_status: dict[str, int] = {}
        for c in checklists:
            by_status[c.status.value] = by_status.get(c.status.value, 0) + 1
        return {
            "total": len(checklists),
            "by_status": by_status,
            "active": len(self.get_active()),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# WORKFLOW ENGINE
# ═══════════════════════════════════════════════════════════════════════════════


class WorkflowEngine:
    """
    Движок workflow и шаблонов.

    Объединяет шаблоны, чек-листы и автоматизации.
    """

    def __init__(self):
        self.templates = TemplateLibrary()
        self.checklists = ChecklistManager()
        self._workflows: dict[str, Workflow] = {}

    # ── Templates ─────────────────────────────────────────────────────────

    def create_template(
        self,
        name: str,
        template_type: str,
        content: str,
        description: str = "",
        fields: list[dict] | None = None,
        tags: list[str] | None = None,
    ) -> Template:
        """Создать шаблон."""
        template_fields = []
        if fields:
            for f in fields:
                template_fields.append(TemplateField(
                    name=f.get("name", ""),
                    description=f.get("description", ""),
                    field_type=f.get("type", "string"),
                    default_value=f.get("default"),
                    required=f.get("required", False),
                    options=f.get("options", []),
                ))

        return self.templates.create_template(
            name=name,
            template_type=template_type,
            content=content,
            description=description,
            fields=template_fields,
            tags=tags,
        )

    def use_template(
        self,
        template_name: str,
        values: dict[str, Any] | None = None,
    ) -> str | None:
        """Использовать шаблон."""
        template = self.templates.find_by_name(template_name)
        if not template:
            return None
        return template.render(values or {})

    # ── Checklists ────────────────────────────────────────────────────────

    def create_checklist(
        self,
        name: str,
        steps: list[str],
        description: str = "",
    ) -> Checklist:
        """Создать чек-лист."""
        return self.checklists.create_checklist(
            name=name,
            steps=steps,
            description=description,
        )

    def check_step(
        self,
        checklist_name: str,
        step_number: int,
    ) -> Checklist | None:
        """Отметить шаг чек-листа (1-based)."""
        results = self.checklists.find_by_name(checklist_name)
        if not results:
            return None
        checklist = results[0]
        checklist.complete_step_by_order(step_number - 1)  # Convert to 0-based
        return checklist

    # ── Workflows ─────────────────────────────────────────────────────────

    def create_workflow(
        self,
        name: str,
        description: str = "",
        actions: list[dict] | None = None,
        trigger_condition: str = "",
    ) -> Workflow:
        """Создать workflow."""
        workflow = Workflow(
            name=name,
            description=description,
            trigger_condition=trigger_condition,
        )

        if actions:
            for a in actions:
                workflow.add_action(
                    name=a.get("name", ""),
                    action_type=a.get("type", "tool_call"),
                    config=a.get("config", {}),
                )

        workflow.status = WorkflowStatus.ACTIVE
        self._workflows[workflow.id] = workflow
        return workflow

    def get_workflow(self, workflow_id: str) -> Workflow | None:
        """Получить workflow."""
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> list[Workflow]:
        """Список workflow."""
        return list(self._workflows.values())

    # ── Stats ─────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Полная статистика."""
        return {
            "templates": self.templates.get_stats(),
            "checklists": self.checklists.get_stats(),
            "workflows": len(self._workflows),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

workflow_engine = WorkflowEngine()
