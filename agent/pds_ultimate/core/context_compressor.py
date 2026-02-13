"""
PDS-Ultimate Context Compressor (Part 10 — Item 9)
====================================================
Автоматическое сжатие и суммаризация контекста.

Проблема: контекст растёт → скорость и точность падают.
Решение: рекурсивная суммаризация + умное сжатие.

Компоненты:
1. TextSummarizer — экстрактивная суммаризация (ключевые предложения)
2. ContextWindow — скользящее окно контекста с авто-сжатием
3. ConversationCompressor — сжатие диалога (удаление повторов)
4. RecursiveSummarizer — рекурсивное сжатие длинных текстов
5. ContextCompressorV2 — фасад
"""

from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass, field

# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class CompressedText:
    """Результат сжатия текста."""
    original_length: int
    compressed_length: int
    text: str
    method: str = "extractive"
    key_terms: list[str] = field(default_factory=list)

    @property
    def compression_ratio(self) -> float:
        if self.original_length == 0:
            return 1.0
        return self.compressed_length / self.original_length

    @property
    def savings_pct(self) -> float:
        return (1 - self.compression_ratio) * 100

    def to_dict(self) -> dict:
        return {
            "compressed_text": self.text,
            "original_chars": self.original_length,
            "compressed_chars": self.compressed_length,
            "ratio": round(self.compression_ratio, 3),
            "savings_pct": round(self.savings_pct, 1),
            "method": self.method,
            "key_terms": self.key_terms[:10],
        }


@dataclass
class ContextEntry:
    """Запись в окне контекста."""
    id: str
    content: str
    role: str = "system"  # system, user, assistant
    importance: float = 0.5  # 0-1
    timestamp: float = field(default_factory=time.time)
    compressed: bool = False

    @property
    def char_count(self) -> int:
        return len(self.content)


@dataclass
class ConversationTurn:
    """Реплика в диалоге."""
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


# ═══════════════════════════════════════════════════════════════════════════════
# 1. TEXT SUMMARIZER — Экстрактивная суммаризация
# ═══════════════════════════════════════════════════════════════════════════════


class TextSummarizer:
    """
    Экстрактивная суммаризация: выбирает наиболее важные предложения.

    Алгоритм:
    1. Разбиваем на предложения
    2. Скорим каждое предложение (TF, позиция, длина)
    3. Берём top-K предложений
    """

    STOP_WORDS_RU = frozenset({
        "и", "в", "на", "с", "по", "для", "из", "к", "о", "а", "но",
        "что", "это", "как", "не", "да", "от", "до", "за", "при",
        "так", "же", "уже", "ещё", "бы", "ли", "ни", "то",
    })

    SENTENCE_SPLIT = re.compile(r'(?<=[.!?])\s+')

    def summarize(
        self,
        text: str,
        ratio: float = 0.3,
        min_sentences: int = 1,
        max_sentences: int = 10,
    ) -> CompressedText:
        """
        Суммаризировать текст.

        Args:
            text: исходный текст
            ratio: доля предложений для сохранения (0-1)
            min_sentences: минимум предложений
            max_sentences: максимум предложений
        """
        if not text or len(text) < 50:
            return CompressedText(
                original_length=len(text),
                compressed_length=len(text),
                text=text,
            )

        sentences = self._split_sentences(text)
        if len(sentences) <= min_sentences:
            return CompressedText(
                original_length=len(text),
                compressed_length=len(text),
                text=text,
            )

        word_freq = self._word_frequencies(text)
        scores = self._score_sentences(sentences, word_freq)

        n_select = max(
            min_sentences,
            min(max_sentences, int(len(sentences) * ratio)),
        )

        ranked = sorted(
            enumerate(scores), key=lambda x: x[1], reverse=True
        )
        selected_indices = sorted([i for i, _ in ranked[:n_select]])
        selected = [sentences[i] for i in selected_indices]

        compressed = " ".join(selected)
        key_terms = [
            w for w, _ in Counter(word_freq).most_common(10) if len(w) > 2
        ]

        return CompressedText(
            original_length=len(text),
            compressed_length=len(compressed),
            text=compressed,
            method="extractive",
            key_terms=key_terms,
        )

    def _split_sentences(self, text: str) -> list[str]:
        """Разбить на предложения."""
        sentences = self.SENTENCE_SPLIT.split(text.strip())
        return [s.strip() for s in sentences if s.strip()]

    def _word_frequencies(self, text: str) -> dict[str, float]:
        """Подсчитать частоты слов (без стоп-слов)."""
        tokens = re.findall(r'[а-яёa-z0-9]+', text.lower())
        tokens = [
            t for t in tokens if t not in self.STOP_WORDS_RU and len(t) > 1]
        counts = Counter(tokens)
        if not counts:
            return {}
        max_freq = max(counts.values())
        return {w: c / max_freq for w, c in counts.items()}

    def _score_sentences(
        self,
        sentences: list[str],
        word_freq: dict[str, float],
    ) -> list[float]:
        """Оценить предложения."""
        scores = []
        n = len(sentences)
        for i, sent in enumerate(sentences):
            tokens = re.findall(r'[а-яёa-z0-9]+', sent.lower())
            # TF score
            tf = sum(word_freq.get(t, 0) for t in tokens)
            tf = tf / max(len(tokens), 1)
            # Position bonus (первые и последние предложения важнее)
            pos = 0.0
            if i == 0 or i == n - 1:
                pos = 0.3
            elif i < n * 0.2:
                pos = 0.15
            # Length penalty (слишком короткие/длинные)
            length_penalty = 0.0
            if len(tokens) < 4:
                length_penalty = -0.2
            elif len(tokens) > 50:
                length_penalty = -0.1
            scores.append(tf + pos + length_penalty)
        return scores


