"""
PDS-Ultimate Internet Reasoning Layer v2 (Part 8)
====================================================
Продвинутый слой интернет-рассуждений.

Усиливает существующий Internet Reasoning Engine (Part 5):

1. Multi-Source Verification — минимум 2-3 независимых источника
2. Trust Scoring v2 — оценка достоверности сайтов по истории
3. Contradiction Detection — выявление расхождений между источниками
4. Staleness Detection — обнаружение устаревших данных
5. Source Credibility — понимание кому верить в интернете
6. Self-Query Expansion — агент сам уточняет запрос
7. Hypothesis Testing — параллельная проверка гипотез
8. Fact Extraction — извлечение структурированных фактов
9. Confidence Calibration — калибровка уверенности по данным
10. Context Compression — сжатие больших текстов без потери смысла
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════════
# TRUST SCORER v2 — Оценка достоверности источников
# ═══════════════════════════════════════════════════════════════════════════════


class TrustScorerV2:
    """
    Оценка достоверности источников.

    Факторы:
    - Домен (Wikipedia = высокий, random blog = низкий)
    - Возраст контента (свежий = выше)
    - Наличие ссылок/цитирований
    - Совпадение с другими источниками (consensus)
    - История взаимодействий (если раньше давал правильные данные)
    """

    # Базовые trust scores по доменам
    DOMAIN_SCORES: dict[str, float] = {
        # Высокая достоверность (0.8-1.0)
        "wikipedia.org": 0.90,
        "britannica.com": 0.92,
        "gov": 0.88,  # .gov домены
        "edu": 0.85,  # .edu домены
        "nature.com": 0.95,
        "science.org": 0.94,
        "pubmed.ncbi.nlm.nih.gov": 0.93,
        "reuters.com": 0.88,
        "bbc.com": 0.85,
        "bbc.co.uk": 0.85,
        "nytimes.com": 0.83,

        # Средняя достоверность (0.5-0.8)
        "stackoverflow.com": 0.80,
        "github.com": 0.75,
        "medium.com": 0.55,
        "quora.com": 0.50,
        "reddit.com": 0.45,

        # Низкая достоверность (0.1-0.5)
        "twitter.com": 0.35,
        "x.com": 0.35,
        "facebook.com": 0.30,
        "tiktok.com": 0.20,
    }

    # Домены-спамеры (всегда низкий trust)
    SPAM_DOMAINS = frozenset({
        "clickbait", "ads", "spam", "fake",
    })

    def __init__(self):
        self._history: dict[str, list[float]] = {}  # domain → [scores]
        self._custom_scores: dict[str, float] = {}

    def score_domain(self, url: str) -> float:
        """Оценить домен по URL."""
        domain = self._extract_domain(url)

        # Пользовательская оценка
        if domain in self._custom_scores:
            return self._custom_scores[domain]

        # По базе
        for known_domain, score in self.DOMAIN_SCORES.items():
            if known_domain in domain:
                return score

        # .gov, .edu домены
        if domain.endswith(".gov"):
            return 0.88
        if domain.endswith(".edu"):
            return 0.85

        # История
        if domain in self._history:
            scores = self._history[domain]
            if scores:
                return sum(scores) / len(scores)

        # По умолчанию
        return 0.50

    def score_content(
        self,
        text: str,
        url: str = "",
        publish_date: datetime | None = None,
    ) -> float:
        """
        Комплексная оценка контента.

        Учитывает: домен + свежесть + длину + наличие цитирований.
        """
        score = self.score_domain(url)

        # Свежесть (-0.1 за каждый год старости)
        if publish_date:
            age_days = (datetime.utcnow() - publish_date).days
            if age_days > 365 * 3:
                score *= 0.7  # Более 3 лет — снижаем
            elif age_days > 365:
                score *= 0.85
            elif age_days > 180:
                score *= 0.95

        # Длина контента (слишком короткий = подозрительно)
        if len(text) < 100:
            score *= 0.7
        elif len(text) < 500:
            score *= 0.85

        # Наличие цитирований/ссылок
        citations = text.count(
            "[") + text.count("source") + text.count("according to")
        if citations > 3:
            score = min(1.0, score * 1.1)

        return min(1.0, max(0.0, score))

    def update_history(self, url: str, score: float) -> None:
        """Обновить историю для домена."""
        domain = self._extract_domain(url)
        if domain not in self._history:
            self._history[domain] = []
        self._history[domain].append(score)
        # Ограничиваем историю
        if len(self._history[domain]) > 50:
            self._history[domain] = self._history[domain][-25:]

    def set_custom_score(self, domain: str, score: float) -> None:
        """Установить пользовательскую оценку домена."""
        self._custom_scores[domain] = max(0.0, min(1.0, score))

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Извлечь домен из URL."""
        url = url.lower().strip()
        # Убираем протокол
        for prefix in ["https://", "http://", "www."]:
            if url.startswith(prefix):
                url = url[len(prefix):]
        # Берём до первого /
        return url.split("/")[0].split("?")[0]


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRADICTION DETECTOR — Выявление расхождений
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class FactClaim:
    """Факт/утверждение из источника."""
    text: str
    source_url: str = ""
    source_name: str = ""
    trust_score: float = 0.5
    timestamp: datetime = field(default_factory=datetime.utcnow)
    category: str = ""  # number, date, name, statement

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "source": self.source_name or self.source_url,
            "trust": round(self.trust_score, 2),
            "category": self.category,
        }


