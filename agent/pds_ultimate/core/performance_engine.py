"""
PDS-Ultimate Performance Engine
=================================
Кэширование результатов + Batch API вызовы + пулинг.

Компоненты:
1. ResultCache — TTL-кэш результатов tool/LLM с умной инвалидацией
2. BatchAPIProcessor — группировка нескольких LLM вызовов в пакет
3. RequestDeduplicator — дедупликация параллельных одинаковых запросов
4. PerformanceMonitor — мониторинг latency, hit-rate, throughput

Без внешних зависимостей — чистый asyncio + stdlib.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

from pds_ultimate.config import logger

# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class CacheStrategy(str, Enum):
    """Стратегия кэширования."""
    TTL = "ttl"          # Кэш с временем жизни
    LRU = "lru"          # Least Recently Used
    LFU = "lfu"          # Least Frequently Used


@dataclass
class CacheEntry:
    """Запись в кэше."""
    key: str
    value: Any
    created_at: float
    expires_at: float
    access_count: int = 0
    last_accessed: float = 0.0
    category: str = "general"  # tool / llm / search

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def age(self) -> float:
        return time.time() - self.created_at


@dataclass
class CacheStats:
    """Статистика кэша."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    size: int = 0
    max_size: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{self.hit_rate:.1%}",
            "evictions": self.evictions,
            "size": self.size,
            "max_size": self.max_size,
        }


@dataclass
class BatchRequest:
    """Запрос в пакетной очереди."""
    request_id: str
    prompt: str
    system_prompt: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None
    json_mode: bool = False
    future: asyncio.Future | None = None
    created_at: float = field(default_factory=time.time)


