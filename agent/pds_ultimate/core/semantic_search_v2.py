"""
PDS-Ultimate Semantic Search v2 (Part 10 — Item 5)
=====================================================
Поиск по смыслу: прошлые ответы, базы данных, документы.

Расширяет semantic_engine.py:
1. KnowledgeBase — база знаний с категоризацией
2. DocumentStore — хранение и поиск документов по смыслу
3. ContextualSearch — поиск с учётом контекста диалога
4. EmbeddingPruner — удаление устаревших векторов (бонус)
5. SemanticCache — кэш семантически похожих запросов

Без внешних ML-зависимостей — используем расширенный BoW + char n-grams + IDF
(semantic_engine.py), но с продвинутыми стратегиями поиска.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum

# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS & DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class KnowledgeCategory(str, Enum):
    """Категория знания."""
    ANSWER = "answer"           # Прошлые ответы агента
    DOCUMENT = "document"       # Загруженные документы
    CONVERSATION = "conversation"  # Контекст диалогов
    FACT = "fact"              # Проверенные факты
    SKILL = "skill"            # Навыки / how-to
    BUSINESS = "business"      # Бизнес-данные
    GENERAL = "general"


class FreshnessLevel(str, Enum):
    """Свежесть знания."""
    FRESH = "fresh"       # < 1 дня
    RECENT = "recent"     # < 7 дней
    AGING = "aging"       # < 30 дней
    STALE = "stale"       # > 30 дней
    EXPIRED = "expired"   # > 90 дней


@dataclass
class KnowledgeItem:
    """Единица знания в базе."""
    id: str = ""
    content: str = ""
    category: KnowledgeCategory = KnowledgeCategory.GENERAL
    source: str = ""            # Откуда знание
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.8     # Уверенность в знании (0-1)
    access_count: int = 0
    last_accessed: float = 0.0
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0     # 0 = не истекает
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = hashlib.md5(
                f"{self.content[:100]}:{self.created_at}".encode()
            ).hexdigest()[:12]

    @property
    def age_days(self) -> float:
        return (time.time() - self.created_at) / 86400

    @property
    def freshness(self) -> FreshnessLevel:
        days = self.age_days
        if days < 1:
            return FreshnessLevel.FRESH
        elif days < 7:
            return FreshnessLevel.RECENT
        elif days < 30:
            return FreshnessLevel.AGING
        elif days < 90:
            return FreshnessLevel.STALE
        return FreshnessLevel.EXPIRED

    @property
    def is_expired(self) -> bool:
        if self.expires_at > 0:
            return time.time() > self.expires_at
        return False

    @property
    def relevance_score(self) -> float:
        """Оценка релевантности с учётом свежести и доступов."""
        freshness_multiplier = {
            FreshnessLevel.FRESH: 1.0,
            FreshnessLevel.RECENT: 0.95,
            FreshnessLevel.AGING: 0.8,
            FreshnessLevel.STALE: 0.6,
            FreshnessLevel.EXPIRED: 0.3,
        }
        base = self.confidence * freshness_multiplier[self.freshness]
        access_boost = min(0.1, self.access_count * 0.005)
        return min(1.0, base + access_boost)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content[:200],
            "category": self.category.value,
            "source": self.source,
            "tags": self.tags,
            "confidence": round(self.confidence, 2),
            "freshness": self.freshness.value,
            "relevance": round(self.relevance_score, 3),
            "age_days": round(self.age_days, 1),
            "access_count": self.access_count,
        }


@dataclass
class SearchQuery:
    """Структурированный поисковый запрос."""
    text: str
    category: KnowledgeCategory | None = None
    tags: list[str] = field(default_factory=list)
    min_confidence: float = 0.0
    min_freshness: FreshnessLevel | None = None
    max_results: int = 10
    context: str = ""           # Контекст диалога для boosting

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "category": self.category.value if self.category else None,
            "tags": self.tags,
            "min_confidence": self.min_confidence,
            "max_results": self.max_results,
        }


@dataclass
class SemanticSearchResult:
    """Результат семантического поиска."""
    item: KnowledgeItem
    score: float               # Cosine similarity
    boosted_score: float = 0.0  # После boosting
    match_reason: str = ""

    @property
    def final_score(self) -> float:
        return self.boosted_score if self.boosted_score > 0 else self.score

    def to_dict(self) -> dict:
        return {
            "item": self.item.to_dict(),
            "score": round(self.score, 4),
            "boosted_score": round(self.boosted_score, 4),
            "match_reason": self.match_reason,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. KNOWLEDGE BASE — База знаний
# ═══════════════════════════════════════════════════════════════════════════════


class KnowledgeBase:
    """
    База знаний с категоризацией и управлением жизненным циклом.

    Хранит:
    - Прошлые ответы агента
    - Загруженные документы
    - Факты из исследований
    - Бизнес-данные
    """

    def __init__(self, max_items: int = 10000):
        self._items: dict[str, KnowledgeItem] = {}
        self._by_category: defaultdict[str, list[str]] = defaultdict(list)
        self._by_tag: defaultdict[str, set[str]] = defaultdict(set)
        self._max_items = max_items

    def add(
        self,
        content: str,
        category: KnowledgeCategory | str = KnowledgeCategory.GENERAL,
        source: str = "",
        tags: list[str] | None = None,
        confidence: float = 0.8,
        expires_hours: float = 0,
        metadata: dict | None = None,
    ) -> KnowledgeItem:
        """Добавить знание в базу."""
        if isinstance(category, str):
            try:
                category = KnowledgeCategory(category)
            except ValueError:
                category = KnowledgeCategory.GENERAL

        item = KnowledgeItem(
            content=content,
            category=category,
            source=source,
            tags=tags or [],
            confidence=max(0.0, min(1.0, confidence)),
            expires_at=time.time() + expires_hours * 3600 if expires_hours > 0 else 0,
            metadata=metadata or {},
        )

        if len(self._items) >= self._max_items:
            self._evict_least_relevant()

        self._items[item.id] = item
        self._by_category[item.category.value].append(item.id)
        for tag in item.tags:
            self._by_tag[tag.lower()].add(item.id)

        return item

    def get(self, item_id: str) -> KnowledgeItem | None:
        """Получить знание по ID."""
        item = self._items.get(item_id)
        if item:
            item.access_count += 1
            item.last_accessed = time.time()
        return item

    def remove(self, item_id: str) -> bool:
        """Удалить знание."""
        item = self._items.pop(item_id, None)
        if not item:
            return False
        cat_list = self._by_category.get(item.category.value, [])
        if item_id in cat_list:
            cat_list.remove(item_id)
        for tag in item.tags:
            self._by_tag.get(tag.lower(), set()).discard(item_id)
        return True

    def find_by_category(
        self,
        category: KnowledgeCategory | str,
    ) -> list[KnowledgeItem]:
        """Найти знания по категории."""
        if isinstance(category, KnowledgeCategory):
            category = category.value
        ids = self._by_category.get(category, [])
        return [self._items[i] for i in ids if i in self._items]

    def find_by_tags(self, tags: list[str]) -> list[KnowledgeItem]:
        """Найти знания по тегам (OR)."""
        ids: set[str] = set()
        for tag in tags:
            ids |= self._by_tag.get(tag.lower(), set())
        return [self._items[i] for i in ids if i in self._items]

    def get_expired(self) -> list[KnowledgeItem]:
        """Получить истёкшие знания."""
        return [item for item in self._items.values() if item.is_expired]

    def cleanup_expired(self) -> int:
        """Удалить истёкшие знания."""
        expired = self.get_expired()
        for item in expired:
            self.remove(item.id)
        return len(expired)

    def _evict_least_relevant(self) -> None:
        """Удалить наименее релевантное знание."""
        if not self._items:
            return
        worst = min(
            self._items.values(),
            key=lambda i: i.relevance_score,
        )
        self.remove(worst.id)

    @property
    def size(self) -> int:
        return len(self._items)

    def get_stats(self) -> dict:
        """Статистика базы знаний."""
        by_cat: dict[str, int] = {}
        for cat, ids in self._by_category.items():
            by_cat[cat] = len([i for i in ids if i in self._items])
        freshness: dict[str, int] = Counter()
        for item in self._items.values():
            freshness[item.freshness.value] += 1
        return {
            "total": self.size,
            "max_items": self._max_items,
            "by_category": by_cat,
            "by_freshness": dict(freshness),
            "expired": len(self.get_expired()),
            "tags_count": len(self._by_tag),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. DOCUMENT STORE — Поиск документов по смыслу
# ═══════════════════════════════════════════════════════════════════════════════


class DocumentStore:
    """
    Хранение и семантический поиск документов.

    Использует SemanticSearchEngine для embeddings + search.
    Добавляет: chunking, metadata filtering, relevance boosting.
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        from pds_ultimate.core.semantic_engine import SemanticSearchEngine
        self._engine = SemanticSearchEngine()
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._documents: dict[str, dict] = {}  # doc_id → metadata
        self._chunk_map: dict[str, str] = {}   # chunk_id → doc_id

    def add_document(
        self,
        doc_id: str,
        text: str,
        title: str = "",
        source: str = "",
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ) -> int:
        """
        Добавить документ с автоматическим chunking.

        Returns: количество чанков
        """
        chunks = self._chunk_text(text)
        meta = metadata or {}
        meta.update({"title": title, "source": source})
        self._documents[doc_id] = {
            "title": title,
            "source": source,
            "chunks": len(chunks),
            "tags": tags or [],
            "added_at": time.time(),
        }

        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}__chunk_{i}"
            self._chunk_map[chunk_id] = doc_id
            chunk_meta = {**meta, "chunk_index": i,
                          "total_chunks": len(chunks)}
            self._engine.add_document(
                doc_id=chunk_id,
                text=chunk,
                tags=tags,
                metadata=chunk_meta,
            )

        if len(chunks) > 3:
            self._engine.rebuild_index()

        return len(chunks)

    def remove_document(self, doc_id: str) -> bool:
        """Удалить документ и все его чанки."""
        if doc_id not in self._documents:
            return False
        chunks_to_remove = [
            cid for cid, did in self._chunk_map.items() if did == doc_id
        ]
        for cid in chunks_to_remove:
            self._engine.remove_document(cid)
            del self._chunk_map[cid]
        del self._documents[doc_id]
        return True

    def search(
        self,
        query: str,
        tags: list[str] | None = None,
        top_k: int = 5,
        min_score: float = 0.05,
    ) -> list[dict]:
        """
        Семантический поиск по документам.

        Returns: [{doc_id, chunk_text, score, title, source}]
        """
        results = self._engine.search(
            query, tags=tags, top_k=top_k * 2, min_score=min_score,
        )

        seen_docs: set[str] = set()
        output: list[dict] = []
        for r in results:
            parent_doc = self._chunk_map.get(r.doc_id, r.doc_id)
            if parent_doc in seen_docs:
                continue
            seen_docs.add(parent_doc)
            doc_info = self._documents.get(parent_doc, {})
            output.append({
                "doc_id": parent_doc,
                "chunk_text": r.content[:500],
                "score": round(r.score, 4),
                "title": doc_info.get("title", ""),
                "source": doc_info.get("source", ""),
            })
            if len(output) >= top_k:
                break

        return output

    def _chunk_text(self, text: str) -> list[str]:
        """Разбить текст на чанки с перекрытием."""
        if len(text) <= self._chunk_size:
            return [text]

        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + self._chunk_size
            if end < len(text):
                break_point = text.rfind('. ', start, end)
                if break_point > start + self._chunk_size // 2:
                    end = break_point + 1
            chunks.append(text[start:end].strip())
            start = end - self._chunk_overlap
        return [c for c in chunks if c]

    @property
    def document_count(self) -> int:
        return len(self._documents)

    @property
    def chunk_count(self) -> int:
        return len(self._chunk_map)

    def get_stats(self) -> dict:
        return {
            "documents": self.document_count,
            "chunks": self.chunk_count,
            "engine": self._engine.get_stats(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. CONTEXTUAL SEARCH — Поиск с контекстом
# ═══════════════════════════════════════════════════════════════════════════════


class ContextualSearch:
    """
    Поиск с учётом контекста диалога.

    Расширяет запрос терминами из контекста,
    применяет boosting по свежести и категории.
    """

    # Boosting по категории знания
    CATEGORY_BOOST: dict[str, float] = {
        "answer": 1.2,
        "fact": 1.3,
        "skill": 1.1,
        "business": 1.15,
        "document": 1.0,
        "conversation": 0.9,
        "general": 0.8,
    }

    # Boosting по свежести
    FRESHNESS_BOOST: dict[str, float] = {
        "fresh": 1.3,
        "recent": 1.15,
        "aging": 1.0,
        "stale": 0.8,
        "expired": 0.5,
    }

    def __init__(self, knowledge_base: KnowledgeBase):
        from pds_ultimate.core.semantic_engine import SemanticSearchEngine
        self._kb = knowledge_base
        self._engine = SemanticSearchEngine()
        self._synced = False

    def sync_from_kb(self) -> int:
        """Синхронизировать индекс с базой знаний."""
        self._engine.index.clear()
        count = 0
        for item in self._kb._items.values():
            if not item.is_expired:
                self._engine.add_document(
                    doc_id=item.id,
                    text=item.content,
                    tags=item.tags + [item.category.value],
                    metadata={"category": item.category.value,
                              "confidence": item.confidence},
                )
                count += 1
        if count > 5:
            self._engine.rebuild_index()
        self._synced = True
        return count

    def search(
        self,
        query: SearchQuery,
    ) -> list[SemanticSearchResult]:
        """
        Контекстуальный семантический поиск.

        1. Расширяет запрос контекстом
        2. Ищет по семантике
        3. Применяет boosting (категория, свежесть, confidence)
        4. Фильтрует по min_confidence и freshness
        """
        if not self._synced:
            self.sync_from_kb()

        expanded_query = query.text
        if query.context:
            context_terms = self._extract_key_terms(query.context, max_terms=5)
            if context_terms:
                expanded_query = f"{query.text} {' '.join(context_terms)}"

        raw_results = self._engine.search(
            expanded_query,
            tags=query.tags or None,
            top_k=query.max_results * 3,
            min_score=0.01,
        )

        results: list[SemanticSearchResult] = []
        for r in raw_results:
            item = self._kb.get(r.doc_id)
            if not item:
                continue

            if item.confidence < query.min_confidence:
                continue
            if query.category and item.category != query.category:
                continue
            if query.min_freshness:
                freshness_order = list(FreshnessLevel)
                if freshness_order.index(item.freshness) > freshness_order.index(query.min_freshness):
                    continue

            cat_boost = self.CATEGORY_BOOST.get(item.category.value, 1.0)
            fresh_boost = self.FRESHNESS_BOOST.get(item.freshness.value, 1.0)
            conf_boost = 0.8 + item.confidence * 0.4

            boosted = r.score * cat_boost * fresh_boost * conf_boost

            reasons = []
            if cat_boost > 1.0:
                reasons.append(f"category:{item.category.value}")
            if fresh_boost > 1.0:
                reasons.append(f"fresh:{item.freshness.value}")

            results.append(SemanticSearchResult(
                item=item,
                score=r.score,
                boosted_score=round(boosted, 4),
                match_reason=", ".join(reasons) if reasons else "semantic",
            ))

        results.sort(key=lambda x: x.final_score, reverse=True)
        return results[:query.max_results]

    @staticmethod
    def _extract_key_terms(text: str, max_terms: int = 5) -> list[str]:
        """Извлечь ключевые термины из контекста."""
        from pds_ultimate.core.semantic_engine import STOP_WORDS
        tokens = re.findall(r'[а-яёa-z0-9]{3,}', text.lower())
        filtered = [t for t in tokens if t not in STOP_WORDS]
        counts = Counter(filtered)
        return [w for w, _ in counts.most_common(max_terms)]


# ═══════════════════════════════════════════════════════════════════════════════
# 4. EMBEDDING PRUNER — Удаление устаревших векторов
# ═══════════════════════════════════════════════════════════════════════════════


class EmbeddingPruner:
    """
    Удаление устаревших/низкокачественных векторов.

    Стратегии:
    - По возрасту (> N дней)
    - По access_count (не использовались)
    - По confidence (низкая уверенность)
    - По дубликатам (семантически похожие)
    """

    def __init__(self, knowledge_base: KnowledgeBase):
        self._kb = knowledge_base

    def prune_expired(self) -> int:
        """Удалить истёкшие знания."""
        return self._kb.cleanup_expired()

    def prune_stale(self, max_age_days: float = 90) -> int:
        """Удалить устаревшие знания (> max_age_days)."""
        cutoff = time.time() - max_age_days * 86400
        to_remove = [
            item.id for item in self._kb._items.values()
            if item.created_at < cutoff and item.access_count < 3
        ]
        for item_id in to_remove:
            self._kb.remove(item_id)
        return len(to_remove)

    def prune_low_confidence(self, min_confidence: float = 0.3) -> int:
        """Удалить знания с низкой уверенностью."""
        to_remove = [
            item.id for item in self._kb._items.values()
            if item.confidence < min_confidence
        ]
        for item_id in to_remove:
            self._kb.remove(item_id)
        return len(to_remove)

    def prune_unused(self, min_accesses: int = 0, older_than_days: float = 30) -> int:
        """Удалить неиспользуемые знания."""
        cutoff = time.time() - older_than_days * 86400
        to_remove = [
            item.id for item in self._kb._items.values()
            if item.access_count <= min_accesses and item.created_at < cutoff
        ]
        for item_id in to_remove:
            self._kb.remove(item_id)
        return len(to_remove)

    def prune_all(
        self,
        max_age_days: float = 90,
        min_confidence: float = 0.3,
    ) -> dict:
        """Комплексная очистка."""
        expired = self.prune_expired()
        stale = self.prune_stale(max_age_days)
        low_conf = self.prune_low_confidence(min_confidence)
        return {
            "expired": expired,
            "stale": stale,
            "low_confidence": low_conf,
            "total_pruned": expired + stale + low_conf,
        }

    def get_stats(self) -> dict:
        """Статистика для pruning."""
        items = list(self._kb._items.values())
        if not items:
            return {"total": 0, "prunable": 0}
        expired = sum(1 for i in items if i.is_expired)
        stale = sum(1 for i in items if i.freshness == FreshnessLevel.STALE)
        low_conf = sum(1 for i in items if i.confidence < 0.3)
        unused = sum(1 for i in items if i.access_count ==
                     0 and i.age_days > 30)
        return {
            "total": len(items),
            "expired": expired,
            "stale": stale,
            "low_confidence": low_conf,
            "unused": unused,
            "prunable": expired + low_conf,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. SEMANTIC CACHE — Кэш семантически похожих запросов
# ═══════════════════════════════════════════════════════════════════════════════


class SemanticCache:
    """
    Кэш, который находит ответ если запрос семантически похож
    на ранее обработанный.

    Экономит LLM-вызовы, ускоряет ответы.
    """

    def __init__(self, max_entries: int = 500, similarity_threshold: float = 0.75):
        from pds_ultimate.core.semantic_engine import SemanticSearchEngine
        self._engine = SemanticSearchEngine()
        # doc_id → {query, response, ...}
        self._responses: dict[str, dict] = {}
        self._max_entries = max_entries
        self._threshold = similarity_threshold
        self._hits = 0
        self._misses = 0

    def get(self, query: str) -> dict | None:
        """
        Попытка найти кэшированный ответ.

        Returns: {query, response, score} или None
        """
        if not self._responses:
            self._misses += 1
            return None

        results = self._engine.search(
            query, top_k=1, min_score=self._threshold)
        if results:
            doc_id = results[0].doc_id
            cached = self._responses.get(doc_id)
            if cached:
                cached["access_count"] = cached.get("access_count", 0) + 1
                cached["last_accessed"] = time.time()
                self._hits += 1
                return {
                    "query": cached["query"],
                    "response": cached["response"],
                    "score": results[0].score,
                    "original_query": cached["query"],
                }

        self._misses += 1
        return None

    def put(self, query: str, response: str, metadata: dict | None = None) -> str:
        """Кэшировать ответ."""
        if len(self._responses) >= self._max_entries:
            self._evict_oldest()

        doc_id = self._engine.add_document(text=query, metadata=metadata)
        self._responses[doc_id] = {
            "query": query,
            "response": response,
            "created_at": time.time(),
            "access_count": 0,
            "metadata": metadata or {},
        }
        return doc_id

    def invalidate(self, doc_id: str) -> bool:
        """Инвалидировать запись."""
        if doc_id in self._responses:
            self._engine.remove_document(doc_id)
            del self._responses[doc_id]
            return True
        return False

    def clear(self) -> None:
        """Очистить кэш."""
        self._engine.index.clear()
        self._responses.clear()

    def _evict_oldest(self) -> None:
        """Удалить самую старую запись."""
        if not self._responses:
            return
        oldest_id = min(
            self._responses,
            key=lambda k: self._responses[k].get("last_accessed",
                                                 self._responses[k]["created_at"]),
        )
        self.invalidate(oldest_id)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def get_stats(self) -> dict:
        return {
            "entries": len(self._responses),
            "max_entries": self._max_entries,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self.hit_rate, 3),
            "threshold": self._threshold,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# FACADE: SemanticSearchV2
# ═══════════════════════════════════════════════════════════════════════════════


class SemanticSearchV2:
    """
    Фасад для семантического поиска v2.

    Объединяет:
    - KnowledgeBase
    - DocumentStore
    - ContextualSearch
    - EmbeddingPruner
    - SemanticCache
    """

    def __init__(self):
        self.knowledge_base = KnowledgeBase()
        self.document_store = DocumentStore()
        self.contextual_search = ContextualSearch(self.knowledge_base)
        self.pruner = EmbeddingPruner(self.knowledge_base)
        self.cache = SemanticCache()

    def add_knowledge(
        self,
        content: str,
        category: str = "general",
        source: str = "",
        tags: list[str] | None = None,
        confidence: float = 0.8,
    ) -> KnowledgeItem:
        """Добавить знание."""
        item = self.knowledge_base.add(
            content=content,
            category=category,
            source=source,
            tags=tags,
            confidence=confidence,
        )
        self.contextual_search._synced = False
        return item

    def search_knowledge(
        self,
        query: str,
        context: str = "",
        category: str | None = None,
        max_results: int = 5,
    ) -> list[SemanticSearchResult]:
        """Поиск знаний."""
        sq = SearchQuery(
            text=query,
            context=context,
            category=KnowledgeCategory(category) if category else None,
            max_results=max_results,
        )
        return self.contextual_search.search(sq)

    def add_document(
        self,
        doc_id: str,
        text: str,
        title: str = "",
        tags: list[str] | None = None,
    ) -> int:
        """Добавить документ."""
        return self.document_store.add_document(
            doc_id=doc_id, text=text, title=title, tags=tags,
        )

    def search_documents(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """Поиск по документам."""
        return self.document_store.search(query, top_k=top_k)

    def prune(self) -> dict:
        """Очистка устаревших знаний."""
        return self.pruner.prune_all()

    def get_stats(self) -> dict:
        return {
            "knowledge_base": self.knowledge_base.get_stats(),
            "document_store": self.document_store.get_stats(),
            "cache": self.cache.get_stats(),
            "pruner": self.pruner.get_stats(),
        }


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

semantic_search_v2 = SemanticSearchV2()