@dataclass
class Contradiction:
    """Обнаруженное противоречие."""
    claim_a: FactClaim
    claim_b: FactClaim
    description: str = ""
    severity: str = "medium"  # low, medium, high
    resolution: str = ""  # Какому источнику верить

    def to_dict(self) -> dict:
        return {
            "claim_a": self.claim_a.to_dict(),
            "claim_b": self.claim_b.to_dict(),
            "description": self.description,
            "severity": self.severity,
            "resolution": self.resolution,
        }


class ContradictionDetector:
    """
    Детектор противоречий между источниками.

    Стратегии:
    - Числовые данные: прямое сравнение
    - Даты: сравнение временных рамок
    - Утверждения: семантическое сравнение (keywords overlap)
    """

    def detect(self, facts: list[FactClaim]) -> list[Contradiction]:
        """Обнаружить противоречия в списке фактов."""
        contradictions: list[Contradiction] = []

        for i in range(len(facts)):
            for j in range(i + 1, len(facts)):
                contradiction = self._compare_facts(facts[i], facts[j])
                if contradiction:
                    contradictions.append(contradiction)

        return contradictions

    def _compare_facts(self, a: FactClaim, b: FactClaim) -> Contradiction | None:
        """Сравнить два факта на противоречие."""
        # Один источник — не противоречие
        if a.source_url == b.source_url:
            return None

        # Числовые данные
        nums_a = self._extract_numbers(a.text)
        nums_b = self._extract_numbers(b.text)

        if nums_a and nums_b:
            # Если контекст похожий но числа разные
            similarity = self._text_similarity(a.text, b.text)
            if similarity > 0.3:
                for na in nums_a:
                    for nb in nums_b:
                        if na != 0 and nb != 0:
                            diff = abs(na - nb) / max(abs(na), abs(nb))
                            if diff > 0.15:  # >15% разница
                                # Кому верить?
                                resolution = ""
                                if a.trust_score > b.trust_score + 0.1:
                                    resolution = f"Доверяем: {a.source_name or a.source_url}"
                                elif b.trust_score > a.trust_score + 0.1:
                                    resolution = f"Доверяем: {b.source_name or b.source_url}"
                                else:
                                    resolution = "Нужна дополнительная проверка"

                                severity = "high" if diff > 0.5 else "medium" if diff > 0.25 else "low"

                                return Contradiction(
                                    claim_a=a,
                                    claim_b=b,
                                    description=(
                                        f"Числовое расхождение: {na} vs {nb} "
                                        f"(разница {diff:.0%})"
                                    ),
                                    severity=severity,
                                    resolution=resolution,
                                )

        # Прямые противоречия по ключевым словам
        negation_pairs = [
            ("yes", "no"), ("да", "нет"),
            ("true", "false"), ("верно", "неверно"),
            ("increased", "decreased"), ("выросл", "упал"),
            ("support", "oppose"), ("за", "против"),
        ]

        a_lower = a.text.lower()
        b_lower = b.text.lower()

        for pos, neg in negation_pairs:
            if (pos in a_lower and neg in b_lower) or (neg in a_lower and pos in b_lower):
                similarity = self._text_similarity(a.text, b.text)
                if similarity > 0.2:
                    return Contradiction(
                        claim_a=a,
                        claim_b=b,
                        description=f"Противоположные утверждения: {pos}/{neg}",
                        severity="medium",
                        resolution=self._resolve_by_trust(a, b),
                    )

        return None

    def _resolve_by_trust(self, a: FactClaim, b: FactClaim) -> str:
        """Определить кому верить по trust score."""
        if a.trust_score > b.trust_score + 0.15:
            return f"Доверяем: {a.source_name or 'источник A'} (trust={a.trust_score:.2f})"
        elif b.trust_score > a.trust_score + 0.15:
            return f"Доверяем: {b.source_name or 'источник B'} (trust={b.trust_score:.2f})"
        return "Равная достоверность — нужна дополнительная проверка"

    @staticmethod
    def _extract_numbers(text: str) -> list[float]:
        """Извлечь числа из текста."""
        numbers = re.findall(r'-?\d+\.?\d*', text)
        return [float(n) for n in numbers[:5]]

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """Простое сходство текстов (Jaccard по словам)."""
        words_a = set(re.findall(r'\w{3,}', a.lower()))
        words_b = set(re.findall(r'\w{3,}', b.lower()))

        if not words_a or not words_b:
            return 0.0

        intersection = words_a & words_b
        union = words_a | words_b

        return len(intersection) / len(union) if union else 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# QUERY EXPANDER — Самостоятельное уточнение запросов
