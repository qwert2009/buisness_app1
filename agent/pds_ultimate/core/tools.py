"""
PDS-Ultimate Tool Registry
============================
Формальная система инструментов (tools) для AI-агента.

Паттерн: каждый бизнес-модуль регистрирует свои инструменты.
Агент (ReAct loop) вызывает их через единый интерфейс.

Вдохновлено: OpenAI Function Calling, LangChain Tools,
Phidata (tools + memory + knowledge), KodeAgent (ReAct/CodeAct).

Каждый Tool имеет:
- name: уникальное имя (snake_case)
- description: описание для LLM (что делает, когда использовать)
- parameters: JSON Schema параметров
- execute(): асинхронная функция выполнения
"""

from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

from pds_ultimate.config import logger

# ─── Tool Definition ─────────────────────────────────────────────────────────


@dataclass
class ToolParameter:
    """Параметр инструмента."""
    name: str
    param_type: str  # "string", "number", "boolean", "array", "object"
    description: str
    required: bool = True
    default: Any = None
    enum: list[str] | None = None


@dataclass
class Tool:
    """
    Инструмент агента.

    Пример:
        Tool(
            name="create_order",
            description="Создать новый заказ с позициями товаров",
            parameters=[
                ToolParameter("items_text", "string", "Текст с позициями"),
            ],
            handler=order_manager.create_from_text,
            category="logistics",
        )
    """
    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)
    handler: Optional[Callable[..., Coroutine]] = None
    category: str = "general"
    # Отображать ли в system prompt (false для внутренних tools)
    visible: bool = True
    # Требуется ли db_session для вызова
    needs_db: bool = False

    def to_json_schema(self) -> dict:
        """Конвертировать в JSON Schema для LLM (OpenAI Function Calling format)."""
        properties = {}
        required = []

        for p in self.parameters:
            prop: dict[str, Any] = {
                "type": p.param_type,
                "description": p.description,
            }
            if p.enum:
                prop["enum"] = p.enum
            if p.default is not None:
                prop["default"] = p.default

            properties[p.name] = prop
            if p.required:
                required.append(p.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


# ─── Tool Result ─────────────────────────────────────────────────────────────

@dataclass
class ToolResult:
    """Результат выполнения инструмента."""
    tool_name: str
    success: bool
    output: str
    data: Any = None  # Структурированные данные (для chaining)
    error: str | None = None

    def __str__(self) -> str:
        if self.success:
            return self.output
        return f"ОШИБКА [{self.tool_name}]: {self.error}"


# ─── Tool Registry ──────────────────────────────────────────────────────────

class ToolRegistry:
    """
    Реестр всех инструментов системы.

    Паттерн: Singleton-подобный глобальный реестр.
    Модули регистрируют свои tools при инициализации.
    Агент получает полный список для system prompt.
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._categories: dict[str, list[str]] = {}

    def register(self, tool: Tool) -> None:
        """Зарегистрировать инструмент."""
        if tool.name in self._tools:
            logger.warning(
                f"Tool '{tool.name}' уже зарегистрирован — перезаписываю")
        self._tools[tool.name] = tool

        # Категория
        if tool.category not in self._categories:
            self._categories[tool.category] = []
        if tool.name not in self._categories[tool.category]:
            self._categories[tool.category].append(tool.name)

        logger.debug(f"Tool зарегистрирован: {tool.name} [{tool.category}]")

    def unregister(self, name: str) -> None:
        """Удалить инструмент."""
        if name in self._tools:
            tool = self._tools.pop(name)
            if tool.category in self._categories:
                self._categories[tool.category] = [
                    n for n in self._categories[tool.category] if n != name
                ]

    def get(self, name: str) -> Tool | None:
        """Получить инструмент по имени."""
        return self._tools.get(name)

    def list_tools(self, category: str | None = None, visible_only: bool = True) -> list[Tool]:
        """Список инструментов."""
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        if visible_only:
            tools = [t for t in tools if t.visible]
        return tools

    def list_names(self) -> list[str]:
        """Список имён всех видимых инструментов."""
        return [t.name for t in self._tools.values() if t.visible]

    @property
    def categories(self) -> list[str]:
        """Список категорий."""
        return list(self._categories.keys())

    @property
    def count(self) -> int:
        """Количество зарегистрированных инструментов."""
        return len(self._tools)

    async def execute(self, name: str, params: dict | None = None, db_session=None) -> ToolResult:
        """
        Выполнить инструмент.

        Args:
            name: Имя инструмента
            params: Параметры вызова
            db_session: SQLAlchemy session (если нужен)

        Returns:
            ToolResult с результатом или ошибкой
        """
        tool = self.get(name)
        if not tool:
            return ToolResult(
                tool_name=name,
                success=False,
                output="",
                error=f"Инструмент '{name}' не найден. Доступные: {', '.join(self.list_names())}",
            )

        if not tool.handler:
            return ToolResult(
                tool_name=name,
                success=False,
                output="",
                error=f"Инструмент '{name}' не имеет обработчика",
            )

        params = params or {}

        try:
            # Добавляем db_session если нужен
            if tool.needs_db and db_session:
                params["db_session"] = db_session

            result = await tool.handler(**params)

            # Нормализуем результат
            if isinstance(result, ToolResult):
                return result
            elif isinstance(result, dict):
                return ToolResult(
                    tool_name=name,
                    success=True,
                    output=json.dumps(result, ensure_ascii=False, default=str),
                    data=result,
                )
            elif isinstance(result, (list, tuple)):
                return ToolResult(
                    tool_name=name,
                    success=True,
                    output=json.dumps(result, ensure_ascii=False, default=str),
                    data=result,
                )
            else:
                return ToolResult(
                    tool_name=name,
                    success=True,
                    output=str(
                        result) if result is not None else "Выполнено успешно.",
                    data=result,
                )

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.error(
                f"Tool '{name}' ошибка: {error_msg}\n{traceback.format_exc()}")
            return ToolResult(
                tool_name=name,
                success=False,
                output="",
                error=error_msg,
            )

    def get_tools_prompt(self) -> str:
        """
        Сгенерировать описание всех инструментов для system prompt.

        Формат: каждый tool с описанием и параметрами.
        Используется в ReAct loop для LLM.
        """
        lines = []
        for category in sorted(self._categories.keys()):
            tool_names = self._categories[category]
            tools = [self._tools[n]
                     for n in tool_names if n in self._tools and self._tools[n].visible]
            if not tools:
                continue

            lines.append(f"\n### {category.upper()}")
            for tool in tools:
                params_desc = ""
                if tool.parameters:
                    param_parts = []
                    for p in tool.parameters:
                        req = " (обязательный)" if p.required else " (опционально)"
                        param_parts.append(
                            f"    - {p.name} ({p.param_type}){req}: {p.description}")
                    params_desc = "\n" + "\n".join(param_parts)

                lines.append(
                    f"- **{tool.name}**: {tool.description}{params_desc}")

        return "\n".join(lines)

    def get_tools_json_schema(self) -> list[dict]:
        """Получить JSON Schema всех видимых инструментов."""
        return [t.to_json_schema() for t in self._tools.values() if t.visible]


# ─── Глобальный реестр ────────────────────────────────────────────────────────

tool_registry = ToolRegistry()


# ─── Декоратор для регистрации tools ─────────────────────────────────────────

def register_tool(
    name: str,
    description: str,
    category: str = "general",
    parameters: list[ToolParameter] | None = None,
    needs_db: bool = False,
    visible: bool = True,
):
    """
    Декоратор для регистрации функции как инструмента.

    Использование:
        @register_tool(
            name="get_balance",
            description="Получить текущий баланс",
            category="finance",
        )
        async def get_balance():
            return {"balance": 1000}
    """
    def decorator(func):
        tool = Tool(
            name=name,
            description=description,
            parameters=parameters or [],
            handler=func,
            category=category,
            needs_db=needs_db,
            visible=visible,
        )
        tool_registry.register(tool)
        return func
    return decorator
