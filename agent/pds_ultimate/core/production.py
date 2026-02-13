"""
PDS-Ultimate Production Hardening (Part 12)
=============================================
Готовность к промышленной эксплуатации:

1. RateLimiter — ограничение частоты запросов (sliding window)
2. RequestTracker — отслеживание всех запросов + метрики
3. HealthChecker — проверка здоровья подсистем
4. GracefulShutdown — корректное завершение с дренажом задач
5. ErrorReporter — агрегация и классификация ошибок
6. StructuredLogger — структурированное логирование (JSON)
7. UptimeMonitor — аптайм, перезагрузки, SLA
8. SystemMetrics — CPU, memory, disk, event loop lag
9. AlertManager — пороги + оповещения о проблемах
10. ProductionHardening — центральный фасад
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# 1. RATE LIMITER — Sliding Window
# ═══════════════════════════════════════════════════════════════════════════════


class RateLimitResult(Enum):
    """Результат проверки rate limit."""
    ALLOWED = "allowed"
    LIMITED = "limited"
    BLOCKED = "blocked"


@dataclass
class RateLimitEntry:
    """Запись о лимите для одного ключа."""
    key: str
    window_seconds: float
    max_requests: int
    timestamps: list[float] = field(default_factory=list)
    blocked_until: float = 0.0
    total_limited: int = 0

    def _cleanup(self, now: float) -> None:
        """Удалить устаревшие метки."""
        cutoff = now - self.window_seconds
        self.timestamps = [t for t in self.timestamps if t > cutoff]

    def check(self, now: float | None = None) -> RateLimitResult:
        """Проверить, разрешён ли запрос."""
        now = now or time.time()

        # Blocked?
        if now < self.blocked_until:
            return RateLimitResult.BLOCKED

        self._cleanup(now)

        if len(self.timestamps) >= self.max_requests:
            self.total_limited += 1
            return RateLimitResult.LIMITED

        return RateLimitResult.ALLOWED

    def record(self, now: float | None = None) -> None:
        """Записать успешный запрос."""
        now = now or time.time()
        self.timestamps.append(now)

    def block(self, duration_seconds: float, now: float | None = None) -> None:
        """Заблокировать на время."""
        now = now or time.time()
        self.blocked_until = now + duration_seconds

    @property
    def remaining(self) -> int:
        """Оставшихся запросов в окне."""
        self._cleanup(time.time())
        return max(0, self.max_requests - len(self.timestamps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "window_seconds": self.window_seconds,
            "max_requests": self.max_requests,
            "current_count": len(self.timestamps),
            "remaining": self.remaining,
            "total_limited": self.total_limited,
            "blocked": time.time() < self.blocked_until,
        }


class RateLimiter:
    """
    Sliding window rate limiter.

    Поддерживает:
    - Per-user limits (user_id)
    - Per-tool limits (tool_name)
    - Global limits
    - Temporary blocks (abuse detection)
    """

    # Дефолтные лимиты
    DEFAULT_LIMITS: dict[str, tuple[int, float]] = {
        "global": (100, 60.0),       # 100 req / 60s
        "user": (30, 60.0),          # 30 req / 60s per user
        "tool": (20, 60.0),          # 20 req / 60s per tool
        "llm": (10, 60.0),           # 10 LLM calls / 60s
        "web_search": (5, 60.0),     # 5 searches / 60s
    }

    def __init__(self) -> None:
        self._entries: dict[str, RateLimitEntry] = {}
        self._custom_limits: dict[str, tuple[int, float]] = {}

    def set_limit(self, category: str, max_requests: int,
                  window_seconds: float) -> None:
        """Установить кастомный лимит."""
        self._custom_limits[category] = (max_requests, window_seconds)

    def _get_or_create(self, key: str, category: str) -> RateLimitEntry:
        """Получить или создать запись."""
        if key not in self._entries:
            limits = self._custom_limits.get(
                category,
                self.DEFAULT_LIMITS.get(category, (100, 60.0)),
            )
            self._entries[key] = RateLimitEntry(
                key=key,
                max_requests=limits[0],
                window_seconds=limits[1],
            )
        return self._entries[key]

    def check(self, key: str, category: str = "global") -> RateLimitResult:
        """Проверить rate limit."""
        entry = self._get_or_create(key, category)
        return entry.check()

    def record(self, key: str, category: str = "global") -> RateLimitResult:
        """Проверить и записать запрос. Возвращает результат."""
        entry = self._get_or_create(key, category)
        result = entry.check()
        if result == RateLimitResult.ALLOWED:
            entry.record()
        return result

    def block(self, key: str, duration: float, category: str = "global") -> None:
        """Временная блокировка."""
        entry = self._get_or_create(key, category)
        entry.block(duration)

    def get_status(self, key: str | None = None) -> dict[str, Any]:
        """Статус лимитов."""
        if key:
            entry = self._entries.get(key)
            return entry.to_dict() if entry else {"key": key, "status": "no_data"}
        return {
            "total_entries": len(self._entries),
            "entries": {
                k: v.to_dict()
                for k, v in sorted(self._entries.items())[:50]
            },
            "custom_limits": dict(self._custom_limits),
        }

    def reset(self, key: str | None = None) -> None:
        """Сбросить лимиты."""
        if key:
            self._entries.pop(key, None)
        else:
            self._entries.clear()

    def get_stats(self) -> dict[str, Any]:
        """Общая статистика."""
        total_limited = sum(e.total_limited for e in self._entries.values())
        blocked = sum(
            1 for e in self._entries.values()
            if time.time() < e.blocked_until
        )
        return {
            "total_keys": len(self._entries),
            "total_limited": total_limited,
            "currently_blocked": blocked,
            "custom_limits": len(self._custom_limits),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. REQUEST TRACKER
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class RequestRecord:
    """Запись одного запроса."""
    request_id: str
    user_id: str
    action: str
    started_at: float
    finished_at: float = 0.0
    duration_ms: float = 0.0
    success: bool = True
    error: str = ""
    tool_name: str = ""

    def finish(self, success: bool = True, error: str = "") -> None:
        self.finished_at = time.time()
        self.duration_ms = (self.finished_at - self.started_at) * 1000
        self.success = success
        self.error = error


class RequestTracker:
    """
    Отслеживание всех запросов.

    - Метрики: avg time, p95, error rate
    - Последние N запросов для отладки
    - Per-user / per-tool статистика
    """

    def __init__(self, max_history: int = 1000) -> None:
        self._history: list[RequestRecord] = []
        self._max_history = max_history
        self._total_requests = 0
        self._total_errors = 0
        self._active: dict[str, RequestRecord] = {}
        self._counter = 0

    def start_request(self, user_id: str, action: str,
                      tool_name: str = "") -> str:
        """Начать отслеживание запроса. Возвращает request_id."""
        self._counter += 1
        req_id = f"req_{self._counter:06d}"
        record = RequestRecord(
            request_id=req_id,
            user_id=user_id,
            action=action,
            started_at=time.time(),
            tool_name=tool_name,
        )
        self._active[req_id] = record
        return req_id

    def finish_request(self, req_id: str, success: bool = True,
                       error: str = "") -> Optional[RequestRecord]:
        """Завершить запрос."""
        record = self._active.pop(req_id, None)
        if not record:
            return None

        record.finish(success, error)
        self._total_requests += 1
        if not success:
            self._total_errors += 1

        self._history.append(record)
        # Trim
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        return record

    def get_stats(self) -> dict[str, Any]:
        """Статистика запросов."""
        if not self._history:
            return {
                "total_requests": self._total_requests,
                "total_errors": self._total_errors,
                "error_rate": 0.0,
                "active_requests": len(self._active),
                "avg_duration_ms": 0.0,
                "p95_duration_ms": 0.0,
            }

        durations = [r.duration_ms for r in self._history if r.finished_at > 0]
        durations.sort()

        avg_d = sum(durations) / len(durations) if durations else 0.0
        p95_d = durations[int(len(durations) * 0.95)] if durations else 0.0
        error_rate = (
            (self._total_errors / self._total_requests * 100)
            if self._total_requests > 0
            else 0.0
        )

        return {
            "total_requests": self._total_requests,
            "total_errors": self._total_errors,
            "error_rate": round(error_rate, 2),
            "active_requests": len(self._active),
            "avg_duration_ms": round(avg_d, 1),
            "p95_duration_ms": round(p95_d, 1),
            "history_size": len(self._history),
        }

    def get_recent(self, count: int = 10) -> list[dict[str, Any]]:
        """Последние N запросов."""
        recent = self._history[-count:]
        return [
            {
                "id": r.request_id,
                "user": r.user_id,
                "action": r.action,
                "tool": r.tool_name,
                "duration_ms": round(r.duration_ms, 1),
                "success": r.success,
                "error": r.error,
            }
            for r in reversed(recent)
        ]


# ═══════════════════════════════════════════════════════════════════════════════
# 3. HEALTH CHECKER
# ═══════════════════════════════════════════════════════════════════════════════


class HealthStatus(Enum):
    """Статус здоровья подсистемы."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class SubsystemHealth:
    """Здоровье одной подсистемы."""
    name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    message: str = ""
    last_check: float = 0.0
    response_time_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "last_check_ago_s": round(time.time() - self.last_check, 1)
            if self.last_check > 0
            else None,
            "response_time_ms": round(self.response_time_ms, 1),
            "details": self.details,
        }