# ═══════════════════════════════════════════════════════════════════════════════


class QueryExpander:
    """
    Расширение и уточнение поисковых запросов.

    Агент не просто ищет 1 раз — он:
    1. Ищет по исходному запросу
    2. Анализирует результаты — чего не хватает?
    3. Генерирует уточнённые запросы
    4. Ищет повторно
    5. Синтезирует

    Self-Query Expansion:
    - Синонимы и переформулировки
    - Специализированные запросы (site:, intitle:)
    - Перевод на другие языки для расширения охвата
    """

    # Паттерны расширения
    EXPANSION_PATTERNS: dict[str, list[str]] = {
        "цена|стоимость|price|cost": [
            "{query} price comparison",
            "{query} стоимость 2026",
            "{query} цена отзывы",
        ],
        "лучший|best|top": [
            "{query} comparison",
            "{query} vs alternatives",
            "{query} рейтинг",
        ],
        "как|how|tutorial": [
            "{query} tutorial step by step",
            "{query} guide for beginners",
            "{query} примеры",
        ],
        "новост|news|update": [
            "{query} latest news 2026",
            "{query} последние новости",
        ],
        "ошибка|error|problem|bug": [
            "{query} fix solution",
            "{query} how to solve",
            "{query} workaround",
        ],
    }

    def expand(self, query: str, max_queries: int = 3) -> list[str]:
        """
        Расширить запрос вариантами.

        Returns:
            Список запросов (включая оригинальный)
        """
        queries = [query]

        lower = query.lower()

        # По паттернам
        for pattern, templates in self.EXPANSION_PATTERNS.items():
            if re.search(pattern, lower):
                for template in templates[:max_queries - 1]:
                    expanded = template.format(query=query)
                    if expanded not in queries:
                        queries.append(expanded)

        # Если мало вариантов — добавляем базовые
        if len(queries) < max_queries:
            # Добавляем год для актуальности
            if "2026" not in query and "2025" not in query:
                queries.append(f"{query} 2026")

            # Добавляем "site:" для авторитетных источников
            if len(queries) < max_queries:
                queries.append(
                    f"{query} site:wikipedia.org OR site:britannica.com")

        return queries[:max_queries]

    def refine_from_results(
        self,
        original_query: str,
        results_summary: str,
        gaps: list[str] | None = None,
    ) -> list[str]:
        """
        Уточнить запрос на основе промежуточных результатов.

        Args:
            original_query: Исходный запрос
            results_summary: Что уже нашли
            gaps: Что не хватает

        Returns:
            Уточнённые запросы
        """
        refined = []

        if gaps:
            for gap in gaps[:3]:
                refined.append(f"{original_query} {gap}")

        # Если есть результаты — ищем конкретнее
        if results_summary:
            # Извлекаем ключевые термины из результатов
            terms = re.findall(r'\b[A-ZА-Я][a-zа-я]{3,}\b', results_summary)
            unique_terms = list(set(terms))[:3]
            if unique_terms:
                refined.append(f"{original_query} {' '.join(unique_terms)}")

        return refined if refined else [original_query]