# ═══════════════════════════════════════════════════════════════════════════════
# 2. CONTEXT WINDOW — Скользящее окно контекста
# ═══════════════════════════════════════════════════════════════════════════════


class ContextWindow:
    """
    Скользящее окно контекста с авто-сжатием.

    Когда контекст превышает max_chars, старейшие записи сжимаются.
    """

    def __init__(self, max_chars: int = 10000, compress_ratio: float = 0.3):
        self._entries: list[ContextEntry] = []
        self._max_chars = max_chars
        self._compress_ratio = compress_ratio
        self._summarizer = TextSummarizer()
        self._entry_counter = 0

    def add(
        self,
        content: str,
        role: str = "system",
        importance: float = 0.5,
    ) -> str:
        """Добавить запись в контекст."""
        self._entry_counter += 1
        entry_id = f"ctx_{self._entry_counter}"
        entry = ContextEntry(
            id=entry_id,
            content=content,
            role=role,
            importance=importance,
        )
        self._entries.append(entry)
        self._auto_compress()
        return entry_id

    def get_context(self) -> str:
        """Получить весь контекст."""
        return "\n".join(e.content for e in self._entries)

    def get_entries(self) -> list[ContextEntry]:
        return list(self._entries)

    @property
    def total_chars(self) -> int:
        return sum(e.char_count for e in self._entries)

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def _auto_compress(self) -> None:
        """Автоматическое сжатие при переполнении."""
        while self.total_chars > self._max_chars and len(self._entries) > 1:
            # Сжимаем первую (самую старую) не-сжатую запись с низким приоритетом
            target = None
            for e in self._entries:
                if not e.compressed and e.importance < 0.8:
                    target = e
                    break
            if target is None:
                # Все сжаты — удаляем самую старую
                self._entries.pop(0)
                continue

            result = self._summarizer.summarize(
                target.content,
                ratio=self._compress_ratio,
            )
            target.content = result.text
            target.compressed = True

    def clear(self) -> None:
        self._entries.clear()

    def get_stats(self) -> dict:
        compressed_count = sum(1 for e in self._entries if e.compressed)
        return {
            "entries": self.entry_count,
            "total_chars": self.total_chars,
            "max_chars": self._max_chars,
            "compressed_entries": compressed_count,
            "utilization_pct": round(
                self.total_chars / self._max_chars * 100, 1
            ) if self._max_chars > 0 else 0,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. CONVERSATION COMPRESSOR — Сжатие диалога
# ═══════════════════════════════════════════════════════════════════════════════


class ConversationCompressor:
    """
    Сжатие истории диалога.

    Стратегии:
    - Удаление повторных сообщений
    - Объединение коротких сообщений
    - Суммаризация старых сообщений
    """

    def __init__(self, max_turns: int = 50, summary_threshold: int = 20):
        self._max_turns = max_turns
        self._summary_threshold = summary_threshold
        self._summarizer = TextSummarizer()

    def compress(
        self,
        turns: list[ConversationTurn],
    ) -> list[ConversationTurn]:
        """Сжать диалог."""
        if len(turns) <= self._summary_threshold:
            return turns

        # Стратегия: суммаризировать старые сообщения, оставить последние
        keep_recent = self._summary_threshold // 2
        old_turns = turns[:-keep_recent]
        recent_turns = turns[-keep_recent:]

        # Суммаризировать старые
        old_text = "\n".join(
            f"{t.role}: {t.content}" for t in old_turns
        )
        summary = self._summarizer.summarize(old_text, ratio=0.2)

        summary_turn = ConversationTurn(
            role="system",
            content=f"[Сводка предыдущего диалога]: {summary.text}",
        )

        return [summary_turn] + recent_turns

    def remove_duplicates(
        self,
        turns: list[ConversationTurn],
    ) -> list[ConversationTurn]:
        """Удалить дублирующиеся сообщения."""
        seen: set[str] = set()
        unique: list[ConversationTurn] = []
        for turn in turns:
            key = f"{turn.role}:{turn.content[:100]}"
            if key not in seen:
                seen.add(key)
                unique.append(turn)
        return unique

    def merge_short(
        self,
        turns: list[ConversationTurn],
        min_length: int = 20,
    ) -> list[ConversationTurn]:
        """Объединить короткие последовательные сообщения одного role."""
        if not turns:
            return []
        merged: list[ConversationTurn] = [turns[0]]
        for turn in turns[1:]:
            last = merged[-1]
            if (
                turn.role == last.role
                and len(last.content) < min_length
            ):
                last.content = f"{last.content} {turn.content}"
            else:
                merged.append(turn)
        return merged

    def get_stats(self) -> dict:
        return {
            "max_turns": self._max_turns,
            "summary_threshold": self._summary_threshold,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. RECURSIVE SUMMARIZER — Рекурсивная суммаризация
# ═══════════════════════════════════════════════════════════════════════════════


class RecursiveSummarizer:
    """
    Рекурсивная суммаризация: сжимает длинный текст в несколько проходов.

    Алгоритм:
    1. Разбиваем на чанки
    2. Суммаризируем каждый чанк
    3. Если результат всё ещё большой — повторяем
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        target_ratio: float = 0.2,
        max_depth: int = 3,
    ):
        self._chunk_size = chunk_size
        self._target_ratio = target_ratio
        self._max_depth = max_depth
        self._summarizer = TextSummarizer()

    def summarize(
        self,
        text: str,
        target_length: int | None = None,
    ) -> CompressedText:
        """Рекурсивно суммаризировать."""
        if target_length is None:
            target_length = int(len(text) * self._target_ratio)

        original_len = len(text)
        current = text

        for depth in range(self._max_depth):
            if len(current) <= target_length:
                break

            chunks = self._chunk_text(current)
            summaries = []
            for chunk in chunks:
                result = self._summarizer.summarize(chunk, ratio=0.4)
                summaries.append(result.text)
            current = " ".join(summaries)

        key_terms = self._summarizer._word_frequencies(text)
        top_terms = sorted(key_terms, key=key_terms.get, reverse=True)[:10]

        return CompressedText(
            original_length=original_len,
            compressed_length=len(current),
            text=current,
            method="recursive",
            key_terms=top_terms,
        )

    def _chunk_text(self, text: str) -> list[str]:
        """Разбить на чанки."""
        chunks = []
        start = 0
        while start < len(text):
            end = start + self._chunk_size
            if end < len(text):
                break_point = text.rfind(". ", start, end)
                if break_point > start:
                    end = break_point + 1
            chunks.append(text[start:end].strip())
            start = end
        return [c for c in chunks if c]


# ═══════════════════════════════════════════════════════════════════════════════
# FACADE: ContextCompressorV2
# ═══════════════════════════════════════════════════════════════════════════════


class ContextCompressorV2:
    """
    Фасад для сжатия контекста.

    Использование:
        compressor = ContextCompressorV2()

        # Суммаризировать текст
        result = compressor.summarize("длинный текст...")

        # Добавить в окно контекста
        compressor.add_context("новая информация")
        ctx = compressor.get_context()

        # Сжать диалог
        turns = [ConversationTurn("user", "hi"), ...]
        compressed = compressor.compress_conversation(turns)
    """

    def __init__(self, max_context_chars: int = 10000):
        self.summarizer = TextSummarizer()
        self.context_window = ContextWindow(max_chars=max_context_chars)
        self.conversation_compressor = ConversationCompressor()
        self.recursive_summarizer = RecursiveSummarizer()

    def summarize(
        self,
        text: str,
        ratio: float = 0.3,
    ) -> CompressedText:
        """Суммаризировать текст."""
        return self.summarizer.summarize(text, ratio=ratio)

    def summarize_recursive(
        self,
        text: str,
        target_length: int | None = None,
    ) -> CompressedText:
        """Рекурсивная суммаризация для очень длинных текстов."""
        return self.recursive_summarizer.summarize(text, target_length)

    def add_context(
        self,
        content: str,
        role: str = "system",
        importance: float = 0.5,
    ) -> str:
        """Добавить в окно контекста."""
        return self.context_window.add(content, role, importance)

    def get_context(self) -> str:
        """Получить текущий контекст."""
        return self.context_window.get_context()

    def compress_conversation(
        self,
        turns: list[ConversationTurn],
    ) -> list[ConversationTurn]:
        """Сжать диалог."""
        turns = self.conversation_compressor.remove_duplicates(turns)
        turns = self.conversation_compressor.merge_short(turns)
        turns = self.conversation_compressor.compress(turns)
        return turns

    def get_stats(self) -> dict:
        return {
            "context_window": self.context_window.get_stats(),
            "conversation": self.conversation_compressor.get_stats(),
        }


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

context_compressor = ContextCompressorV2()