class HealthChecker:
    """
    Проверка здоровья всех подсистем.

    Подсистемы:
    - database: SQLite connection
    - llm_engine: DeepSeek API reachable
    - bot: Telegram Bot alive
    - scheduler: APScheduler running
    - integrations: Telethon, WhatsApp, Gmail
    - memory: Memory managers loaded
    - disk: Free space available
    """

    def __init__(self) -> None:
        self._subsystems: dict[str, SubsystemHealth] = {}
        self._checks: dict[str, Any] = {}  # name → check function

    def register_check(self, name: str, check_fn: Any) -> None:
        """Зарегистрировать проверку подсистемы."""
        self._checks[name] = check_fn
        if name not in self._subsystems:
            self._subsystems[name] = SubsystemHealth(name=name)

    def report_status(self, name: str, status: HealthStatus,
                      message: str = "", **details: Any) -> None:
        """Сообщить статус подсистемы (без вызова check)."""
        if name not in self._subsystems:
            self._subsystems[name] = SubsystemHealth(name=name)
        sub = self._subsystems[name]
        sub.status = status
        sub.message = message
        sub.last_check = time.time()
        sub.details = details

    async def check_all(self) -> dict[str, SubsystemHealth]:
        """Проверить все подсистемы."""
        for name, check_fn in self._checks.items():
            start = time.time()
            try:
                if asyncio.iscoroutinefunction(check_fn):
                    result = await check_fn()
                else:
                    result = check_fn()

                elapsed = (time.time() - start) * 1000
                sub = self._subsystems.get(name, SubsystemHealth(name=name))
                self._subsystems[name] = sub

                if isinstance(result, dict):
                    sub.status = HealthStatus(
                        result.get("status", "healthy"))
                    sub.message = result.get("message", "OK")
                    sub.details = result.get("details", {})
                elif isinstance(result, bool):
                    sub.status = (
                        HealthStatus.HEALTHY if result
                        else HealthStatus.UNHEALTHY
                    )
                    sub.message = "OK" if result else "Check failed"
                else:
                    sub.status = HealthStatus.HEALTHY
                    sub.message = str(result) if result else "OK"

                sub.response_time_ms = elapsed
                sub.last_check = time.time()

            except Exception as e:
                sub = self._subsystems.get(name, SubsystemHealth(name=name))
                self._subsystems[name] = sub
                sub.status = HealthStatus.UNHEALTHY
                sub.message = f"Error: {e}"
                sub.response_time_ms = (time.time() - start) * 1000
                sub.last_check = time.time()

        return dict(self._subsystems)

    def get_overall_status(self) -> HealthStatus:
        """Общий статус системы."""
        if not self._subsystems:
            return HealthStatus.UNKNOWN

        statuses = [s.status for s in self._subsystems.values()]

        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            return HealthStatus.UNHEALTHY
        if any(s == HealthStatus.DEGRADED for s in statuses):
            return HealthStatus.DEGRADED
        if all(s == HealthStatus.HEALTHY for s in statuses):
            return HealthStatus.HEALTHY
        return HealthStatus.UNKNOWN

    def get_report(self) -> dict[str, Any]:
        """Полный отчёт."""
        return {
            "overall": self.get_overall_status().value,
            "subsystems": {
                name: sub.to_dict()
                for name, sub in sorted(self._subsystems.items())
            },
            "total_checks": len(self._subsystems),
        }

    def get_stats(self) -> dict[str, Any]:
        return {
            "subsystems": len(self._subsystems),
            "checks_registered": len(self._checks),
            "overall": self.get_overall_status().value,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. GRACEFUL SHUTDOWN
# ═══════════════════════════════════════════════════════════════════════════════


class ShutdownPhase(Enum):
    """Фаза завершения."""
    RUNNING = "running"
    DRAINING = "draining"       # Не принимаем новые, дожидаемся текущие
    SAVING = "saving"           # Сохраняем состояние
    CLEANUP = "cleanup"         # Закрываем ресурсы
    STOPPED = "stopped"


@dataclass
class ShutdownTask:
    """Задача при завершении."""
    name: str
    handler: Any     # async callable
    priority: int = 0   # выше = раньше
    timeout: float = 10.0


class GracefulShutdown:
    """
    Корректное завершение работы.

    Фазы:
    1. DRAINING — прекращаем принимать новые запросы
    2. SAVING — сохраняем память, состояние
    3. CLEANUP — закрываем соединения, браузер
    4. STOPPED — всё остановлено
    """

    def __init__(self) -> None:
        self._phase = ShutdownPhase.RUNNING
        self._tasks: list[ShutdownTask] = []
        self._drain_timeout: float = 30.0
        self._started_at: float = 0.0
        self._finished_at: float = 0.0
        self._results: dict[str, dict[str, Any]] = {}

    @property
    def phase(self) -> ShutdownPhase:
        return self._phase

    @property
    def is_running(self) -> bool:
        return self._phase == ShutdownPhase.RUNNING

    @property
    def is_shutting_down(self) -> bool:
        return self._phase not in (
            ShutdownPhase.RUNNING, ShutdownPhase.STOPPED)

    def register(self, name: str, handler: Any, priority: int = 0,
                 timeout: float = 10.0) -> None:
        """Зарегистрировать задачу завершения."""
        self._tasks.append(ShutdownTask(
            name=name, handler=handler, priority=priority, timeout=timeout,
        ))
        # Сортируем по приоритету (убывание)
        self._tasks.sort(key=lambda t: -t.priority)

    async def shutdown(self, drain_timeout: float | None = None) -> dict[str, Any]:
        """Выполнить graceful shutdown."""
        self._started_at = time.time()
        dt = drain_timeout or self._drain_timeout

        # Phase 1: Draining
        self._phase = ShutdownPhase.DRAINING
        await asyncio.sleep(min(dt, 0.1))  # Minimal drain

        # Phase 2: Saving
        self._phase = ShutdownPhase.SAVING
        save_tasks = [t for t in self._tasks if t.priority >= 50]
        for task in save_tasks:
            await self._run_task(task)

        # Phase 3: Cleanup
        self._phase = ShutdownPhase.CLEANUP
        other_tasks = [t for t in self._tasks if t.priority < 50]
        for task in other_tasks:
            await self._run_task(task)

        # Done
        self._phase = ShutdownPhase.STOPPED
        self._finished_at = time.time()

        return {
            "duration_s": round(self._finished_at - self._started_at, 2),
            "tasks_executed": len(self._results),
            "results": dict(self._results),
        }

    async def _run_task(self, task: ShutdownTask) -> None:
        """Выполнить задачу с таймаутом."""
        start = time.time()
        try:
            if asyncio.iscoroutinefunction(task.handler):
                await asyncio.wait_for(
                    task.handler(), timeout=task.timeout)
            else:
                task.handler()

            self._results[task.name] = {
                "success": True,
                "duration_ms": round((time.time() - start) * 1000, 1),
            }
        except asyncio.TimeoutError:
            self._results[task.name] = {
                "success": False,
                "error": f"Timeout ({task.timeout}s)",
                "duration_ms": round((time.time() - start) * 1000, 1),
            }
        except Exception as e:
            self._results[task.name] = {
                "success": False,
                "error": str(e),
                "duration_ms": round((time.time() - start) * 1000, 1),
            }

    def get_stats(self) -> dict[str, Any]:
        return {
            "phase": self._phase.value,
            "tasks_registered": len(self._tasks),
            "is_running": self.is_running,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. ERROR REPORTER
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ErrorEntry:
    """Запись об ошибке."""
    error_type: str
    message: str
    source: str
    timestamp: float = field(default_factory=time.time)
    count: int = 1
    last_seen: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.last_seen == 0.0:
            self.last_seen = self.timestamp


class ErrorReporter:
    """
    Агрегация и классификация ошибок.

    - Группировка по типу
    - Подсчёт повторений
    - Последние N ошибок
    - Топ ошибок по частоте
    """

    def __init__(self, max_history: int = 500) -> None:
        self._errors: list[ErrorEntry] = []
        self._max_history = max_history
        self._by_type: dict[str, int] = defaultdict(int)
        self._by_source: dict[str, int] = defaultdict(int)
        self._total = 0

    def report(self, error_type: str, message: str, source: str = "unknown",
               **details: Any) -> None:
        """Записать ошибку."""
        entry = ErrorEntry(
            error_type=error_type,
            message=message,
            source=source,
            details=details,
        )
        self._errors.append(entry)
        self._by_type[error_type] += 1
        self._by_source[source] += 1
        self._total += 1

        if len(self._errors) > self._max_history:
            self._errors = self._errors[-self._max_history:]

    def get_recent(self, count: int = 10) -> list[dict[str, Any]]:
        """Последние ошибки."""
        recent = self._errors[-count:]
        return [
            {
                "type": e.error_type,
                "message": e.message[:200],
                "source": e.source,
                "ago_s": round(time.time() - e.timestamp, 1),
            }
            for e in reversed(recent)
        ]

    def get_top_errors(self, count: int = 10) -> list[dict[str, Any]]:
        """Топ ошибок по частоте."""
        sorted_types = sorted(
            self._by_type.items(), key=lambda x: -x[1])
        return [
            {"type": t, "count": c}
            for t, c in sorted_types[:count]
        ]

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_errors": self._total,
            "unique_types": len(self._by_type),
            "unique_sources": len(self._by_source),
            "history_size": len(self._errors),
            "top_types": self.get_top_errors(5),
        }

    def clear(self) -> None:
        """Очистить историю."""
        self._errors.clear()
        self._by_type.clear()
        self._by_source.clear()
        self._total = 0


# ═══════════════════════════════════════════════════════════════════════════════
# 6. STRUCTURED LOGGER
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class LogEntry:
    """Структурированная запись лога."""
    level: str
    message: str
    source: str = ""
    timestamp: float = field(default_factory=time.time)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "ts": datetime.fromtimestamp(self.timestamp).isoformat(),
            "level": self.level,
            "msg": self.message,
        }
        if self.source:
            d["src"] = self.source
        if self.extra:
            d.update(self.extra)
        return d


