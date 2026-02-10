"""
PDS-Ultimate Memory System
=============================
Продвинутая система памяти AI-агента.

Три уровня памяти (вдохновлено MemGPT + Phidata + Cortex):

1. WORKING MEMORY (рабочая) — текущий контекст разговора, временные данные.
   Живёт в RAM, сбрасывается при перезагрузке.

2. EPISODIC MEMORY (эпизодическая) — важные взаимодействия, решения, факты.
   Сохраняется в БД, доступна через семантический поиск.
   Примеры: "босс предпочитает поставщика Х", "курс доставки обычно 10%"

3. SEMANTIC MEMORY (семантическая) — знания, правила, паттерны.
   Извлечённые обобщения из эпизодов.
   Примеры: "при заказах > $5000 нужно предупреждать о рисках"

Ключевые фичи:
- Автоматическое извлечение фактов из диалога (fact extraction)
- Сжатие старой истории в саммари (memory consolidation)
- Контекстный recall: подгрузка релевантных воспоминаний
- Importance scoring: важные факты не забываются
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pds_ultimate.config import logger

# ─── Memory Entry ────────────────────────────────────────────────────────────


class MemoryEntry:
    """
    Единица памяти.

    Attributes:
        content: Содержимое (факт, наблюдение, правило)
        memory_type: episodic | semantic | fact | preference | rule
        importance: 0.0-1.0 (чем выше, тем дольше помнится)
        tags: Теги для быстрого поиска
        source: Откуда получено (user, agent, extraction)
        metadata: Дополнительные данные
    """

    def __init__(
        self,
        content: str,
        memory_type: str = "episodic",
        importance: float = 0.5,
        tags: list[str] | None = None,
        source: str = "agent",
        metadata: dict | None = None,
    ):
        self.content = content
        self.memory_type = memory_type
        self.importance = min(1.0, max(0.0, importance))
        self.tags = tags or []
        self.source = source
        self.metadata = metadata or {}
        self.created_at = datetime.utcnow()
        self.access_count = 0
        self.last_accessed = self.created_at
        self.db_id: int | None = None  # ID в БД

    def touch(self) -> None:
        """Обновить время последнего доступа."""
        self.access_count += 1
        self.last_accessed = datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "memory_type": self.memory_type,
            "importance": self.importance,
            "tags": self.tags,
            "source": self.source,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "access_count": self.access_count,
        }

    def __repr__(self) -> str:
        return f"<Memory [{self.memory_type}] imp={self.importance:.1f}: {self.content[:50]}...>"


# ─── Working Memory ─────────────────────────────────────────────────────────

class WorkingMemory:
    """
    Рабочая память — текущий контекст задачи.

    Хранит:
    - Текущую цель (goal)
    - План действий (plan steps)
    - Промежуточные результаты (scratchpad)
    - Контекстные факты (подгруженные из long-term)
    """

    def __init__(self):
        self.current_goal: str = ""
        self.plan: list[dict[str, Any]] = []  # [{step, status, result}]
        self.scratchpad: list[str] = []  # Заметки агента
        # Подгруженные воспоминания
        self.relevant_memories: list[MemoryEntry] = []
        self.tool_results: list[dict[str, Any]] = []  # Результаты инструментов
        self.iteration: int = 0
        self.context_vars: dict[str, Any] = {}  # Переменные контекста

    def set_goal(self, goal: str) -> None:
        """Установить текущую цель."""
        self.current_goal = goal
        self.plan.clear()
        self.scratchpad.clear()
        self.tool_results.clear()
        self.iteration = 0

    def add_plan_step(self, step: str, order: int = -1) -> None:
        """Добавить шаг плана."""
        entry = {"step": step, "status": "pending", "result": None}
        if order >= 0 and order < len(self.plan):
            self.plan.insert(order, entry)
        else:
            self.plan.append(entry)

    def complete_step(self, index: int, result: str) -> None:
        """Отметить шаг как выполненный."""
        if 0 <= index < len(self.plan):
            self.plan[index]["status"] = "completed"
            self.plan[index]["result"] = result

    def fail_step(self, index: int, error: str) -> None:
        """Отметить шаг как неудавшийся."""
        if 0 <= index < len(self.plan):
            self.plan[index]["status"] = "failed"
            self.plan[index]["result"] = error

    def get_current_step(self) -> dict[str, Any] | None:
        """Получить текущий незавершённый шаг."""
        for step in self.plan:
            if step["status"] == "pending":
                return step
        return None

    def add_note(self, note: str) -> None:
        """Добавить заметку в scratchpad."""
        self.scratchpad.append(f"[iter {self.iteration}] {note}")

    def add_tool_result(self, tool_name: str, result: str, success: bool) -> None:
        """Записать результат вызова инструмента."""
        self.tool_results.append({
            "tool": tool_name,
            "result": result[:2000],  # Ограничение размера
            "success": success,
            "iteration": self.iteration,
        })

    def get_context_summary(self) -> str:
        """Сформировать краткое описание текущего контекста для LLM."""
        parts = []

        if self.current_goal:
            parts.append(f"ТЕКУЩАЯ ЦЕЛЬ: {self.current_goal}")

        if self.plan:
            plan_lines = []
            for i, step in enumerate(self.plan):
                emoji = {"pending": "⏳", "completed": "✅",
                         "failed": "❌"}.get(step["status"], "?")
                plan_lines.append(f"  {emoji} {i + 1}. {step['step']}")
                if step["result"]:
                    plan_lines.append(f"     → {step['result'][:100]}")
            parts.append("ПЛАН:\n" + "\n".join(plan_lines))

        if self.scratchpad:
            recent = self.scratchpad[-5:]  # Последние 5 заметок
            parts.append("ЗАМЕТКИ:\n" + "\n".join(f"  • {n}" for n in recent))

        if self.relevant_memories:
            mem_lines = [
                f"  • {m.content[:100]}" for m in self.relevant_memories[:5]]
            parts.append("РЕЛЕВАНТНЫЕ ФАКТЫ:\n" + "\n".join(mem_lines))

        if self.tool_results:
            recent_tools = self.tool_results[-3:]
            tool_lines = [
                f"  • {t['tool']}: {'✅' if t['success'] else '❌'} {t['result'][:100]}"
                for t in recent_tools
            ]
            parts.append("ПОСЛЕДНИЕ ДЕЙСТВИЯ:\n" + "\n".join(tool_lines))

        return "\n\n".join(parts) if parts else "Нет активного контекста."

    def reset(self) -> None:
        """Полный сброс рабочей памяти."""
        self.current_goal = ""
        self.plan.clear()
        self.scratchpad.clear()
        self.relevant_memories.clear()
        self.tool_results.clear()
        self.iteration = 0
        self.context_vars.clear()


# ─── Memory Manager ─────────────────────────────────────────────────────────

class MemoryManager:
    """
    Менеджер долгосрочной памяти.

    Функции:
    1. Сохранение важных фактов из диалога
    2. Поиск релевантных воспоминаний по контексту
    3. Автоматическое сжатие старой истории
    4. Importance-based retention (важные факты живут дольше)
    """

    # Максимум записей в памяти (по умолчанию)
    MAX_MEMORIES = 1000

    # Промпт для извлечения фактов
    FACT_EXTRACTION_PROMPT = """Проанализируй следующий диалог и извлеки важные факты,
