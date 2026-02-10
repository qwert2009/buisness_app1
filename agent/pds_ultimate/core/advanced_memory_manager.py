"""
PDS-Ultimate Advanced Memory Manager (часть 2)
=================================================
Менеджер памяти с семантическим поиском, failure-driven learning,
time awareness, context compression, memory pruning.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import datetime, timedelta

from pds_ultimate.config import logger
from pds_ultimate.core.advanced_memory import (
    AdvancedMemoryEntry,
    AdvancedWorkingMemory,
    FailureEntry,
    MemoryType,
)

# ═══════════════════════════════════════════════════════════════════════════════
# TF-IDF SEMANTIC SEARCH (без внешних embeddings)
# ═══════════════════════════════════════════════════════════════════════════════


class SemanticIndex:
    """
    Семантический индекс для поиска по смыслу.

    Использует TF-IDF + n-gram overlap + tag matching.
    Работает без внешних API (DeepSeek/OpenAI embeddings).
    При наличии embeddings API — можно добавить vector search.
    """

    # Стоп-слова (русские + английские)
    STOP_WORDS = frozenset({
        "и", "в", "на", "с", "по", "для", "из", "что", "это", "как",
        "не", "но", "от", "к", "за", "то", "он", "она", "мы", "вы",
        "a", "the", "is", "in", "on", "at", "to", "for", "of", "and",
        "or", "but", "it", "this", "that", "with", "from", "by", "be",
        "are", "was", "were", "been", "will", "would", "can", "could",
        "я", "ты", "его", "её", "их", "мой", "свой", "все", "так",
        "да", "нет", "уже", "ещё", "бы", "ли", "же", "если", "когда",
    })

    def __init__(self):
        self._doc_freq: Counter = Counter()  # document frequency
        self._total_docs: int = 0

    def tokenize(self, text: str) -> list[str]:
        """Токенизация с нормализацией."""
        text = text.lower().strip()
        tokens = re.findall(r'[а-яёa-z0-9_-]{2,}', text)
        return [t for t in tokens if t not in self.STOP_WORDS]

    def bigrams(self, tokens: list[str]) -> list[str]:
        """Биграммы для улучшения точности."""
        return [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - 1)]

    def update_index(self, entries: list[AdvancedMemoryEntry]) -> None:
        """Обновить индекс частот из всех записей."""
        self._doc_freq.clear()
        self._total_docs = len(entries)

        for entry in entries:
            tokens = set(self.tokenize(entry.content))
            tokens.update(t.lower() for t in entry.tags)
            for token in tokens:
                self._doc_freq[token] += 1

    def score(self, query: str, entry: AdvancedMemoryEntry) -> float:
        """
        Вычислить релевантность записи к запросу.

        Scoring = TF-IDF overlap + tag match + bigram match + type bonus
        """
        query_tokens = self.tokenize(query)
        if not query_tokens:
            return 0.0

        content_tokens = self.tokenize(entry.content)
        tag_tokens = [t.lower() for t in entry.tags]

        # TF-IDF scoring
        query_set = set(query_tokens)
        content_set = set(content_tokens)

        tfidf_score = 0.0
        for token in query_set & content_set:
            tf = content_tokens.count(token) / max(1, len(content_tokens))
            df = self._doc_freq.get(token, 1)
            idf = math.log(max(1, self._total_docs) / max(1, df))
            tfidf_score += tf * idf

        # Tag match (высокий вес)
        tag_set = set(tag_tokens)
        tag_overlap = len(query_set & tag_set)
        tag_score = tag_overlap * 2.0

        # Bigram match (фразовое совпадение)
        query_bigrams = set(self.bigrams(query_tokens))
        content_bigrams = set(self.bigrams(content_tokens))
        bigram_overlap = len(query_bigrams & content_bigrams)
        bigram_score = bigram_overlap * 1.5

        # Effective importance
        eff_importance = entry.effective_importance()

        total = (tfidf_score + tag_score + bigram_score) * eff_importance
        return total


# ═══════════════════════════════════════════════════════════════════════════════
# CONTEXT COMPRESSOR
# ═══════════════════════════════════════════════════════════════════════════════

class ContextCompressor:
    """
    Auto-summary & context compression.

    - Рекурсивное суммирование длинных текстов
    - Chunking для больших документов
    - Compression ratio tracking
    """

    MAX_CONTEXT_CHARS = 4000
    CHUNK_SIZE = 2000

    @staticmethod
    def compress_history(
        history: list[dict[str, str]],
        max_messages: int = 10,
    ) -> list[dict[str, str]]:
        """
        Сжать историю диалога.

        Стратегия:
        1. Последние N сообщений — оставить полностью
        2. Более старые — сжать в summary
        """
        if len(history) <= max_messages:
            return history

        # Разделяем: старые + недавние
        old = history[:-max_messages]
        recent = history[-max_messages:]

        # Сжимаем старые в 1 сообщение
        summary_parts = []
        for msg in old:
            role = msg.get("role", "user")
            content = msg.get("content", "")[:100]
            summary_parts.append(f"[{role}] {content}")

        summary = (
            f"[Сжатая история ({len(old)} сообщений)]\n"
            + "\n".join(summary_parts[-10:])  # Макс 10 строк из старых
        )

        compressed = [{"role": "system", "content": summary}] + recent
        return compressed

    @staticmethod
    def compress_text(text: str, max_length: int = 2000) -> str:
        """
        Сжать длинный текст, сохранив ключевую информацию.

        Стратегия: оставить первый абзац + последний абзац + ключевые предложения.
        """
        if len(text) <= max_length:
            return text

        paragraphs = text.split("\n\n")
        if len(paragraphs) <= 2:
            return text[:max_length] + "..."

        # Первый + последний абзац
        first = paragraphs[0][:max_length // 3]
        last = paragraphs[-1][:max_length // 3]

        # Из середины — предложения с числами и ключевыми словами
        middle = "\n\n".join(paragraphs[1:-1])
        key_sentences = []
        for sent in re.split(r'[.!?]\s+', middle):
            if any(c.isdigit() for c in sent) or len(sent.split()) > 5:
                key_sentences.append(sent.strip())
                if len("\n".join(key_sentences)) > max_length // 3:
                    break

        middle_text = ". ".join(key_sentences[:5])
        result = f"{first}\n\n[...сжато...]\n\n{middle_text}\n\n{last}"
        return result[:max_length]

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 2000,
                   overlap: int = 200) -> list[str]:
        """Разбить текст на chunks с перекрытием."""
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]

            # Ищем конец предложения
            if end < len(text):
                last_period = chunk.rfind(".")
                if last_period > chunk_size // 2:
                    chunk = chunk[:last_period + 1]
                    end = start + last_period + 1

            chunks.append(chunk)
            start = end - overlap if end < len(text) else end

        return chunks


# ═══════════════════════════════════════════════════════════════════════════════
# ADVANCED MEMORY MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class AdvancedMemoryManager:
    """
    Продвинутый менеджер памяти.

    Возможности:
    1. 5 типов памяти (episodic, semantic, procedural, strategic, failure)
    2. Failure-driven learning (хранение ошибок, адаптация)
    3. Time awareness (decay, expiry, актуальность)
    4. Auto-summary & context compression
    5. Memory pruning (удаление устаревших)
    6. TF-IDF semantic search
    7. Per-user memory isolation
    8. Confidence tracking
    """

    MAX_MEMORIES = 2000
    PRUNE_THRESHOLD = 0.05  # Удаляем записи с effective_importance < threshold
    PRUNE_AGE_DAYS = 90     # Удаляем записи старше N дней с низкой важностью

    # Промпт для извлечения фактов (расширенный)
    FACT_EXTRACTION_PROMPT = """Проанализируй диалог и извлеки важные факты.