# ═══════════════════════════════════════════════════════════════════════════════
# HYPOTHESIS TESTER — Параллельная проверка гипотез
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class Hypothesis:
    """Гипотеза для проверки."""
    id: str = ""
    statement: str = ""
    confidence: float = 0.5
    evidence_for: list[FactClaim] = field(default_factory=list)
    evidence_against: list[FactClaim] = field(default_factory=list)
    status: str = "testing"  # testing, confirmed, rejected, uncertain
    tested_at: datetime | None = None

    @property
    def net_evidence(self) -> float:
        """Чистая оценка: (за - против) / всего."""
        total = len(self.evidence_for) + len(self.evidence_against)
        if total == 0:
            return 0.0

        score_for = sum(e.trust_score for e in self.evidence_for)
        score_against = sum(e.trust_score for e in self.evidence_against)

        return (score_for - score_against) / total

    def to_dict(self) -> dict:
        return {
            "statement": self.statement,
            "confidence": round(self.confidence, 2),
            "evidence_for": len(self.evidence_for),
            "evidence_against": len(self.evidence_against),
            "net_evidence": round(self.net_evidence, 2),
            "status": self.status,
        }


class HypothesisTester:
    """
    Параллельная проверка гипотез.

    1. Генерирует гипотезы из вопроса
    2. Проверяет каждую через поиск
    3. Собирает evidence for/against
    4. Определяет наиболее вероятный ответ
    """

    def generate_hypotheses(self, question: str, max_count: int = 3) -> list[Hypothesis]:
        """Генерация гипотез из вопроса (rule-based)."""
        hypotheses: list[Hypothesis] = []

        lower = question.lower()

        # Бинарные вопросы
        if any(w in lower for w in ["ли", "можно ли", "is it", "can", "should"]):
            hypotheses.append(Hypothesis(
                id="h_yes",
                statement=f"ДА: {question}",
                confidence=0.5,
            ))
            hypotheses.append(Hypothesis(
                id="h_no",
                statement=f"НЕТ: {question}",
                confidence=0.5,
            ))

        # Сравнительные вопросы
        elif any(w in lower for w in ["лучше", "better", "vs", "или", " or "]):
            parts = re.split(r'\bили\b|\bor\b|\bvs\b|\bлучше\b', lower)
            if len(parts) >= 2:
                for i, part in enumerate(parts[:max_count]):
                    hypotheses.append(Hypothesis(
                        id=f"h_{i}",
                        statement=f"Лучший вариант: {part.strip()}",
                        confidence=0.5,
                    ))

        # Общие вопросы — одна гипотеза
        if not hypotheses:
            hypotheses.append(Hypothesis(
                id="h_main",
                statement=question,
                confidence=0.5,
            ))

        return hypotheses[:max_count]

    def evaluate_hypothesis(
        self,
        hypothesis: Hypothesis,
        facts: list[FactClaim],
    ) -> Hypothesis:
        """Оценить гипотезу на основе фактов."""
        for fact in facts:
            # Простая эвристика: если факт содержит ключевые слова гипотезы
            h_words = set(re.findall(r'\w{3,}', hypothesis.statement.lower()))
            f_words = set(re.findall(r'\w{3,}', fact.text.lower()))

            overlap = len(h_words & f_words) / max(len(h_words), 1)

            if overlap > 0.3:
                # Факт релевантен гипотезе
                # Поддерживает или опровергает?
                negative_words = {
                    "не", "нет", "нельзя", "невозможно", "ошибочно",
                    "not", "no", "cannot", "impossible", "wrong", "false",
                }

                is_negative = any(w in fact.text.lower()
                                  for w in negative_words)

                if is_negative:
                    hypothesis.evidence_against.append(fact)
                else:
                    hypothesis.evidence_for.append(fact)

        # Обновляем уверенность
        net = hypothesis.net_evidence
        hypothesis.confidence = max(0.0, min(1.0, 0.5 + net * 0.5))

        # Определяем статус
        if hypothesis.confidence > 0.75:
            hypothesis.status = "confirmed"
        elif hypothesis.confidence < 0.25:
            hypothesis.status = "rejected"
        else:
            hypothesis.status = "uncertain"

        hypothesis.tested_at = datetime.utcnow()
        return hypothesis