@dataclass
class PerformanceMetrics:
    """Метрики производительности."""
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    batch_calls: int = 0
    dedup_saves: int = 0
    avg_latency_ms: float = 0.0
    _latencies: list[float] = field(default_factory=list)

    def record_latency(self, latency_ms: float) -> None:
        self._latencies.append(latency_ms)
        # Скользящее среднее (последние 100)
        recent = self._latencies[-100:]
        self.avg_latency_ms = sum(recent) / len(recent)

    def to_dict(self) -> dict:
        total = self.cache_hits + self.cache_misses
        return {
            "total_requests": self.total_requests,
            "cache_hit_rate": f"{self.cache_hits / total:.1%}" if total else "0%",
            "batch_calls": self.batch_calls,
            "dedup_saves": self.dedup_saves,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. RESULT CACHE
# ═══════════════════════════════════════════════════════════════════════════════


class ResultCache:
    """
    Умный кэш результатов с TTL, LRU-eviction и категориями.

    Использование:
        cache = ResultCache(max_size=1000, default_ttl=300)

        # Кэш tool результата
        cache.put("tool:weather:москва", data, category="tool", ttl=60)
        result = cache.get("tool:weather:москва")

        # Сокращение: decorator
        @cache.cached(ttl=120, category="llm")
        async def expensive_llm_call(prompt):
            ...
    """

    DEFAULT_TTL = 300  # 5 минут
    MAX_SIZE = 2000

    # TTL по категориям (секунды)
    CATEGORY_TTL = {
        "tool": 120,       # Результаты инструментов — 2 мин
        "llm": 300,        # LLM ответы — 5 мин
        "search": 600,     # Поисковые результаты — 10 мин
        "translation": 3600,  # Переводы — 1 час
        "parse": 60,       # Парсинг — 1 мин (данные могут меняться)
        "general": 300,    # По умолчанию
    }

    def __init__(
        self,
        max_size: int = MAX_SIZE,
        default_ttl: float = DEFAULT_TTL,
    ):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._stats = CacheStats(max_size=max_size)
        self._lock = asyncio.Lock()

    # ─── Core API ────────────────────────────────────────────────────────

    def get(self, key: str) -> Any | None:
        """
        Получить значение из кэша.
        Возвращает None если нет или протух.
        """
        entry = self._cache.get(key)

        if entry is None:
            self._stats.misses += 1
            return None

        if entry.is_expired:
            # Протухло — удаляем
            del self._cache[key]
            self._stats.misses += 1
            self._stats.size = len(self._cache)
            return None

        # Hit!
        entry.access_count += 1
        entry.last_accessed = time.time()
        # LRU: двигаем в конец
        self._cache.move_to_end(key)
        self._stats.hits += 1
        return entry.value

    def put(
        self,
        key: str,
        value: Any,
        ttl: float | None = None,
        category: str = "general",
    ) -> None:
        """Положить значение в кэш."""
        # Определяем TTL
        if ttl is None:
            ttl = self.CATEGORY_TTL.get(category, self._default_ttl)

        now = time.time()
        entry = CacheEntry(
            key=key,
            value=value,
            created_at=now,
            expires_at=now + ttl,
            last_accessed=now,
            category=category,
        )

        # Если ключ уже есть — обновляем
        if key in self._cache:
            self._cache[key] = entry
            self._cache.move_to_end(key)
        else:
            # Eviction если переполнено
            while len(self._cache) >= self._max_size:
                self._evict()
            self._cache[key] = entry

        self._stats.size = len(self._cache)

    def invalidate(self, key: str) -> bool:
        """Удалить конкретный ключ."""
        if key in self._cache:
            del self._cache[key]
            self._stats.size = len(self._cache)
            return True
        return False

    def invalidate_pattern(self, pattern: str) -> int:
        """Удалить все ключи, начинающиеся с pattern."""
        keys_to_delete = [
            k for k in self._cache if k.startswith(pattern)
        ]
        for k in keys_to_delete:
            del self._cache[k]
        self._stats.size = len(self._cache)
        return len(keys_to_delete)

    def invalidate_category(self, category: str) -> int:
        """Удалить все записи определённой категории."""
        keys_to_delete = [
            k for k, v in self._cache.items() if v.category == category
        ]
        for k in keys_to_delete:
            del self._cache[k]
        self._stats.size = len(self._cache)
        return len(keys_to_delete)

    def clear(self) -> None:
        """Очистить весь кэш."""
        self._cache.clear()
        self._stats.size = 0

    def cleanup_expired(self) -> int:
        """Удалить все протухшие записи."""
        expired = [k for k, v in self._cache.items() if v.is_expired]
        for k in expired:
            del self._cache[k]
        self._stats.size = len(self._cache)
        return len(expired)

    # ─── Decorator ───────────────────────────────────────────────────────

    def cached(
        self,
        ttl: float | None = None,
        category: str = "general",
        key_prefix: str = "",
    ):
        """
        Декоратор для кэширования async функций.

        @cache.cached(ttl=60, category="tool")
        async def get_weather(city: str):
            ...
        """
        def decorator(func):
            async def wrapper(*args, **kwargs):
                # Генерируем ключ
                cache_key = self._make_key(
                    key_prefix or func.__name__, args, kwargs
                )

                # Проверяем кэш
                cached_value = self.get(cache_key)
                if cached_value is not None:
                    return cached_value

                # Выполняем функцию
                result = await func(*args, **kwargs)

                # Кэшируем
                self.put(cache_key, result, ttl=ttl, category=category)
                return result

            wrapper.__wrapped__ = func
            wrapper.__name__ = func.__name__
            return wrapper
        return decorator

    # ─── Statistics ──────────────────────────────────────────────────────

    @property
    def stats(self) -> CacheStats:
        return self._stats

    @property
    def size(self) -> int:
        return len(self._cache)

    def get_stats(self) -> dict:
        """Полная статистика кэша."""
        # Подсчёт по категориям
        categories: dict[str, int] = {}
        for entry in self._cache.values():
            categories[entry.category] = categories.get(entry.category, 0) + 1

        return {
            **self._stats.to_dict(),
            "categories": categories,
        }

    # ─── Internal ────────────────────────────────────────────────────────

    def _evict(self) -> None:
        """Вытеснить самую старую неиспользуемую запись (LRU)."""
        if self._cache:
            # OrderedDict — первый элемент = самый старый
            self._cache.popitem(last=False)
            self._stats.evictions += 1

    @staticmethod
    def _make_key(prefix: str, args: tuple, kwargs: dict) -> str:
        """Создать ключ кэша из аргументов."""
        raw = json.dumps(
            {"args": [str(a) for a in args], "kwargs": {str(k): str(v)
                                                        for k, v in kwargs.items()}},
            sort_keys=True,
        )
        h = hashlib.md5(raw.encode()).hexdigest()[:12]
        return f"{prefix}:{h}"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. REQUEST DEDUPLICATOR
# ═══════════════════════════════════════════════════════════════════════════════


class RequestDeduplicator:
    """
    Дедупликация параллельных запросов.

    Если два пользователя одновременно спрашивают одно и то же,
    выполняем запрос один раз и отдаём результат обоим.
    """

    def __init__(self):
        self._inflight: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()
        self._dedup_count = 0

    async def deduplicate(
        self,
        key: str,
        coro_factory: Callable[[], Coroutine],
    ) -> Any:
        """
        Выполнить coroutine с дедупликацией.

        Если запрос с таким ключом уже в полёте — ждём его результат.
        Иначе — запускаем новый.

        Args:
            key: Ключ дедупликации
            coro_factory: Фабрика coroutine (вызовется если запроса нет в полёте)

        Returns:
            Результат coroutine
        """
        async with self._lock:
            if key in self._inflight:
                # Уже есть запрос — ждём его
                self._dedup_count += 1
                future = self._inflight[key]
                logger.debug(f"Dedup: ждём существующий запрос '{key}'")

        if key in self._inflight:
            return await future

        # Создаём новый запрос
        loop = asyncio.get_event_loop()
        future = loop.create_future()

        async with self._lock:
            self._inflight[key] = future

        try:
            result = await coro_factory()
            future.set_result(result)
            return result
        except Exception as e:
            future.set_exception(e)
            raise
        finally:
            async with self._lock:
                self._inflight.pop(key, None)

    @property
    def dedup_count(self) -> int:
        return self._dedup_count

    @property
    def inflight_count(self) -> int:
        return len(self._inflight)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. BATCH API PROCESSOR
# ═══════════════════════════════════════════════════════════════════════════════


class BatchAPIProcessor:
    """
    Группировка нескольких LLM-вызовов в один batch.

    Накапливает запросы за window_ms миллисекунд,
    затем отправляет все разом (или по одному, если batch API нет).

    Usage:
        batch = BatchAPIProcessor(llm_engine, window_ms=100)
        await batch.start()

        # Запросы будут группироваться автоматически
        result = await batch.submit("Переведи: Hello")
    """

    def __init__(
        self,
        llm_call: Callable | None = None,
        window_ms: float = 100,
        max_batch_size: int = 10,
    ):
        self._llm_call = llm_call
        self._window_ms = window_ms
        self._max_batch_size = max_batch_size
        self._queue: list[BatchRequest] = []
        self._lock = asyncio.Lock()
        self._processor_task: asyncio.Task | None = None
        self._running = False
        self._batch_count = 0

    async def start(self) -> None:
        """Запустить фоновый процессор."""
        self._running = True
        self._processor_task = asyncio.create_task(self._process_loop())
        logger.info(
            f"BatchAPIProcessor запущен (window={self._window_ms}ms, "
            f"max_batch={self._max_batch_size})"
        )

    async def stop(self) -> None:
        """Остановить процессор."""
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        # Обработать оставшиеся запросы
        if self._queue:
            await self._flush_batch()
        logger.info("BatchAPIProcessor остановлен")

    async def submit(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        """
        Отправить запрос в batch-очередь.

        Returns:
            Результат LLM
        """
        loop = asyncio.get_event_loop()
        future = loop.create_future()

        request = BatchRequest(
            request_id=hashlib.md5(
                f"{prompt}{time.time()}".encode()
            ).hexdigest()[:12],
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
            future=future,
        )

        async with self._lock:
            self._queue.append(request)

            # Если достигнут max_batch — сразу flush
            if len(self._queue) >= self._max_batch_size:
                await self._flush_batch()

        return await future

    async def _process_loop(self) -> None:
        """Фоновый цикл обработки batch."""
        while self._running:
            await asyncio.sleep(self._window_ms / 1000)
            if self._queue:
                await self._flush_batch()

    async def _flush_batch(self) -> None:
        """Обработать накопленный batch."""
        async with self._lock:
            batch = self._queue[:self._max_batch_size]
            self._queue = self._queue[self._max_batch_size:]

        if not batch:
            return

        self._batch_count += 1
        logger.debug(
            f"Batch #{self._batch_count}: обработка {len(batch)} запросов")

        # Параллельно выполняем все запросы
        tasks = [self._execute_single(req) for req in batch]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_single(self, request: BatchRequest) -> None:
        """Выполнить один запрос из batch."""
        if not self._llm_call or not request.future:
            return

        try:
            result = await self._llm_call(
                message=request.prompt,
                system_prompt=request.system_prompt,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                json_mode=request.json_mode,
            )
            if not request.future.done():
                request.future.set_result(result)
        except Exception as e:
            if not request.future.done():
                request.future.set_exception(e)

    @property
    def batch_count(self) -> int:
        return self._batch_count

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    def get_stats(self) -> dict:
        return {
            "batch_count": self._batch_count,
            "queue_size": self.queue_size,
            "running": self._running,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. PERFORMANCE MONITOR
# ═══════════════════════════════════════════════════════════════════════════════


class PerformanceMonitor:
    """
    Мониторинг производительности всей системы.

    Собирает метрики:
    - Cache hit rate
    - Average latency
    - Throughput (requests/sec)
    - Batch efficiency
    """

    def __init__(self):
        self._metrics = PerformanceMetrics()
        self._start_time = time.time()

    def record_request(
        self,
        latency_ms: float,
        cached: bool = False,
    ) -> None:
        """Записать метрику запроса."""
        self._metrics.total_requests += 1
        if cached:
            self._metrics.cache_hits += 1
        else:
            self._metrics.cache_misses += 1
        self._metrics.record_latency(latency_ms)

    def record_batch(self) -> None:
        """Записать batch вызов."""
        self._metrics.batch_calls += 1

    def record_dedup(self) -> None:
        """Записать дедупликацию."""
        self._metrics.dedup_saves += 1

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time

    @property
    def throughput(self) -> float:
        """Запросов в секунду."""
        uptime = self.uptime
        if uptime == 0:
            return 0
        return self._metrics.total_requests / uptime

    def get_report(self) -> dict:
        """Полный отчёт производительности."""
        return {
            **self._metrics.to_dict(),
            "uptime_sec": round(self.uptime, 1),
            "throughput_rps": round(self.throughput, 2),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. PERFORMANCE ENGINE — Главный оркестратор
# ═══════════════════════════════════════════════════════════════════════════════


class PerformanceEngine:
    """
    Главный оркестратор производительности.

    Объединяет:
    - ResultCache: кэш результатов
    - RequestDeduplicator: дедупликация
    - BatchAPIProcessor: batch LLM
    - PerformanceMonitor: мониторинг

    Встраивается в LLMEngine и ToolRegistry.
    """

    def __init__(
        self,
        cache_size: int = 2000,
        cache_ttl: float = 300,
        batch_window_ms: float = 100,
    ):
        self._cache = ResultCache(max_size=cache_size, default_ttl=cache_ttl)
        self._dedup = RequestDeduplicator()
        self._batch = BatchAPIProcessor(window_ms=batch_window_ms)
        self._monitor = PerformanceMonitor()

    @property
    def cache(self) -> ResultCache:
        return self._cache

    @property
    def dedup(self) -> RequestDeduplicator:
        return self._dedup

    @property
    def batch(self) -> BatchAPIProcessor:
        return self._batch

    @property
    def monitor(self) -> PerformanceMonitor:
        return self._monitor

    async def cached_call(
        self,
        key: str,
        coro_factory: Callable[[], Coroutine],
        ttl: float | None = None,
        category: str = "general",
    ) -> Any:
        """
        Вызов с кэшированием и дедупликацией.

        1. Проверяем кэш
        2. Если miss — дедуплицируем
        3. Кэшируем результат

        Args:
            key: Ключ кэша
            coro_factory: Фабрика coroutine
            ttl: Время жизни кэша
            category: Категория кэша

        Returns:
            Результат вызова
        """
        start = time.time()

        # 1. Проверяем кэш
        cached = self._cache.get(key)
        if cached is not None:
            latency = (time.time() - start) * 1000
            self._monitor.record_request(latency, cached=True)
            return cached

        # 2. Дедуплицируем + выполняем
        result = await self._dedup.deduplicate(key, coro_factory)

        # 3. Кэшируем
        self._cache.put(key, result, ttl=ttl, category=category)

        latency = (time.time() - start) * 1000
        self._monitor.record_request(latency, cached=False)

        return result

    async def start(self) -> None:
        """Запустить все компоненты."""
        logger.info("PerformanceEngine запущен")

    async def stop(self) -> None:
        """Остановить все компоненты."""
        await self._batch.stop()
        logger.info("PerformanceEngine остановлен")

    def get_stats(self) -> dict:
        """Полная статистика."""
        return {
            "cache": self._cache.get_stats(),
            "dedup": {
                "saves": self._dedup.dedup_count,
                "inflight": self._dedup.inflight_count,
            },
            "batch": self._batch.get_stats(),
            "performance": self._monitor.get_report(),
        }


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

performance_engine = PerformanceEngine()