Классифицируй каждый факт по типу памяти.

Верни JSON массив:
[
  {{
    "fact": "краткое описание",
    "type": "episodic|semantic|procedural|strategic|preference|rule",
    "importance": 0.0-1.0,
    "confidence": 0.0-1.0,
    "tags": ["тег1", "тег2"],
    "expiry_days": null или число дней актуальности
  }}
]

Типы:
- episodic: конкретное событие, действие, результат
- semantic: обобщённое знание, факт о мире
- procedural: алгоритм, процедура, способ сделать
- strategic: решение о приоритетах, планах, стратегии
- preference: предпочтение пользователя
- rule: бизнес-правило

Извлекай ТОЛЬКО действительно важные факты.
Пустой массив [] если ничего важного нет."""

    FAILURE_ANALYSIS_PROMPT = """Проанализируй неудачу агента.

Ошибка: {error}
Контекст: {context}
Исходная цель: {goal}

Верни JSON:
{{
  "what_went_wrong": "краткое описание ошибки",
  "root_cause": "причина",
  "correction": "как надо было сделать",
  "severity": "low|medium|high|critical",
  "lesson": "урок на будущее",
  "tags": ["тег1", "тег2"]
}}"""

    def __init__(self):
        self._memories: list[AdvancedMemoryEntry] = []
        self._working: dict[int, AdvancedWorkingMemory] = {}
        self._index = SemanticIndex()
        self._compressor = ContextCompressor()
        self._index_dirty = True  # Нужно ли обновить индекс

    # ─── Working Memory ──────────────────────────────────────────────────

    def get_working(self, chat_id: int) -> AdvancedWorkingMemory:
        """Получить или создать рабочую память для чата."""
        if chat_id not in self._working:
            self._working[chat_id] = AdvancedWorkingMemory()
        return self._working[chat_id]

    def reset_working(self, chat_id: int) -> None:
        """Сбросить рабочую память."""
        if chat_id in self._working:
            self._working[chat_id].reset()

    # ─── Store ───────────────────────────────────────────────────────────

    def store(self, entry: AdvancedMemoryEntry) -> None:
        """Сохранить запись с дедупликацией."""
        # Дедупликация по context_hash
        for existing in self._memories:
            if existing.context_hash == entry.context_hash and existing.is_active:
                # Обновляем существующую
                existing.importance = max(
                    existing.importance, entry.importance)
                existing.confidence = max(
                    existing.confidence, entry.confidence)
                existing.touch()
                logger.debug(f"Memory deduplicated: {entry.content[:40]}...")
                return

        self._memories.append(entry)
        self._index_dirty = True
        self._enforce_limits()
        logger.debug(
            f"Memory stored: [{entry.memory_type}] {entry.content[:50]}..."
        )

    def store_fact(self, content: str, importance: float = 0.5,
                   confidence: float = 0.8, tags: list[str] | None = None,
                   source: str = "extraction",
                   chat_id: int | None = None) -> AdvancedMemoryEntry:
        """Быстрое сохранение факта."""
        entry = AdvancedMemoryEntry(
            content=content,
            memory_type=MemoryType.FACT,
            importance=importance,
            confidence=confidence,
            tags=tags or [],
            source=source,
            chat_id=chat_id,
        )
        self.store(entry)
        return entry

    def store_preference(self, content: str, importance: float = 0.7,
                         chat_id: int | None = None) -> AdvancedMemoryEntry:
        """Сохранить предпочтение."""
        entry = AdvancedMemoryEntry(
            content=content,
            memory_type=MemoryType.PREFERENCE,
            importance=importance,
            confidence=0.9,
            tags=["preference", "user"],
            source="extraction",
            decay_rate=0.02,  # Предпочтения не забываются быстро
            chat_id=chat_id,
        )
        self.store(entry)
        return entry

    def store_rule(self, content: str, importance: float = 0.8,
                   chat_id: int | None = None) -> AdvancedMemoryEntry:
        """Сохранить бизнес-правило."""
        entry = AdvancedMemoryEntry(
            content=content,
            memory_type=MemoryType.RULE,
            importance=importance,
            confidence=0.9,
            tags=["rule", "business"],
            source="extraction",
            decay_rate=0.01,  # Правила почти не забываются
            chat_id=chat_id,
        )
        self.store(entry)
        return entry

    def store_procedural(self, content: str, importance: float = 0.7,
                         tags: list[str] | None = None,
                         chat_id: int | None = None) -> AdvancedMemoryEntry:
        """Сохранить процедурное знание (как делать)."""
        entry = AdvancedMemoryEntry(
            content=content,
            memory_type=MemoryType.PROCEDURAL,
            importance=importance,
            confidence=0.8,
            tags=(tags or []) + ["procedural", "how-to"],
            source="extraction",
            decay_rate=0.03,
            chat_id=chat_id,
        )
        self.store(entry)
        return entry

    def store_strategic(self, content: str, importance: float = 0.9,
                        tags: list[str] | None = None,
                        chat_id: int | None = None) -> AdvancedMemoryEntry:
        """Сохранить стратегическое решение."""
        entry = AdvancedMemoryEntry(
            content=content,
            memory_type=MemoryType.STRATEGIC,
            importance=importance,
            confidence=0.85,
            tags=(tags or []) + ["strategic", "decision"],
            source="extraction",
            decay_rate=0.005,  # Стратегии живут долго
            chat_id=chat_id,
        )
        self.store(entry)
        return entry

    # ─── Failure-Driven Learning ─────────────────────────────────────────

    def store_failure(
        self,
        content: str,
        error_context: str = "",
        correction: str = "",
        severity: str = "medium",
        tags: list[str] | None = None,
        chat_id: int | None = None,
    ) -> FailureEntry:
        """
        Failure-driven learning: сохранить ошибку.

        Агент учится на ошибках — при похожей ситуации
        НЕ повторяет неудачное решение.
        """
        entry = FailureEntry(
            content=content,
            error_context=error_context,
            correction=correction,
            severity=severity,
            tags=tags or [],
            source="failure_learning",
            chat_id=chat_id,
        )
        self.store(entry)
        logger.info(
            f"Failure stored [{severity}]: {content[:60]}..."
        )
        return entry

    def get_relevant_failures(
        self, query: str, limit: int = 3
    ) -> list[FailureEntry]:
        """Найти релевантные ошибки (чтобы не повторять)."""
        failures = [
            m for m in self._memories
            if m.memory_type == MemoryType.FAILURE
            and m.is_active
            and not m.is_expired()
        ]

        if not failures:
            return []

        self._rebuild_index_if_needed()
        scored = []
        for f in failures:
            score = self._index.score(query, f)
            if score > 0:
                scored.append((score, f))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in scored[:limit]]

    # ─── Semantic Recall ─────────────────────────────────────────────────

    def recall(
        self,
        query: str,
        limit: int = 5,
        memory_type: str | None = None,
        tags: list[str] | None = None,
        min_importance: float = 0.0,
        chat_id: int | None = None,
    ) -> list[AdvancedMemoryEntry]:
        """
        Semantic recall — поиск по смыслу (TF-IDF + tags + decay).
        """
        self._rebuild_index_if_needed()

        candidates = [
            m for m in self._memories
            if m.is_active and not m.is_expired()
        ]

        # Фильтры
        if memory_type:
            candidates = [
                m for m in candidates if m.memory_type == memory_type]
        if tags:
            candidates = [
                m for m in candidates if any(t in m.tags for t in tags)
            ]
        if min_importance > 0:
            candidates = [
                m for m in candidates
                if m.effective_importance() >= min_importance
            ]
        if chat_id is not None:
            candidates = [
                m for m in candidates
                if m.chat_id is None or m.chat_id == chat_id
            ]

        # TF-IDF scoring
        scored = []
        for m in candidates:
            score = self._index.score(query, m)
            if score > 0:
                scored.append((score, m))

        scored.sort(key=lambda x: x[0], reverse=True)

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
        chat_id: int | None = None,
    ) -> list[AdvancedMemoryEntry]:
        """Получить все воспоминания, отсортированные по effective importance."""
        candidates = [
            m for m in self._memories
            if m.is_active and not m.is_expired()
        ]
        if memory_type:
            candidates = [
                m for m in candidates if m.memory_type == memory_type]
        if min_importance > 0:
            candidates = [
                m for m in candidates
                if m.effective_importance() >= min_importance
            ]
        if chat_id is not None:
            candidates = [
                m for m in candidates
                if m.chat_id is None or m.chat_id == chat_id
            ]

        candidates.sort(key=lambda m: m.effective_importance(), reverse=True)
        return candidates[:limit]

    def get_context_for_prompt(
        self, query: str, max_entries: int = 7,
        chat_id: int | None = None,
    ) -> str:
        """
        Получить контекст из памяти для system prompt.

        Собирает из ВСЕХ типов памяти — не только факты.
        Включает failures (уроки), procedures (как делать), strategies.
        """
        results: list[AdvancedMemoryEntry] = []

        # Из каждого типа берём самое релевантное
        for mem_type in [
            MemoryType.FACT, MemoryType.PREFERENCE, MemoryType.RULE,
            MemoryType.STRATEGIC, MemoryType.PROCEDURAL,
        ]:
            found = self.recall(
                query, limit=2, memory_type=mem_type, chat_id=chat_id
            )
            results.extend(found)

        # Добавляем уроки из ошибок
        failures = self.get_relevant_failures(query, limit=2)
        results.extend(failures)

        # Дедупликация
        seen = set()
        unique = []
        for e in results:
            if e.content not in seen:
                seen.add(e.content)
                unique.append(e)

        if not unique:
            return ""

        # Сортируем по effective importance
        unique.sort(key=lambda e: e.effective_importance(), reverse=True)
        unique = unique[:max_entries]

        lines = ["ДОЛГОСРОЧНАЯ ПАМЯТЬ:"]
        for e in unique:
            icon = {
                MemoryType.FACT: "📌",
                MemoryType.PREFERENCE: "⭐",
                MemoryType.RULE: "📏",
                MemoryType.SEMANTIC: "📚",
                MemoryType.PROCEDURAL: "🔧",
                MemoryType.STRATEGIC: "🎯",
                MemoryType.FAILURE: "⚠️",
                MemoryType.EPISODIC: "📖",
            }.get(e.memory_type, "•")

            conf = f"[conf={e.confidence:.0%}]" if e.confidence < 0.7 else ""
            line = f"  {icon} {e.content}"
            if conf:
                line += f" {conf}"

            # Для failures — добавляем correction
            if isinstance(e, FailureEntry) and e.correction:
                line += f"\n     → Урок: {e.correction}"

            lines.append(line)

        return "\n".join(lines)

    # ─── Time Awareness ──────────────────────────────────────────────────

    def get_time_context(self) -> str:
        """
        Time awareness — информация о текущем времени для агента.
        Агент должен понимать «когда сейчас» и учитывать актуальность.
        """
        now = datetime.utcnow()
        return (
            f"ТЕКУЩЕЕ ВРЕМЯ: {now.strftime('%Y-%m-%d %H:%M')} UTC\n"
            f"День недели: {now.strftime('%A')}\n"
            f"⚠️ Проверяй актуальность данных. "
            f"Данные старше 2024 могут быть устаревшими."
        )

    # ─── Memory Pruning ──────────────────────────────────────────────────

    def prune(self) -> int:
        """
        Memory embedding pruning — удаление устаревших записей.

        Удаляет:
        1. Expired записи
        2. Записи с effective_importance < threshold
        3. Старые записи с низкой важностью и 0 обращений
        """
        before = len(self._memories)
        now = datetime.utcnow()
        cutoff = now - timedelta(days=self.PRUNE_AGE_DAYS)

        active = []
        for m in self._memories:
            # Удаляем expired
            if m.is_expired():
                continue

            # Удаляем с очень низкой эффективностью
            if m.effective_importance() < self.PRUNE_THRESHOLD:
                continue

            # Удаляем старые неиспользуемые
            if (m.created_at < cutoff
                    and m.access_count == 0
                    and m.importance < 0.3):
                continue

            active.append(m)

        self._memories = active
        pruned = before - len(self._memories)

        if pruned > 0:
            self._index_dirty = True
            logger.info(f"Memory pruned: {pruned} записей удалено")

        return pruned

    # ─── Persist to/from DB ──────────────────────────────────────────────

    def save_to_db(self, db_session) -> int:
        """Сохранить все unsaved memories в БД."""
        from pds_ultimate.core.database import AgentMemory

        count = 0
        for m in self._memories:
            if m.db_id is not None:
                continue  # Уже в БД

            metadata = m.metadata.copy()
            metadata["confidence"] = m.confidence
            metadata["decay_rate"] = m.decay_rate
            metadata["source_quality"] = m.source_quality
            metadata["failure_count"] = m.failure_count
            metadata["success_count"] = m.success_count
            metadata["context_hash"] = m.context_hash
            if m.chat_id is not None:
                metadata["chat_id"] = m.chat_id
            if m.expiry:
                metadata["expiry"] = m.expiry.isoformat()
            if isinstance(m, FailureEntry):
                metadata["error_context"] = m.error_context
                metadata["correction"] = m.correction
                metadata["severity"] = m.severity

            db_entry = AgentMemory(
                content=m.content,
                memory_type=m.memory_type,
                importance=m.importance,
                tags=json.dumps(m.tags, ensure_ascii=False),
                source=m.source,
                metadata_json=json.dumps(
                    metadata, ensure_ascii=False, default=str
                ),
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
        """Загрузить memories из БД."""
        from pds_ultimate.core.database import AgentMemory

        try:
            db_entries = db_session.query(AgentMemory).filter_by(
                is_active=True
            ).order_by(
                AgentMemory.importance.desc()
            ).limit(self.MAX_MEMORIES).all()

            count = 0
            existing_ids = {
                m.db_id for m in self._memories if m.db_id is not None
            }

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
                        db_entry.metadata_json
                    ) if db_entry.metadata_json else {}
                except (json.JSONDecodeError, TypeError):
                    pass

                # Восстанавливаем расширенные поля из metadata
                confidence = float(metadata.get("confidence", 0.8))
                decay_rate = float(metadata.get("decay_rate", 0.1))
                source_quality = float(metadata.get("source_quality", 0.7))
                chat_id = metadata.get("chat_id")
                expiry = None
                if metadata.get("expiry"):
                    try:
                        expiry = datetime.fromisoformat(metadata["expiry"])
                    except (ValueError, TypeError):
                        pass

                # FailureEntry или обычная
                if db_entry.memory_type == MemoryType.FAILURE:
                    entry = FailureEntry(
                        content=db_entry.content,
                        error_context=metadata.get("error_context", ""),
                        correction=metadata.get("correction", ""),
                        severity=metadata.get("severity", "medium"),
                        importance=db_entry.importance,
                        confidence=confidence,
                        tags=tags,
                        source=db_entry.source or "db",
                        decay_rate=decay_rate,
                        source_quality=source_quality,
                        chat_id=chat_id,
                    )
                else:
                    entry = AdvancedMemoryEntry(
                        content=db_entry.content,
                        memory_type=db_entry.memory_type,
                        importance=db_entry.importance,
                        confidence=confidence,
                        tags=tags,
                        source=db_entry.source or "db",
                        metadata=metadata,
                        decay_rate=decay_rate,
                        expiry=expiry,
                        source_quality=source_quality,
                        chat_id=chat_id,
                    )

                entry.db_id = db_entry.id
                entry.access_count = db_entry.access_count or 0
                entry.created_at = db_entry.created_at
                entry.failure_count = int(metadata.get("failure_count", 0))
                entry.success_count = int(metadata.get("success_count", 0))

                self._memories.append(entry)
                count += 1

            if count > 0:
                self._index_dirty = True
            logger.info(f"Загружено {count} записей памяти из БД")
            return count
        except Exception as e:
            logger.warning(f"Не удалось загрузить память из БД: {e}")
            return 0

    # ─── Fact Extraction ─────────────────────────────────────────────────

    async def extract_and_store_facts(
        self, dialogue: str, llm_engine=None,
        chat_id: int | None = None,
    ) -> list[AdvancedMemoryEntry]:
        """Извлечь факты из диалога через LLM."""
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

                # Определяем expiry
                expiry = None
                expiry_days = fact_data.get("expiry_days")
                if expiry_days and isinstance(expiry_days, (int, float)):
                    expiry = datetime.utcnow() + timedelta(days=expiry_days)

                entry = AdvancedMemoryEntry(
                    content=content,
                    memory_type=fact_data.get("type", MemoryType.FACT),
                    importance=float(fact_data.get("importance", 0.5)),
                    confidence=float(fact_data.get("confidence", 0.8)),
                    tags=fact_data.get("tags", []),
                    source="extraction",
                    expiry=expiry,
                    chat_id=chat_id,
                )
                self.store(entry)
                stored.append(entry)

            if stored:
                logger.info(f"Извлечено {len(stored)} фактов из диалога")
            return stored

        except Exception as e:
            logger.warning(f"Ошибка извлечения фактов: {e}")
            return []

    # ─── Failure Analysis ────────────────────────────────────────────────

    async def analyze_and_store_failure(
        self,
        error: str,
        context: str,
        goal: str,
        llm_engine=None,
        chat_id: int | None = None,
    ) -> FailureEntry | None:
        """
        Failure-driven learning: проанализировать ошибку через LLM.

        Агент анализирует что пошло не так и сохраняет урок.
        В будущем при похожей ситуации не повторит ошибку.
        """
        if not llm_engine:
            from pds_ultimate.core.llm_engine import llm_engine as default_engine
            llm_engine = default_engine

        prompt = self.FAILURE_ANALYSIS_PROMPT.format(
            error=error, context=context, goal=goal,
        )

        try:
            response = await llm_engine.chat(
                message=prompt,
                system_prompt="Ты аналитик ошибок. Отвечай JSON.",
                task_type="parse_order",
                temperature=0.2,
                json_mode=True,
            )

            analysis = json.loads(response)
            if not isinstance(analysis, dict):
                return None

            failure = self.store_failure(
                content=analysis.get("what_went_wrong", error),
                error_context=analysis.get("root_cause", context),
                correction=analysis.get("correction", ""),
                severity=analysis.get("severity", "medium"),
                tags=analysis.get("tags", []) + ["auto_analyzed"],
                chat_id=chat_id,
            )

            # Сохраняем урок как отдельное знание
            lesson = analysis.get("lesson", "")
            if lesson:
                self.store_fact(
                    content=f"УРОК: {lesson}",
                    importance=0.8,
                    confidence=0.85,
                    tags=["lesson", "failure_learning"],
                    source="failure_analysis",
                    chat_id=chat_id,
                )

            return failure

        except Exception as e:
            logger.warning(f"Ошибка анализа failure: {e}")
            # Fallback: сохраняем без LLM-анализа
            return self.store_failure(
                content=error[:200],
                error_context=context[:200],
                correction="",
                severity="medium",
                chat_id=chat_id,
            )

    # ─── History Consolidation ───────────────────────────────────────────

    async def consolidate_history(
        self,
        history: list[dict[str, str]],
        llm_engine=None,
    ) -> str:
        """Сжать историю + извлечь факты."""
        if not llm_engine:
            from pds_ultimate.core.llm_engine import llm_engine as default_engine
            llm_engine = default_engine

        dialogue = "\n".join(
            f"{msg['role']}: {msg['content']}" for msg in history
        )

        try:
            await self.extract_and_store_facts(dialogue, llm_engine)

            consolidation_prompt = (
                "Сожми диалог в краткое саммари.\n"
                "Формат:\nСАММАРИ: [2-3 предложения]\n"
                "ФАКТЫ: [ключевые через |]\n"
                "РЕШЕНИЯ: [принятые решения через |]"
            )

            summary = await llm_engine.chat(
                message=dialogue,
                system_prompt=consolidation_prompt,
                task_type="summarize",
                temperature=0.3,
            )
            return summary
        except Exception as e:
            logger.warning(f"Ошибка сжатия: {e}")
            return f"[История из {len(history)} сообщений]"

    # ─── Internal ────────────────────────────────────────────────────────

    def _rebuild_index_if_needed(self) -> None:
        """Перестроить индекс если нужно."""
        if self._index_dirty:
            active = [m for m in self._memories if m.is_active]
            self._index.update_index(active)
            self._index_dirty = False

    def _enforce_limits(self) -> None:
        """Удалить наименее важные если лимит превышен."""
        if len(self._memories) <= self.MAX_MEMORIES:
            return

        # Сортируем по effective importance
        self._memories.sort(key=lambda m: m.effective_importance())
        excess = len(self._memories) - self.MAX_MEMORIES
        removed = self._memories[:excess]
        self._memories = self._memories[excess:]

        for r in removed:
            r.is_active = False

        self._index_dirty = True
        logger.debug(f"Memory limit: удалено {len(removed)} записей")

    # ─── Stats ───────────────────────────────────────────────────────────

    @property
    def total_count(self) -> int:
        """Общее количество активных записей."""
        return sum(1 for m in self._memories if m.is_active)

    def get_stats(self) -> dict:
        """Расширенная статистика памяти."""
        active = [m for m in self._memories if m.is_active]
        type_counts: dict[str, int] = {}
        total_confidence = 0.0
        total_effective = 0.0
        failures_count = 0

        for m in active:
            type_counts[m.memory_type] = type_counts.get(m.memory_type, 0) + 1
            total_confidence += m.confidence
            total_effective += m.effective_importance()
            if m.memory_type == MemoryType.FAILURE:
                failures_count += 1

        n = max(1, len(active))
        return {
            "total": len(active),
            "total_with_inactive": len(self._memories),
            "by_type": type_counts,
            "avg_importance": sum(m.importance for m in active) / n,
            "avg_confidence": total_confidence / n,
            "avg_effective_importance": total_effective / n,
            "failures_stored": failures_count,
            "working_memories": len(self._working),
            "index_dirty": self._index_dirty,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# BACKWARD COMPATIBILITY WRAPPER
# ═══════════════════════════════════════════════════════════════════════════════

# Алиасы для совместимости со старым кодом
MemoryEntry = AdvancedMemoryEntry
WorkingMemory = AdvancedWorkingMemory
MemoryManager = AdvancedMemoryManager

# ─── Глобальный экземпляр ────────────────────────────────────────────────────

advanced_memory_manager = AdvancedMemoryManager()
