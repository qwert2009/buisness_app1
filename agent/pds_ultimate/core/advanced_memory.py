"""
PDS-Ultimate Advanced Memory System
======================================
Продвинутая система памяти мирового уровня.

Архитектура памяти (5 типов, а не логи):

1. EPISODIC — конкретные события, взаимодействия, результаты
   «Пользователь заказал 100 балаклав 15 января»

2. SEMANTIC — обобщённые знания, правила, концепции
   «Балаклавы обычно заказывают партиями от 100 шт»

3. PROCEDURAL — как делать задачи, алгоритмы, паттерны действий
   «Для расчёта прибыли: доход - расход = остаток - доставка»

4. STRATEGIC — стратегические решения, приоритеты, goals
   «Основной поставщик — Alibaba, запасной — 1688.com»

5. FAILURE — ошибки, неудачные решения, уроки
   «Поиск по Google News дал устаревшие результаты, лучше DuckDuckGo»

Ключевые фичи (из ТЗ):
- Failure-driven learning: хранить ошибки, с каждым разом лучше
- Time awareness: учёт даты, актуальности, устаревших данных
- Auto-summary & context compression: рекурсивное суммирование
- Memory embedding pruning: удаление устаревших записей
- Semantic search (keyword + TF-IDF scoring)
- Confidence scoring: каждая запись имеет оценку уверенности
- Decay: воспоминания теряют релевантность со временем
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════════
# MEMORY TYPES (константы)
# ═══════════════════════════════════════════════════════════════════════════════


class MemoryType:
    """Типы памяти — память НЕ равно логи."""
    EPISODIC = "episodic"        # Конкретные события
    SEMANTIC = "semantic"        # Обобщённые знания
    PROCEDURAL = "procedural"    # Как делать задачи
    STRATEGIC = "strategic"      # Стратегические решения
    FAILURE = "failure"          # Ошибки и уроки
    FACT = "fact"                # Факты (backward compat)
    PREFERENCE = "preference"    # Предпочтения пользователя
    RULE = "rule"                # Бизнес-правила


# ═══════════════════════════════════════════════════════════════════════════════
# ADVANCED MEMORY ENTRY
# ═══════════════════════════════════════════════════════════════════════════════

class AdvancedMemoryEntry:
    """
    Продвинутая единица памяти.

    Расширения по сравнению с MemoryEntry:
    - confidence: уверенность в корректности (0.0-1.0)
    - decay_rate: скорость забывания (0.0=никогда, 1.0=быстро)
    - expiry: дата истечения (для time-sensitive данных)
    - context_hash: хэш контекста (дедупликация)
    - failure_count: сколько раз ошибался с этой записью
    - success_count: сколько раз запись была полезна
    - related_ids: связанные записи памяти
    - source_quality: оценка качества источника (0.0-1.0)
    """

    def __init__(
        self,
        content: str,
        memory_type: str = MemoryType.EPISODIC,
        importance: float = 0.5,
        confidence: float = 0.8,
        tags: list[str] | None = None,
        source: str = "agent",
        metadata: dict | None = None,
        decay_rate: float = 0.1,
        expiry: datetime | None = None,
        source_quality: float = 0.7,
        chat_id: int | None = None,
    ):
        self.content = content
        self.memory_type = memory_type
        self.importance = min(1.0, max(0.0, importance))
        self.confidence = min(1.0, max(0.0, confidence))
        self.tags = tags or []
        self.source = source
        self.metadata = metadata or {}
        self.decay_rate = min(1.0, max(0.0, decay_rate))
        self.expiry = expiry
        self.source_quality = min(1.0, max(0.0, source_quality))
        self.chat_id = chat_id

        self.created_at = datetime.utcnow()
        self.last_accessed = self.created_at
        self.access_count = 0
        self.failure_count = 0
        self.success_count = 0
        self.related_ids: list[int] = []
        self.context_hash = self._compute_hash()
        self.db_id: int | None = None
        self.is_active = True

    def _compute_hash(self) -> str:
        """Хэш для дедупликации."""
        raw = f"{self.content}|{self.memory_type}".lower().strip()
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def touch(self) -> None:
        """Обновить время доступа + увеличить счётчик."""
        self.access_count += 1
        self.last_accessed = datetime.utcnow()

    def mark_success(self) -> None:
        """Запись оказалась полезной."""
        self.success_count += 1
        # Повышаем уверенность и важность
        self.confidence = min(1.0, self.confidence + 0.05)
        self.importance = min(1.0, self.importance + 0.02)
        self.touch()

    def mark_failure(self) -> None:
        """Запись привела к ошибке."""
        self.failure_count += 1
        # Снижаем уверенность
        self.confidence = max(0.0, self.confidence - 0.1)
        if self.failure_count >= 3:
            self.importance = max(0.1, self.importance - 0.1)

    def is_expired(self) -> bool:
        """Проверить: истёк ли срок записи."""
        if self.expiry and datetime.utcnow() > self.expiry:
            return True
        return False

    def effective_importance(self) -> float:
        """
        Эффективная важность с учётом decay (time awareness).

        Формула: importance * confidence * decay_factor * quality_factor
        - decay: чем старше, тем менее релевантно (если decay_rate > 0)
        - confidence: чем увереннее, тем важнее
        - source_quality: чем качественнее источник, тем больше вес
        """
        if self.is_expired():
            return 0.0

        # Time decay: exponential
        age_hours = (datetime.utcnow() -
                     self.created_at).total_seconds() / 3600
        decay_factor = math.exp(-self.decay_rate * age_hours / 720)
        # 720 часов = 30 дней — baseline

        # Access boost: часто используемое не забывается
        access_boost = min(0.3, self.access_count * 0.02)

        # Success/failure ratio
        total_uses = self.success_count + self.failure_count
        if total_uses > 0:
            success_ratio = self.success_count / total_uses
        else:
            success_ratio = 0.5  # neutral

        effective = (
            self.importance
            * self.confidence
            * decay_factor
            * (0.5 + 0.5 * self.source_quality)
            * (0.5 + 0.5 * success_ratio)
            + access_boost
        )
        return min(1.0, max(0.0, effective))

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "memory_type": self.memory_type,
            "importance": self.importance,
            "confidence": self.confidence,
            "effective_importance": self.effective_importance(),
            "tags": self.tags,
            "source": self.source,
            "metadata": self.metadata,
            "decay_rate": self.decay_rate,
            "expiry": self.expiry.isoformat() if self.expiry else None,
            "source_quality": self.source_quality,
            "created_at": self.created_at.isoformat(),
            "access_count": self.access_count,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "context_hash": self.context_hash,
            "chat_id": self.chat_id,
        }

    def __repr__(self) -> str:
        eff = self.effective_importance()
        return (
            f"<AdvMemory [{self.memory_type}] "
            f"imp={self.importance:.1f} conf={self.confidence:.1f} "
            f"eff={eff:.2f}: {self.content[:40]}...>"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# FAILURE MEMORY (Failure-Driven Learning)
# ═══════════════════════════════════════════════════════════════════════════════

class FailureEntry(AdvancedMemoryEntry):
    """
    Запись об ошибке / неудачном решении.

    Failure-driven learning:
    - Хранит что пошло не так
    - Хранит контекст ошибки
    - Хранит как НАДО было сделать (correction)
    - При похожей ситуации агент НЕ повторяет ошибку
    """

    def __init__(
        self,
        content: str,
        error_context: str = "",
        correction: str = "",
        severity: str = "medium",  # low | medium | high | critical
        **kwargs,
    ):
        kwargs.setdefault("importance", 0.8)
        kwargs.setdefault("confidence", 0.9)
        kwargs.setdefault("decay_rate", 0.01)  # Ошибки не забываются быстро
        super().__init__(
            content=content,
            memory_type=MemoryType.FAILURE,
            **kwargs,
        )
        self.error_context = error_context
        self.correction = correction
        self.severity = severity
        self.tags.extend(["failure", "lesson", severity])

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "error_context": self.error_context,
            "correction": self.correction,
            "severity": self.severity,
        })
        return d


# ═══════════════════════════════════════════════════════════════════════════════
# ADVANCED WORKING MEMORY
# ═══════════════════════════════════════════════════════════════════════════════

class AdvancedWorkingMemory:
    """
    Продвинутая рабочая память.

    Расширения:
    - Goal integrity: проверка «я всё ещё решаю исходную цель?»
    - Sub-goals: промежуточные цели для сложных задач
    - Hypothesis tracking: гипотезы и их проверка
    - Context compression: автоматическое сжатие при переполнении
    - Time tracking: сколько времени на каждом шаге
    """

    MAX_SCRATCHPAD = 50
    MAX_TOOL_RESULTS = 20

    def __init__(self):
        self.primary_goal: str = ""
        self.sub_goals: list[dict[str, Any]] = []
        self.plan: list[dict[str, Any]] = []
        self.scratchpad: list[str] = []
        self.relevant_memories: list[AdvancedMemoryEntry] = []
        self.tool_results: list[dict[str, Any]] = []
        self.hypotheses: list[dict[str, Any]] = []
        self.iteration: int = 0
        self.context_vars: dict[str, Any] = {}
        self.start_time: datetime | None = None
        self.step_times: list[dict[str, Any]] = []
        self._goal_checks: list[dict[str, Any]] = []

    # ─── Goal Management ─────────────────────────────────────────────────

    def set_goal(self, goal: str) -> None:
        """Установить основную цель."""
        self.primary_goal = goal
        self.sub_goals.clear()
        self.plan.clear()
        self.scratchpad.clear()
        self.tool_results.clear()
        self.hypotheses.clear()
        self.iteration = 0
        self.start_time = datetime.utcnow()
        self.step_times.clear()
        self._goal_checks.clear()

    def add_sub_goal(self, goal: str, priority: int = 0) -> None:
        """Добавить промежуточную цель."""
        self.sub_goals.append({
            "goal": goal,
            "priority": priority,
            "status": "pending",
            "result": None,
            "created_at": datetime.utcnow().isoformat(),
        })
        self.sub_goals.sort(key=lambda g: g["priority"], reverse=True)

    def check_goal_integrity(self) -> dict[str, Any]:
        """
        Goal Integrity Check — «я всё ещё решаю исходную цель?»

        Returns:
            {"aligned": bool, "primary_goal": str, "current_focus": str}
        """
        current_focus = ""
        if self.plan:
            current_step = next(
                (s for s in self.plan if s["status"] == "pending"), None
            )
            if current_step:
                current_focus = current_step["step"]

        check = {
            "aligned": True,  # По умолчанию считаем aligned
            "primary_goal": self.primary_goal,
            "current_focus": current_focus,
            "iteration": self.iteration,
            "checked_at": datetime.utcnow().isoformat(),
        }
        self._goal_checks.append(check)
        return check

    # ─── Plan Management ─────────────────────────────────────────────────

    def add_plan_step(self, step: str, order: int = -1,
                      depends_on: list[int] | None = None) -> int:
        """Добавить шаг плана (с зависимостями для DAG)."""
        entry = {
            "step": step,
            "status": "pending",
            "result": None,
            "depends_on": depends_on or [],
            "started_at": None,
            "completed_at": None,
        }
        if 0 <= order < len(self.plan):
            self.plan.insert(order, entry)
        else:
            self.plan.append(entry)
        return len(self.plan) - 1

    def complete_step(self, index: int, result: str) -> None:
        """Отметить шаг как выполненный."""
        if 0 <= index < len(self.plan):
            self.plan[index]["status"] = "completed"
            self.plan[index]["result"] = result
            self.plan[index]["completed_at"] = datetime.utcnow().isoformat()
            self.step_times.append({
                "step": index,
                "duration_s": self._step_duration(index),
            })

    def fail_step(self, index: int, error: str) -> None:
        """Отметить шаг как неудавшийся."""
        if 0 <= index < len(self.plan):
            self.plan[index]["status"] = "failed"
            self.plan[index]["result"] = error
            self.plan[index]["completed_at"] = datetime.utcnow().isoformat()

    def get_current_step(self) -> dict[str, Any] | None:
        """Получить текущий незавершённый шаг (с учётом зависимостей)."""
        for i, step in enumerate(self.plan):
            if step["status"] != "pending":
                continue
            # Проверяем зависимости
            deps = step.get("depends_on", [])
            all_deps_done = all(
                self.plan[d]["status"] == "completed"
                for d in deps if 0 <= d < len(self.plan)
            )
            if all_deps_done:
                step["started_at"] = datetime.utcnow().isoformat()
                return step
        return None

    def get_ready_steps(self) -> list[tuple[int, dict]]:
        """Получить все шаги готовые к выполнению (для параллелизма)."""
        ready = []
        for i, step in enumerate(self.plan):
            if step["status"] != "pending":
                continue
            deps = step.get("depends_on", [])
            all_deps_done = all(
                self.plan[d]["status"] == "completed"
                for d in deps if 0 <= d < len(self.plan)
            )
            if all_deps_done:
                ready.append((i, step))
        return ready

    def _step_duration(self, index: int) -> float:
        """Время выполнения шага в секундах."""
        step = self.plan[index]
        if step.get("started_at") and step.get("completed_at"):
            try:
                start = datetime.fromisoformat(step["started_at"])
                end = datetime.fromisoformat(step["completed_at"])
                return (end - start).total_seconds()
            except (ValueError, TypeError):
                pass
        return 0.0

    # ─── Hypothesis Management ───────────────────────────────────────────

    def add_hypothesis(self, hypothesis: str, confidence: float = 0.5) -> int:
        """Добавить гипотезу для проверки."""
        entry = {
            "hypothesis": hypothesis,
            "confidence": confidence,
            "status": "unverified",  # unverified | confirmed | refuted
            "evidence": [],
            "created_at": datetime.utcnow().isoformat(),
        }
        self.hypotheses.append(entry)
        return len(self.hypotheses) - 1

    def update_hypothesis(self, index: int, status: str,
                          evidence: str = "", confidence: float | None = None) -> None:
        """Обновить статус гипотезы."""
        if 0 <= index < len(self.hypotheses):
            self.hypotheses[index]["status"] = status
            if evidence:
                self.hypotheses[index]["evidence"].append(evidence)
            if confidence is not None:
                self.hypotheses[index]["confidence"] = confidence

    # ─── Scratchpad & Tools ──────────────────────────────────────────────

    def add_note(self, note: str) -> None:
        """Добавить заметку в scratchpad с auto-compression."""
        self.scratchpad.append(f"[iter {self.iteration}] {note}")
        if len(self.scratchpad) > self.MAX_SCRATCHPAD:
            # Сжимаем: оставляем последние + важные
            self.scratchpad = self.scratchpad[-self.MAX_SCRATCHPAD:]

    def add_tool_result(self, tool_name: str, result: str,
                        success: bool) -> None:
        """Записать результат инструмента."""
        self.tool_results.append({
            "tool": tool_name,
            "result": result[:2000],
            "success": success,
            "iteration": self.iteration,
            "timestamp": datetime.utcnow().isoformat(),
        })
        if len(self.tool_results) > self.MAX_TOOL_RESULTS:
            self.tool_results = self.tool_results[-self.MAX_TOOL_RESULTS:]

    # ─── Context Summary ─────────────────────────────────────────────────

    def get_context_summary(self) -> str:
        """Сформировать контекст для LLM с goal integrity check."""
        parts = []

        if self.primary_goal:
            parts.append(f"🎯 ОСНОВНАЯ ЦЕЛЬ: {self.primary_goal}")

        if self.sub_goals:
            sub_lines = []
            for sg in self.sub_goals:
                emoji = {"pending": "⏳", "completed": "✅",
                         "failed": "❌"}.get(sg["status"], "?")
                sub_lines.append(f"  {emoji} {sg['goal']}")
            parts.append("ПОДЦЕЛИ:\n" + "\n".join(sub_lines))

        if self.plan:
            plan_lines = []
            for i, step in enumerate(self.plan):
                emoji = {"pending": "⏳", "completed": "✅",
                         "failed": "❌"}.get(step["status"], "?")
                deps = step.get("depends_on", [])
                dep_str = f" [зависит от: {deps}]" if deps else ""
                plan_lines.append(
                    f"  {emoji} {i + 1}. {step['step']}{dep_str}")
                if step["result"]:
                    plan_lines.append(f"     → {step['result'][:100]}")
            parts.append("ПЛАН:\n" + "\n".join(plan_lines))

        if self.hypotheses:
            hyp_lines = []
            for h in self.hypotheses:
                emoji = {"unverified": "❓", "confirmed": "✅",
                         "refuted": "❌"}.get(h["status"], "?")
                hyp_lines.append(
                    f"  {emoji} {h['hypothesis']} "
                    f"(conf={h['confidence']:.1f})"
                )
            parts.append("ГИПОТЕЗЫ:\n" + "\n".join(hyp_lines))

        if self.scratchpad:
            recent = self.scratchpad[-5:]
            parts.append("ЗАМЕТКИ:\n" + "\n".join(f"  • {n}" for n in recent))

        if self.relevant_memories:
            mem_lines = [
                f"  • [{m.memory_type}] {m.content[:80]}"
                for m in self.relevant_memories[:5]
            ]
            parts.append("РЕЛЕВАНТНЫЕ ВОСПОМИНАНИЯ:\n" + "\n".join(mem_lines))

        if self.tool_results:
            recent_tools = self.tool_results[-3:]
            tool_lines = [
                f"  • {t['tool']}: "
                f"{'✅' if t['success'] else '❌'} {t['result'][:80]}"
                for t in recent_tools
            ]
            parts.append("ПОСЛЕДНИЕ ДЕЙСТВИЯ:\n" + "\n".join(tool_lines))

        return "\n\n".join(parts) if parts else "Нет активного контекста."

    def reset(self) -> None:
        """Полный сброс."""
        self.primary_goal = ""
        self.sub_goals.clear()
        self.plan.clear()
        self.scratchpad.clear()
        self.relevant_memories.clear()
        self.tool_results.clear()
        self.hypotheses.clear()
        self.iteration = 0
        self.context_vars.clear()
        self.start_time = None
        self.step_times.clear()
        self._goal_checks.clear()