которые стоит запомнить для будущих взаимодействий.

Верни JSON массив:
[
  {{
    "fact": "краткое описание факта",
    "type": "preference|rule|knowledge|contact_info|business_insight",
    "importance": 0.0-1.0,
    "tags": ["тег1", "тег2"]
  }}
]

Извлекай только ДЕЙСТВИТЕЛЬНО важные факты:
- Предпочтения пользователя
- Бизнес-правила и решения
- Информация о контактах
- Паттерны поведения
- Инсайты и выводы

НЕ извлекай тривиальные приветствия или общие вопросы.
Если важных фактов нет — верни пустой массив []."""

    # Промпт для сжатия истории
    CONSOLIDATION_PROMPT = """Сожми следующую историю диалога в краткое саммари,
сохранив ВСЕ важные факты, решения и контекст.

Формат:
САММАРИ: [2-3 предложения о ключевых темах]
ФАКТЫ: [список ключевых фактов через |]
РЕШЕНИЯ: [список принятых решений через |]"""

    def __init__(self):
        self._memories: list[MemoryEntry] = []
        self._working: dict[int, WorkingMemory] = {}  # per chat_id

    def get_working(self, chat_id: int) -> WorkingMemory:
        """Получить или создать рабочую память для чата."""
        if chat_id not in self._working:
            self._working[chat_id] = WorkingMemory()
        return self._working[chat_id]

    def reset_working(self, chat_id: int) -> None:
        """Сбросить рабочую память чата."""
        if chat_id in self._working:
            self._working[chat_id].reset()

    # ─── Сохранение в долгосрочную память ────────────────────────────────

    def store(self, entry: MemoryEntry) -> None:
        """Сохранить запись в долгосрочную память."""
        self._memories.append(entry)
        self._enforce_limits()
        logger.debug(
            f"Memory stored: [{entry.memory_type}] {entry.content[:50]}...")

    def store_fact(
        self,
        content: str,
        importance: float = 0.5,
        tags: list[str] | None = None,
        source: str = "extraction",
    ) -> MemoryEntry:
        """Быстрое сохранение факта."""
        entry = MemoryEntry(
            content=content,
            memory_type="fact",
            importance=importance,
            tags=tags or [],
            source=source,
        )
        self.store(entry)
        return entry

    def store_preference(self, content: str, importance: float = 0.7) -> MemoryEntry:
        """Сохранить предпочтение пользователя."""
        entry = MemoryEntry(
            content=content,
            memory_type="preference",
            importance=importance,
            tags=["preference", "user"],
            source="extraction",
        )
        self.store(entry)
        return entry

    def store_rule(self, content: str, importance: float = 0.8) -> MemoryEntry:
        """Сохранить бизнес-правило."""
        entry = MemoryEntry(
            content=content,
            memory_type="rule",
            importance=importance,
            tags=["rule", "business"],
            source="extraction",
        )
        self.store(entry)
        return entry

    # ─── Поиск в памяти ─────────────────────────────────────────────────

    def recall(
        self,
        query: str,
        limit: int = 5,
        memory_type: str | None = None,
        tags: list[str] | None = None,
        min_importance: float = 0.0,
    ) -> list[MemoryEntry]:
        """
        Найти релевантные воспоминания.

        Простой keyword-based recall (без embeddings, т.к. не нужен
        дополнительный API/модель — работаем с DeepSeek).

        Args:
            query: Поисковый запрос
            limit: Максимум записей
            memory_type: Фильтр по типу
            tags: Фильтр по тегам
            min_importance: Минимальная важность

        Returns:
            Список релевантных MemoryEntry, отсортированных по релевантности
        """
        candidates = self._memories.copy()

        # Фильтры
        if memory_type:
            candidates = [
                m for m in candidates if m.memory_type == memory_type]
        if tags:
            candidates = [m for m in candidates if any(
                t in m.tags for t in tags)]
        if min_importance > 0:
            candidates = [
                m for m in candidates if m.importance >= min_importance]

        # Скоринг по keyword overlap
        query_words = set(query.lower().split())
        scored = []
        for m in candidates:
            content_words = set(m.content.lower().split())
            tag_words = set(t.lower() for t in m.tags)

            # Пересечение слов (простой TF)
            word_overlap = len(query_words & content_words)
            tag_overlap = len(query_words & tag_words)

            # Итоговый скор
            score = (word_overlap * 1.0 + tag_overlap * 2.0) * m.importance
            if score > 0:
                scored.append((score, m))

        # Сортировка по скору (убывание)
        scored.sort(key=lambda x: x[0], reverse=True)

        # Обновляем access
        results = []
        for _, m in scored[:limit]:
            m.touch()
            results.append(m)

        return results

    def recall_all(
        self,
        memory_type: str | None = None,
        min_importance: float = 0.0,
        limit: int = 20,
    ) -> list[MemoryEntry]:
        """Получить все воспоминания (или по типу), отсортированные по важности."""
        candidates = self._memories.copy()
        if memory_type:
            candidates = [
                m for m in candidates if m.memory_type == memory_type]
        if min_importance > 0:
            candidates = [
                m for m in candidates if m.importance >= min_importance]
        candidates.sort(key=lambda m: m.importance, reverse=True)
        return candidates[:limit]

    def get_context_for_prompt(self, query: str, max_entries: int = 7) -> str:
        """
        Получить строку контекста из памяти для добавления в system prompt.

        Подбирает наиболее релевантные факты, правила и предпочтения.
        """
        # Собираем из разных типов
        facts = self.recall(query, limit=3, memory_type="fact")
        preferences = self.recall(query, limit=2, memory_type="preference")
        rules = self.recall(query, limit=2, memory_type="rule")

        all_entries = facts + preferences + rules
        # Убираем дубликаты
        seen = set()
        unique = []
        for e in all_entries:
            if e.content not in seen:
                seen.add(e.content)
                unique.append(e)

        if not unique:
            return ""

        lines = ["ДОЛГОСРОЧНАЯ ПАМЯТЬ (факты, которые я помню):"]
        for e in unique[:max_entries]:
            icon = {
                "fact": "📌",
                "preference": "⭐",
                "rule": "📏",
                "knowledge": "📚",
                "contact_info": "👤",
                "business_insight": "💡",
            }.get(e.memory_type, "•")
            lines.append(f"  {icon} {e.content}")

        return "\n".join(lines)

    # ─── Persist to/from DB ──────────────────────────────────────────────

    def save_to_db(self, db_session) -> int:
        """
        Сохранить все unsaved memories в БД.
        Returns: количество сохранённых записей
        """
        from pds_ultimate.core.database import AgentMemory

        count = 0
        for m in self._memories:
            if m.db_id is not None:
                continue  # Уже в БД

            db_entry = AgentMemory(
                content=m.content,
                memory_type=m.memory_type,
                importance=m.importance,
                tags=json.dumps(m.tags, ensure_ascii=False),
                source=m.source,
                metadata_json=json.dumps(
                    m.metadata, ensure_ascii=False, default=str),
                access_count=m.access_count,
            )
            db_session.add(db_entry)
            db_session.flush()
            m.db_id = db_entry.id
            count += 1

        if count > 0:
            db_session.commit()
            logger.info(f"Сохранено {count} записей памяти в БД")
        return count

    def load_from_db(self, db_session) -> int:
        """
        Загрузить memories из БД.
        Returns: количество загруженных записей
        """
        from pds_ultimate.core.database import AgentMemory

        try:
            db_entries = db_session.query(AgentMemory).filter_by(
                is_active=True
            ).order_by(AgentMemory.importance.desc()).limit(self.MAX_MEMORIES).all()

            count = 0
            existing_ids = {
                m.db_id for m in self._memories if m.db_id is not None}

            for db_entry in db_entries:
                if db_entry.id in existing_ids:
                    continue

                tags = []
                try:
                    tags = json.loads(db_entry.tags) if db_entry.tags else []
                except (json.JSONDecodeError, TypeError):
                    pass

                metadata = {}
                try:
                    metadata = json.loads(
                        db_entry.metadata_json) if db_entry.metadata_json else {}
                except (json.JSONDecodeError, TypeError):
                    pass

                entry = MemoryEntry(
                    content=db_entry.content,
                    memory_type=db_entry.memory_type,
                    importance=db_entry.importance,
                    tags=tags,
                    source=db_entry.source or "db",
                    metadata=metadata,
                )
                entry.db_id = db_entry.id
                entry.access_count = db_entry.access_count or 0
                entry.created_at = db_entry.created_at
                self._memories.append(entry)
                count += 1

            logger.info(f"Загружено {count} записей памяти из БД")
            return count
        except Exception as e:
            logger.warning(f"Не удалось загрузить память из БД: {e}")
            return 0

    # ─── Извлечение фактов из диалога ────────────────────────────────────

    async def extract_and_store_facts(self, dialogue: str, llm_engine=None) -> list[MemoryEntry]:
        """
        Извлечь факты из диалога и сохранить в память.

        Использует LLM для анализа диалога и выделения важных фактов.
        """
        if not llm_engine:
            from pds_ultimate.core.llm_engine import llm_engine as default_engine
            llm_engine = default_engine

        try:
            response = await llm_engine.chat(
                message=f"Диалог:\n{dialogue}",
                system_prompt=self.FACT_EXTRACTION_PROMPT,
                task_type="parse_order",
                temperature=0.2,
                json_mode=True,
            )

            facts_data = json.loads(response)
            if not isinstance(facts_data, list):
                return []

            stored = []
            for fact_data in facts_data:
                if not isinstance(fact_data, dict):
                    continue

                content = fact_data.get("fact", "").strip()
                if not content:
                    continue

                entry = MemoryEntry(
                    content=content,
                    memory_type=fact_data.get("type", "fact"),
                    importance=float(fact_data.get("importance", 0.5)),
                    tags=fact_data.get("tags", []),
                    source="extraction",
                )
                self.store(entry)
                stored.append(entry)

            if stored:
                logger.info(f"Извлечено {len(stored)} фактов из диалога")
            return stored

        except Exception as e:
            logger.warning(f"Ошибка извлечения фактов: {e}")
            return []

    # ─── Сжатие истории ──────────────────────────────────────────────────

    async def consolidate_history(
        self,
        history: list[dict[str, str]],
        llm_engine=None,
    ) -> str:
        """
        Сжать длинную историю в компактное саммари.

        Используется когда история превышает лимит контекста.
        Важные факты извлекаются и сохраняются в long-term memory.
        """
        if not llm_engine:
            from pds_ultimate.core.llm_engine import llm_engine as default_engine
            llm_engine = default_engine

        dialogue = "\n".join(
            f"{msg['role']}: {msg['content']}" for msg in history
        )

        try:
            # Сначала извлекаем факты
            await self.extract_and_store_facts(dialogue, llm_engine)

            # Затем сжимаем
            summary = await llm_engine.chat(
                message=dialogue,
                system_prompt=self.CONSOLIDATION_PROMPT,
                task_type="summarize",
                temperature=0.3,
            )

            return summary
        except Exception as e:
            logger.warning(f"Ошибка сжатия истории: {e}")
            # Fallback: простое обрезание
            return f"[История из {len(history)} сообщений — сжатие не удалось]"

    # ─── Внутренние методы ───────────────────────────────────────────────

    def _enforce_limits(self) -> None:
        """Удалить наименее важные записи если превышен лимит."""
        if len(self._memories) <= self.MAX_MEMORIES:
            return

        # Сортируем по важности (ascending) и удаляем наименее важные
        self._memories.sort(key=lambda m: m.importance)
        excess = len(self._memories) - self.MAX_MEMORIES
        self._memories = self._memories[excess:]

    @property
    def total_count(self) -> int:
        """Общее количество записей в памяти."""
        return len(self._memories)

    def get_stats(self) -> dict:
        """Статистика памяти."""
        type_counts: dict[str, int] = {}
        for m in self._memories:
            type_counts[m.memory_type] = type_counts.get(m.memory_type, 0) + 1

        return {
            "total": len(self._memories),
            "by_type": type_counts,
            "avg_importance": sum(m.importance for m in self._memories) / max(1, len(self._memories)),
            "working_memories": len(self._working),
        }


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

memory_manager = MemoryManager()