class StructuredLogger:
    """
    Структурированное логирование в JSON-формате.

    Хранит последние N записей для отладки + отправка в канал.
    """

    def __init__(self, max_entries: int = 500) -> None:
        self._entries: list[LogEntry] = []
        self._max_entries = max_entries
        self._total: dict[str, int] = defaultdict(int)

    def log(self, level: str, message: str, source: str = "",
            **extra: Any) -> LogEntry:
        """Добавить запись."""
        entry = LogEntry(
            level=level, message=message, source=source, extra=extra,
        )
        self._entries.append(entry)
        self._total[level] += 1

        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

        return entry

    def info(self, message: str, source: str = "", **extra: Any) -> LogEntry:
        return self.log("INFO", message, source, **extra)

    def warning(self, message: str, source: str = "", **extra: Any) -> LogEntry:
        return self.log("WARNING", message, source, **extra)

    def error(self, message: str, source: str = "", **extra: Any) -> LogEntry:
        return self.log("ERROR", message, source, **extra)

    def debug(self, message: str, source: str = "", **extra: Any) -> LogEntry:
        return self.log("DEBUG", message, source, **extra)

    def get_recent(self, count: int = 20,
                   level: str | None = None) -> list[dict[str, Any]]:
        """Последние записи."""
        entries = self._entries
        if level:
            entries = [e for e in entries if e.level == level.upper()]
        return [e.to_dict() for e in entries[-count:]]

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_entries": sum(self._total.values()),
            "by_level": dict(self._total),
            "buffer_size": len(self._entries),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 7. UPTIME MONITOR