# ═══════════════════════════════════════════════════════════════════════════════
# CONTEXT COMPRESSOR — Сжатие контекста
# ═══════════════════════════════════════════════════════════════════════════════


class ContextCompressor:
    """
    Сжатие больших текстов для экономии контекста LLM.

    Стратегии:
    - Extractive: выбор самых важных предложений
    - Chunking: разбивка на смысловые блоки
    - Deduplication: удаление повторов
    """

    def compress(
        self,
        text: str,
        max_length: int = 2000,
        strategy: str = "extractive",
    ) -> str:
        """
        Сжать текст до max_length символов.

        Strategies:
        - extractive: выбор ключевых предложений
        - truncate: простое обрезание
        - smart: extractive + dedup
        """
        if len(text) <= max_length:
            return text

        if strategy == "truncate":
            return text[:max_length] + "..."

        if strategy == "extractive" or strategy == "smart":
            return self._extractive_compress(text, max_length)

        return text[:max_length]

    def _extractive_compress(self, text: str, max_length: int) -> str:
        """Извлечение ключевых предложений."""
        sentences = self._split_sentences(text)
        if not sentences:
            return text[:max_length]

        # Оцениваем важность каждого предложения
        scored = []
        for i, sent in enumerate(sentences):
            score = self._sentence_importance(sent, i, len(sentences))
            scored.append((score, i, sent))

        # Сортируем по важности
        scored.sort(key=lambda x: x[0], reverse=True)

        # Собираем в пределах лимита (в оригинальном порядке)
        selected: list[tuple[int, str]] = []
        current_length = 0

        for score, idx, sent in scored:
            if current_length + len(sent) + 1 <= max_length:
                selected.append((idx, sent))
                current_length += len(sent) + 1

        # Восстанавливаем порядок
        selected.sort(key=lambda x: x[0])

        return " ".join(s for _, s in selected)

    def _sentence_importance(
        self,
        sentence: str,
        position: int,
        total: int,
    ) -> float:
        """Оценка важности предложения."""
        score = 0.0

        # Позиция (начало и конец важнее)
        if position < total * 0.2:
            score += 0.3  # Начало текста
        elif position > total * 0.8:
            score += 0.2  # Конец текста

        # Длина (слишком короткие — неинформативные)
        length = len(sentence)
        if length > 50:
            score += 0.1
        if length > 100:
            score += 0.1
        if length < 20:
            score -= 0.2

        # Содержит числа (факты)
        if re.search(r'\d', sentence):
            score += 0.2

        # Содержит ключевые слова
        important_words = {
            "важно", "ключев", "главн", "итого", "вывод", "результат",
            "important", "key", "main", "result", "conclusion", "total",
            "therefore", "however", "specifically", "notably",
        }
        lower = sentence.lower()
        for w in important_words:
            if w in lower:
                score += 0.15
                break

        # Содержит имена собственные (заглавные буквы в середине)
        if re.search(r'\b[A-ZА-Я][a-zа-я]+\s[A-ZА-Я]', sentence):
            score += 0.1

        return score

    def _split_sentences(self, text: str) -> list[str]:
        """Разбить текст на предложения."""
        # Простое разбиение по . ! ?
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if len(s.strip()) > 10]

    def deduplicate(self, texts: list[str]) -> list[str]:
        """Удалить дубликаты и очень похожие тексты."""
        if not texts:
            return []

        unique: list[str] = [texts[0]]

        for text in texts[1:]:
            is_dup = False
            for existing in unique:
                sim = ContradictionDetector._text_similarity(text, existing)
                if sim > 0.7:
                    is_dup = True
                    break
            if not is_dup:
                unique.append(text)

        return unique

    def chunk(self, text: str, chunk_size: int = 1000, overlap: int = 100) -> list[str]:
        """Разбить текст на chunks с перекрытием."""
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + chunk_size

            # Ищем конец предложения
            if end < len(text):
                # Ищем ближайшую точку
                dot_pos = text.rfind(".", start + chunk_size // 2, end + 100)
                if dot_pos > start:
                    end = dot_pos + 1

            chunks.append(text[start:end].strip())
            start = end - overlap

        return chunks


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIDENCE ENGINE — Уверенность и неопределённость
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ConfidenceAssessment:
    """Оценка уверенности в ответе."""
    overall: float = 0.5           # 0.0 - 1.0
    source_quality: float = 0.5    # Качество источников
    consensus: float = 0.5         # Согласованность источников
    freshness: float = 0.5         # Актуальность данных
    completeness: float = 0.5      # Полнота ответа
    needs_more_data: bool = False   # Нужно больше данных?
    gaps: list[str] = field(default_factory=list)  # Что не хватает

    @property
    def label(self) -> str:
        if self.overall >= 0.8:
            return "🟢 Высокая"
        elif self.overall >= 0.6:
            return "🟡 Средняя"
        elif self.overall >= 0.4:
            return "🟠 Низкая"
        else:
            return "🔴 Очень низкая"

    def to_dict(self) -> dict:
        return {
            "overall": round(self.overall, 2),
            "label": self.label,
            "source_quality": round(self.source_quality, 2),
            "consensus": round(self.consensus, 2),
            "freshness": round(self.freshness, 2),
            "completeness": round(self.completeness, 2),
            "needs_more_data": self.needs_more_data,
            "gaps": self.gaps,
        }


class ConfidenceEngine:
    """
    Движок оценки уверенности.

    Если уверенность низкая → автоматический дополнительный поиск.
    """

    THRESHOLD_LOW = 0.4        # Ниже — нужен допоиск
    THRESHOLD_ACCEPTABLE = 0.6  # Выше — можно отвечать

    def assess(
        self,
        facts: list[FactClaim],
        contradictions: list[Contradiction] | None = None,
        query: str = "",
    ) -> ConfidenceAssessment:
        """Оценить уверенность в собранных данных."""
        if not facts:
            return ConfidenceAssessment(
                overall=0.1,
                needs_more_data=True,
                gaps=["Нет данных"],
            )

        # Source quality
        trust_scores = [f.trust_score for f in facts]
        source_quality = sum(trust_scores) / len(trust_scores)

        # Consensus (согласованность)
        contradictions = contradictions or []
        if len(facts) > 1:
            consensus = 1.0 - (len(contradictions) / max(len(facts), 1))
            consensus = max(0.0, consensus)
        else:
            consensus = 0.5  # Один источник — средняя уверенность

        # Freshness (берём средний возраст)
        now = datetime.utcnow()
        ages = []
        for f in facts:
            age = (now - f.timestamp).total_seconds() / 3600  # часы
            ages.append(age)
        avg_age = sum(ages) / len(ages) if ages else 0
        freshness = 1.0 if avg_age < 24 else 0.8 if avg_age < 168 else 0.5

        # Completeness
        completeness = min(1.0, len(facts) / 3)  # 3+ факта = полный

        # Overall
        overall = (
            source_quality * 0.3
            + consensus * 0.3
            + freshness * 0.2
            + completeness * 0.2
        )

        # Gaps
        gaps = []
        if len(facts) < 2:
            gaps.append("Мало источников (нужно минимум 2-3)")
        if contradictions:
            gaps.append(f"Есть противоречия ({len(contradictions)})")
        if source_quality < 0.5:
            gaps.append("Низкое качество источников")

        needs_more = overall < self.THRESHOLD_LOW or len(facts) < 2

        return ConfidenceAssessment(
            overall=round(overall, 2),
            source_quality=round(source_quality, 2),
            consensus=round(consensus, 2),
            freshness=round(freshness, 2),
            completeness=round(completeness, 2),
            needs_more_data=needs_more,
            gaps=gaps,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# STALENESS DETECTOR — Обнаружение устаревших данных
# ═══════════════════════════════════════════════════════════════════════════════


class StalenessDetector:
    """
    Определение устаревших данных.

    Правила:
    - Новости > 7 дней — устаревшие
    - Технические данные > 1 год — проверить
    - Научные данные > 3 лет — проверить
    - Исторические факты — не устаревают
    """

    # Категории и их сроки актуальности (дни)
    FRESHNESS_RULES: dict[str, int] = {
        "news": 7,
        "prices": 1,
        "weather": 1,
        "stocks": 1,
        "technology": 365,
        "science": 1095,
        "laws": 730,
        "general": 365,
        "history": 36500,  # 100 лет
    }

    def detect_category(self, query: str) -> str:
        """Определить категорию запроса."""
        lower = query.lower()

        patterns = {
            "news": ["новост", "сегодня", "вчера", "news", "latest", "today"],
            "prices": ["цена", "стоимость", "курс", "price", "cost", "rate"],
            "weather": ["погода", "weather", "forecast", "прогноз"],
            "stocks": ["акции", "stock", "shares", "биржа", "market"],
            "technology": ["технолог", "software", "hardware", "tech", "ai"],
            "science": ["наука", "research", "study", "исследован"],
            "laws": ["закон", "law", "regulation", "правило", "tax"],
            "history": ["истори", "history", "historical", "в прошлом"],
        }

        for category, keywords in patterns.items():
            if any(k in lower for k in keywords):
                return category

        return "general"

    def is_stale(
        self,
        content_date: datetime,
        category: str = "general",
    ) -> tuple[bool, str]:
        """
        Проверить, устарели ли данные.

        Returns:
            (is_stale, reason)
        """
        max_age_days = self.FRESHNESS_RULES.get(category, 365)
        age = (datetime.utcnow() - content_date).days

        if age > max_age_days:
            return True, (
                f"Данные от {content_date.strftime('%d.%m.%Y')} "
                f"устарели для категории «{category}» "
                f"(максимум {max_age_days} дней)"
            )

        return False, ""

    def filter_fresh(
        self,
        facts: list[FactClaim],
        category: str = "general",
    ) -> list[FactClaim]:
        """Отфильтровать только свежие факты."""
        max_age_days = self.FRESHNESS_RULES.get(category, 365)
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)

        return [f for f in facts if f.timestamp >= cutoff]


# ═══════════════════════════════════════════════════════════════════════════════
# REASONING LAYER v2 — Объединение всех компонентов
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ReasoningResult:
    """Результат reasoning процесса."""
    answer: str = ""
    confidence: ConfidenceAssessment = field(
        default_factory=ConfidenceAssessment)
    facts: list[FactClaim] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    sources_used: int = 0
    queries_expanded: int = 0
    reasoning_time_ms: int = 0
    compressed: bool = False

    def to_dict(self) -> dict:
        return {
            "answer": self.answer[:500],
            "confidence": self.confidence.to_dict(),
            "facts_count": len(self.facts),
            "contradictions_count": len(self.contradictions),
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "sources_used": self.sources_used,
            "queries_expanded": self.queries_expanded,
            "reasoning_time_ms": self.reasoning_time_ms,
        }


class ReasoningLayerV2:
    """
    Объединяющий движок reasoning.

    Процесс:
    1. Expand query → несколько вариантов
    2. Search → собрать факты из 2-3+ источников
    3. Score → оценить trust каждого источника
    4. Detect contradictions → найти расхождения
    5. Check staleness → отфильтровать устаревшее
    6. Assess confidence → нужно ли больше данных?
    7. If low confidence → refine queries → search again
    8. Compress → сжать для LLM
    9. Synthesize → сформировать ответ
    """

    def __init__(self):
        self.trust_scorer = TrustScorerV2()
        self.contradiction_detector = ContradictionDetector()
        self.query_expander = QueryExpander()
        self.hypothesis_tester = HypothesisTester()
        self.compressor = ContextCompressor()
        self.confidence_engine = ConfidenceEngine()
        self.staleness_detector = StalenessDetector()

    def expand_query(self, query: str, max_queries: int = 3) -> list[str]:
        """Расширить запрос."""
        return self.query_expander.expand(query, max_queries)

    def score_facts(self, facts: list[FactClaim]) -> list[FactClaim]:
        """Оценить trust score для всех фактов."""
        for fact in facts:
            fact.trust_score = self.trust_scorer.score_content(
                fact.text, fact.source_url, fact.timestamp
            )
        return facts

    def find_contradictions(self, facts: list[FactClaim]) -> list[Contradiction]:
        """Найти противоречия."""
        return self.contradiction_detector.detect(facts)

    def assess_confidence(
        self,
        facts: list[FactClaim],
        contradictions: list[Contradiction] | None = None,
        query: str = "",
    ) -> ConfidenceAssessment:
        """Оценить уверенность."""
        return self.confidence_engine.assess(facts, contradictions, query)

    def compress_context(self, text: str, max_length: int = 2000) -> str:
        """Сжать текст."""
        return self.compressor.compress(text, max_length)

    def generate_hypotheses(self, question: str) -> list[Hypothesis]:
        """Сгенерировать гипотезы."""
        return self.hypothesis_tester.generate_hypotheses(question)

    def test_hypothesis(
        self,
        hypothesis: Hypothesis,
        facts: list[FactClaim],
    ) -> Hypothesis:
        """Проверить гипотезу."""
        return self.hypothesis_tester.evaluate_hypothesis(hypothesis, facts)

    def get_stats(self) -> dict[str, Any]:
        """Статистика."""
        return {
            "trust_domains_tracked": len(self.trust_scorer._history),
            "custom_scores": len(self.trust_scorer._custom_scores),
        }


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

reasoning_v2 = ReasoningLayerV2()