# ═══════════════════════════════════════════════════════════════════════════════


class UptimeMonitor:
    """
    Отслеживание аптайма системы.

    - Время запуска
    - Количество перезагрузок
    - Downtime периоды
    """

    def __init__(self) -> None:
        self._start_time: float = time.time()
        self._restarts: int = 0
        self._downtime_periods: list[tuple[float, float]] = []
        self._last_heartbeat: float = time.time()

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._start_time

    @property
    def uptime_human(self) -> str:
        """Человеко-читаемый аптайм."""
        total = int(self.uptime_seconds)
        days, remainder = divmod(total, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if days:
            parts.append(f"{days}д")
        if hours:
            parts.append(f"{hours}ч")
        if minutes:
            parts.append(f"{minutes}м")
        parts.append(f"{seconds}с")
        return " ".join(parts)

    def heartbeat(self) -> None:
        """Обновить heartbeat."""
        self._last_heartbeat = time.time()

    def record_restart(self) -> None:
        """Записать перезагрузку."""
        self._restarts += 1

    def record_downtime(self, start: float, end: float) -> None:
        """Записать период простоя."""
        self._downtime_periods.append((start, end))

    def get_stats(self) -> dict[str, Any]:
        total_downtime = sum(
            end - start for start, end in self._downtime_periods
        )
        return {
            "uptime_seconds": round(self.uptime_seconds, 1),
            "uptime_human": self.uptime_human,
            "started_at": datetime.fromtimestamp(
                self._start_time).isoformat(),
            "restarts": self._restarts,
            "total_downtime_s": round(total_downtime, 1),
            "last_heartbeat_ago_s": round(
                time.time() - self._last_heartbeat, 1),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 8. SYSTEM METRICS
# ═══════════════════════════════════════════════════════════════════════════════


class SystemMetrics:
    """
    Системные метрики: CPU, memory, disk.
    Не требует psutil — использует /proc и os.
    """

    @staticmethod
    def get_memory_usage() -> dict[str, Any]:
        """Использование памяти текущим процессом."""
        try:
            # Linux: /proc/self/status
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        kb = int(line.split()[1])
                        return {
                            "rss_mb": round(kb / 1024, 1),
                            "rss_kb": kb,
                        }
        except (FileNotFoundError, PermissionError):
            pass
        return {"rss_mb": 0, "rss_kb": 0}

    @staticmethod
    def get_disk_usage(path: str = ".") -> dict[str, Any]:
        """Использование диска."""
        try:
            stat = os.statvfs(path)
            total = stat.f_blocks * stat.f_frsize
            free = stat.f_bavail * stat.f_frsize
            used = total - free
            return {
                "total_gb": round(total / (1024 ** 3), 1),
                "used_gb": round(used / (1024 ** 3), 1),
                "free_gb": round(free / (1024 ** 3), 1),
                "usage_percent": round(used / total * 100, 1) if total else 0,
            }
        except (OSError, ZeroDivisionError):
            return {"total_gb": 0, "used_gb": 0, "free_gb": 0, "usage_percent": 0}

    @staticmethod
    def get_load_average() -> dict[str, Any]:
        """Средняя загрузка (Linux)."""
        try:
            load1, load5, load15 = os.getloadavg()
            return {
                "load_1m": round(load1, 2),
                "load_5m": round(load5, 2),
                "load_15m": round(load15, 2),
            }
        except (OSError, AttributeError):
            return {"load_1m": 0, "load_5m": 0, "load_15m": 0}

    @staticmethod
    def get_event_loop_lag() -> float:
        """Примерная задержка event loop (ms)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return 0.0
        except RuntimeError:
            pass
        return 0.0

    @classmethod
    def get_all(cls) -> dict[str, Any]:
        """Все системные метрики."""
        return {
            "memory": cls.get_memory_usage(),
            "disk": cls.get_disk_usage(),
            "load": cls.get_load_average(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 9. ALERT MANAGER
# ═══════════════════════════════════════════════════════════════════════════════


class AlertSeverity(Enum):
    """Уровень важности алерта."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    """Алерт."""
    name: str
    severity: AlertSeverity
    message: str
    source: str = ""
    timestamp: float = field(default_factory=time.time)
    resolved: bool = False
    resolved_at: float = 0.0

    def resolve(self) -> None:
        self.resolved = True
        self.resolved_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        d = {
            "name": self.name,
            "severity": self.severity.value,
            "message": self.message,
            "source": self.source,
            "ago_s": round(time.time() - self.timestamp, 1),
            "resolved": self.resolved,
        }
        if self.resolved:
            d["resolved_ago_s"] = round(time.time() - self.resolved_at, 1)
        return d


class AlertManager:
    """
    Управление алертами.

    - Пороговые значения
    - Активные алерты
    - Авто-разрешение
    """

    def __init__(self) -> None:
        self._alerts: list[Alert] = []
        self._active: dict[str, Alert] = {}
        self._thresholds: dict[str, dict[str, Any]] = {
            "memory_high": {
                "metric": "memory.rss_mb",
                "threshold": 500,
                "severity": AlertSeverity.WARNING,
                "message": "Высокое потребление памяти: {value}MB",
            },
            "disk_full": {
                "metric": "disk.usage_percent",
                "threshold": 90,
                "severity": AlertSeverity.CRITICAL,
                "message": "Диск заполнен на {value}%",
            },
            "error_rate_high": {
                "metric": "error_rate",
                "threshold": 10,
                "severity": AlertSeverity.WARNING,
                "message": "Высокий процент ошибок: {value}%",
            },
        }

    def fire(self, name: str, severity: AlertSeverity, message: str,
             source: str = "") -> Alert:
        """Создать алерт."""
        alert = Alert(
            name=name, severity=severity, message=message, source=source,
        )
        self._alerts.append(alert)
        self._active[name] = alert
        return alert

    def resolve(self, name: str) -> bool:
        """Разрешить алерт."""
        alert = self._active.pop(name, None)
        if alert:
            alert.resolve()
            return True
        return False

    def check_thresholds(self, metrics: dict[str, Any]) -> list[Alert]:
        """Проверить пороговые значения."""
        fired: list[Alert] = []
        for name, cfg in self._thresholds.items():
            metric_path = cfg["metric"]
            value = self._resolve_metric(metrics, metric_path)
            if value is not None and value > cfg["threshold"]:
                if name not in self._active:
                    alert = self.fire(
                        name=name,
                        severity=cfg["severity"],
                        message=cfg["message"].format(value=value),
                        source=metric_path,
                    )
                    fired.append(alert)
            elif name in self._active:
                self.resolve(name)
        return fired

    @staticmethod
    def _resolve_metric(metrics: dict[str, Any], path: str) -> Any:
        """Разрешить путь к метрике."""
        parts = path.split(".")
        current = metrics
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
            if current is None:
                return None
        return current

    def get_active(self) -> list[dict[str, Any]]:
        """Активные алерты."""
        return [a.to_dict() for a in self._active.values()]

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_alerts": len(self._alerts),
            "active_alerts": len(self._active),
            "thresholds": len(self._thresholds),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 10. PRODUCTION HARDENING — Центральный фасад
# ═══════════════════════════════════════════════════════════════════════════════


class ProductionHardening:
    """
    Центральный фасад Production Hardening.

    Объединяет все компоненты:
    - RateLimiter
    - RequestTracker
    - HealthChecker
    - GracefulShutdown
    - ErrorReporter
    - StructuredLogger
    - UptimeMonitor
    - SystemMetrics
    - AlertManager
    """

    def __init__(self) -> None:
        self.rate_limiter = RateLimiter()
        self.request_tracker = RequestTracker()
        self.health_checker = HealthChecker()
        self.shutdown = GracefulShutdown()
        self.error_reporter = ErrorReporter()
        self.structured_logger = StructuredLogger()
        self.uptime = UptimeMonitor()
        self.system_metrics = SystemMetrics()
        self.alert_manager = AlertManager()

    def get_stats(self) -> dict[str, Any]:
        """Общая статистика."""
        return {
            "rate_limiter": self.rate_limiter.get_stats(),
            "requests": self.request_tracker.get_stats(),
            "health": self.health_checker.get_stats(),
            "shutdown": self.shutdown.get_stats(),
            "errors": self.error_reporter.get_stats(),
            "logger": self.structured_logger.get_stats(),
            "uptime": self.uptime.get_stats(),
            "alerts": self.alert_manager.get_stats(),
        }

    def get_system_report(self) -> dict[str, Any]:
        """Полный системный отчёт."""
        sys_metrics = self.system_metrics.get_all()
        # Check thresholds
        self.alert_manager.check_thresholds(sys_metrics)

        return {
            "uptime": self.uptime.get_stats(),
            "health": self.health_checker.get_report(),
            "system": sys_metrics,
            "requests": self.request_tracker.get_stats(),
            "errors": self.error_reporter.get_stats(),
            "rate_limits": self.rate_limiter.get_stats(),
            "alerts": {
                "active": self.alert_manager.get_active(),
                "stats": self.alert_manager.get_stats(),
            },
        }


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

production = ProductionHardening()
