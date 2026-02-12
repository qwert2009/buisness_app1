"""
PDS-Ultimate Internet Reasoning Layer
=======================================
Слой интернет-рассуждений поверх Browser Engine.

Возможности:
1. Multi-source search — поиск по нескольким источникам, агрегация
2. Source trust scoring — оценка доверия к источникам
3. Contradiction detection — обнаружение противоречий
4. Fact synthesis — синтез информации с цитатами
5. Query expansion — расширение запросов для лучшего покрытия
6. Information freshness — оценка актуальности информации

Архитектура:
  User Query → QueryExpander → MultiSourceSearch → TrustScorer
  → ContradictionDetector → FactSynthesizer → Structured Answer
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from urllib.parse import urlparse

from pds_ultimate.config import logger

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# Домены с высоким доверием (базовый список)
TRUSTED_DOMAINS: dict[str, float] = {
    # Энциклопедии / справочники
    "wikipedia.org": 0.85,
    "britannica.com": 0.90,
    "scholar.google.com": 0.92,
    # Новости (мировые)
    "reuters.com": 0.88,
    "bbc.com": 0.85,
    "bbc.co.uk": 0.85,
    "apnews.com": 0.88,
    # Техника / программирование
    "stackoverflow.com": 0.80,
    "github.com": 0.78,
    "docs.python.org": 0.95,
    "developer.mozilla.org": 0.92,
    "w3.org": 0.95,
    # Бизнес / финансы
    "bloomberg.com": 0.85,
    "forbes.com": 0.75,
    "investopedia.com": 0.80,
    # Наука
    "nature.com": 0.93,
    "sciencedirect.com": 0.90,
    "pubmed.ncbi.nlm.nih.gov": 0.92,
    "arxiv.org": 0.85,
    # Правительственные
    "gov": 0.88,
    "edu": 0.82,
}

# Домены с низким доверием
UNTRUSTED_PATTERNS: list[str] = [
    "reddit.com",
    "quora.com",
    "yahoo.answers",
    "answers.com",
    "wiki.answers",
    "ehow.com",
    "about.com",
]

# Маркеры свежести контента
FRESHNESS_PATTERNS: list[re.Pattern] = [
    re.compile(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})"),          # 2025-01-15
    re.compile(r"(\d{1,2}\s+\w+\s+\d{4})"),                # 15 January 2025
    re.compile(r"(January|February|March|April|May|June|"
               r"July|August|September|October|November|"
               r"December)\s+\d{1,2},?\s+\d{4}", re.I),    # January 15, 2025
    re.compile(r"Updated:?\s*(.{5,30})", re.I),             # Updated: ...
]


# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class SourceReliability(str, Enum):
    """Уровень надёжности источника."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ContradictionSeverity(str, Enum):
    """Серьёзность противоречия."""
    MINOR = "minor"        # Различия в деталях
    MODERATE = "moderate"  # Существенные различия
    MAJOR = "major"        # Прямые противоречия


@dataclass
class SourceInfo:
    """Информация об источнике."""
    url: str
    domain: str
    title: str = ""
    trust_score: float = 0.5       # 0.0-1.0
    reliability: SourceReliability = SourceReliability.UNKNOWN
    freshness_score: float = 0.5   # 0.0-1.0 (1.0 = свежий)
    content_length: int = 0
    detected_date: str | None = None
    language: str = "unknown"

    @property
    def composite_score(self) -> float:
        """Комбинированная оценка (trust * freshness)."""
        return round(self.trust_score * 0.7 + self.freshness_score * 0.3, 3)


@dataclass
class ExtractedFact:
    """Извлечённый факт с привязкой к источнику."""
    text: str
    source: SourceInfo
    confidence: float = 0.5     # 0.0-1.0
    category: str = "general"   # general, price, date, statistic, opinion
    keywords: list[str] = field(default_factory=list)

    @property
    def fact_id(self) -> str:
        """Уникальный ID факта."""
        h = hashlib.md5(self.text.encode()).hexdigest()[:8]
        return f"fact_{h}"


@dataclass
class Contradiction:
    """Противоречие между фактами."""
    fact_a: ExtractedFact
    fact_b: ExtractedFact
    severity: ContradictionSeverity
    description: str = ""

    @property
    def sources_involved(self) -> list[str]:
        return [self.fact_a.source.url, self.fact_b.source.url]


@dataclass
class SynthesizedAnswer:
    """Синтезированный ответ из нескольких источников."""
    query: str
    summary: str                            # Основной ответ
    facts: list[ExtractedFact]              # Все извлечённые факты
    sources: list[SourceInfo]               # Использованные источники
    contradictions: list[Contradiction]     # Найденные противоречия
    confidence: float                       # Общая уверенность 0.0-1.0
    sources_count: int = 0                  # Кол-во источников
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """Конвертация в словарь."""
        return {
            "query": self.query,
            "summary": self.summary,
            "confidence": self.confidence,
            "sources_count": self.sources_count,
            "facts_count": len(self.facts),
            "contradictions_count": len(self.contradictions),
            "sources": [
                {"url": s.url, "domain": s.domain,
                 "trust": s.trust_score, "title": s.title}
                for s in self.sources
            ],
            "contradictions": [
                {"severity": c.severity.value,
                 "description": c.description}
                for c in self.contradictions
            ],
        }

    @property
    def has_contradictions(self) -> bool:
        return len(self.contradictions) > 0

    @property
    def quality_label(self) -> str:
        """Метка качества ответа."""
        if self.confidence >= 0.8 and not self.has_contradictions:
            return "✅ Высокое качество"
        elif self.confidence >= 0.5:
            return "⚠️ Среднее качество"
        else:
            return "❌ Низкое качество"


@dataclass
class ResearchStats:
    """Статистика исследования."""
    queries_performed: int = 0
    pages_analyzed: int = 0
    facts_extracted: int = 0
    contradictions_found: int = 0
    total_time_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "queries": self.queries_performed,
            "pages": self.pages_analyzed,
            "facts": self.facts_extracted,
            "contradictions": self.contradictions_found,
            "time_ms": self.total_time_ms,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. TRUST SCORER — Оценка доверия к источникам
# ═══════════════════════════════════════════════════════════════════════════════


class TrustScorer:
    """
    Оценивает надёжность интернет-источников.

    Факторы:
    - Доменная репутация (предустановленная + выученная)
    - Свежесть контента
    - Длина контента (короткий = менее надёжный)
    - HTTPS vs HTTP
    - TLD (.gov, .edu = высокий)
    """

    def __init__(self):
        self._domain_scores: dict[str, float] = dict(TRUSTED_DOMAINS)
        self._custom_scores: dict[str, float] = {}

    def score_source(
        self,
        url: str,
        title: str = "",
        content: str = "",
        detected_date: str | None = None,
    ) -> SourceInfo:
        """
        Оценить источник по URL и содержимому.

        Returns:
            SourceInfo с заполненными оценками
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower().removeprefix("www.")
        tld = domain.split(".")[-1] if "." in domain else ""

        # 1. Базовая оценка по домену
        trust = self._get_domain_trust(domain, tld)

        # 2. HTTPS бонус
        if parsed.scheme == "https":
            trust = min(1.0, trust + 0.05)

        # 3. Длина контента
        content_len = len(content)
        if content_len < 100:
            trust *= 0.7   # Слишком короткий
        elif content_len > 2000:
            trust = min(1.0, trust + 0.05)  # Подробный

        # 4. Свежесть
        freshness = self._estimate_freshness(content, detected_date)

        # 5. Определяем reliability
        if trust >= 0.75:
            reliability = SourceReliability.HIGH
        elif trust >= 0.45:
            reliability = SourceReliability.MEDIUM
        else:
            reliability = SourceReliability.LOW

        return SourceInfo(
            url=url,
            domain=domain,
            title=title,
            trust_score=round(trust, 3),
            reliability=reliability,
            freshness_score=round(freshness, 3),
            content_length=content_len,
            detected_date=detected_date,
        )

    def _get_domain_trust(self, domain: str, tld: str) -> float:
        """Получить trust score для домена."""
        # Точное совпадение
        if domain in self._custom_scores:
            return self._custom_scores[domain]
        if domain in self._domain_scores:
            return self._domain_scores[domain]

        # Проверка parent domain
        parts = domain.split(".")
        for i in range(1, len(parts)):
            parent = ".".join(parts[i:])
            if parent in self._domain_scores:
                return self._domain_scores[parent]

        # TLD-базовое
        if tld in self._domain_scores:
            return self._domain_scores[tld]

        # Проверка untrusted
        for pattern in UNTRUSTED_PATTERNS:
            if pattern in domain:
                return 0.3

        # Default
        return 0.5

    def _estimate_freshness(
        self,
        content: str,
        detected_date: str | None = None,
    ) -> float:
        """Оценить свежесть контента."""
        if detected_date:
            try:
                # Пробуем распарсить дату
                for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%B %d, %Y"):
                    try:
                        dt = datetime.strptime(detected_date, fmt)
                        days_old = (datetime.now() - dt).days
                        if days_old < 30:
                            return 1.0
                        elif days_old < 180:
                            return 0.8
                        elif days_old < 365:
                            return 0.6
                        elif days_old < 730:
                            return 0.4
                        else:
                            return 0.2
                    except ValueError:
                        continue
            except Exception:
                pass

        # Ищем даты в контенте
        if content:
            for pattern in FRESHNESS_PATTERNS:
                match = pattern.search(content[:2000])
                if match:
                    # Нашли дату → средне-свежий
                    return 0.6

        # Нет информации
        return 0.5

    def add_custom_domain(self, domain: str, score: float) -> None:
        """Добавить пользовательскую оценку домена."""
        self._custom_scores[domain] = max(0.0, min(1.0, score))

    def get_domain_score(self, domain: str) -> float | None:
        """Получить score для домена."""
        domain = domain.lower().removeprefix("www.")
        if domain in self._custom_scores:
            return self._custom_scores[domain]
        if domain in self._domain_scores:
            return self._domain_scores[domain]
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# 2. QUERY EXPANDER — Расширение запросов
# ═══════════════════════════════════════════════════════════════════════════════


class QueryExpander:
    """
    Расширяет пользовательский запрос для лучшего покрытия.

    Стратегии:
    - Синонимы и переформулировки
    - Специализированные запросы (цены, отзывы, сравнение)
    - Добавление контекста (год, регион)
    """

    # Шаблоны расширения по типу запроса
    EXPANSION_TEMPLATES: dict[str, list[str]] = {
        "price": [
            "{query} цена",
            "{query} стоимость купить",
            "{query} price comparison",
        ],
        "review": [
            "{query} отзывы",
            "{query} review",
            "{query} плюсы минусы",
        ],
        "howto": [
            "{query} инструкция",
            "{query} how to guide",
            "{query} пошагово",
        ],
        "comparison": [
            "{query} сравнение",
            "{query} vs альтернативы",
            "{query} лучший выбор",
        ],
        "news": [
            "{query} новости 2025 2026",
            "{query} последние обновления",
            "{query} latest news",
        ],
        "definition": [
            "что такое {query}",
            "{query} определение",
            "{query} wiki",
        ],
    }

    # Ключевые слова для определения типа запроса
    TYPE_KEYWORDS: dict[str, list[str]] = {
        "price": ["цена", "стоимость", "купить", "price", "cost", "сколько стоит"],
        "review": ["отзыв", "review", "мнение", "оценк", "рейтинг"],
        "howto": ["как ", "how to", "инструкция", "настрои", "установи", "сделать"],
        "comparison": ["сравн", "лучш", "vs", "или", "versus", "compare"],
        "news": ["новост", "news", "обновлен", "latest", "последн"],
        "definition": ["что такое", "what is", "определение", "define"],
    }

    def expand(
        self,
        query: str,
        max_queries: int = 3,
        force_type: str | None = None,
    ) -> list[str]:
        """
        Расширить запрос.

        Args:
            query: Исходный запрос
            max_queries: Максимум запросов (включая оригинал)
            force_type: Принудительный тип (price, review, howto, ...)

        Returns:
            Список запросов (оригинал + расширения)
        """
        queries = [query]

        # Определяем тип запроса
        query_type = force_type or self._detect_type(query)

        # Получаем шаблоны расширения
        templates = self.EXPANSION_TEMPLATES.get(query_type, [])

        for template in templates:
            if len(queries) >= max_queries:
                break
            expanded = template.format(query=query)
            if expanded not in queries:
                queries.append(expanded)

        # Если не набрали — добавляем год
        if len(queries) < max_queries:
            year_query = f"{query} 2026"
            if year_query not in queries:
                queries.append(year_query)

        return queries[:max_queries]

    def _detect_type(self, query: str) -> str:
        """Определить тип запроса по ключевым словам."""
        query_lower = query.lower()

        for qtype, keywords in self.TYPE_KEYWORDS.items():
            for kw in keywords:
                if kw in query_lower:
                    return qtype

        return "general"

    def detect_query_type(self, query: str) -> str:
        """Публичный метод определения типа."""
        return self._detect_type(query)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. FACT EXTRACTOR — Извлечение фактов из текста
# ═══════════════════════════════════════════════════════════════════════════════


class FactExtractor:
    """
    Извлекает структурированные факты из текста страницы.

    Категории фактов:
    - general: общая информация
    - price: цены и стоимости
    - date: даты и временные рамки
    - statistic: числовые данные и статистика
    - opinion: мнения и оценки
    """

    # Паттерны для извлечения фактов
    PRICE_PATTERN = re.compile(
        r"[\$€£¥₽₸]\s*[\d,.]+|[\d,.]+\s*(?:USD|EUR|RUB|TMT|CNY|руб|долл|"
        r"манат|юан|тенге)",
        re.I,
    )

    STATISTIC_PATTERN = re.compile(
        r"\d+[.,]?\d*\s*(?:%|процент|percent|млн|млрд|тыс|billion|million|"
        r"thousand|GB|MB|TB|кг|kg|км|km|м²|га)",
        re.I,
    )

    DATE_PATTERN = re.compile(
        r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|"
        r"\d{1,2}\s+(?:янв|фев|мар|апр|мая|июн|июл|авг|сен|окт|ноя|дек)"
        r"[а-яё]*\s+\d{4}",
        re.I,
    )

    OPINION_MARKERS = [
        "считаю", "думаю", "полагаю", "по моему",
        "i think", "i believe", "in my opinion",
        "рекомендую", "советую", "recommend",
        "лучший", "худший", "best", "worst",
    ]

    def extract_facts(
        self,
        text: str,
        source: SourceInfo,
        query: str = "",
        max_facts: int = 10,
    ) -> list[ExtractedFact]:
        """
        Извлечь факты из текста.

        Args:
            text: Текст страницы
            source: Информация об источнике
            query: Оригинальный запрос (для релевантности)
            max_facts: Максимум фактов

        Returns:
            Список ExtractedFact
        """
        if not text or not text.strip():
            return []

        facts: list[ExtractedFact] = []

        # Разбиваем на предложения
        sentences = self._split_sentences(text)

        # Фильтруем по релевантности к запросу
        if query:
            sentences = self._filter_relevant(sentences, query)

        for sentence in sentences[:max_facts * 3]:
            if len(facts) >= max_facts:
                break

            sentence = sentence.strip()
            if len(sentence) < 15 or len(sentence) > 500:
                continue

            category = self._categorize(sentence)
            keywords = self._extract_keywords(sentence, query)
            confidence = self._estimate_confidence(
                sentence, source, category
            )

            facts.append(ExtractedFact(
                text=sentence,
                source=source,
                confidence=confidence,
                category=category,
                keywords=keywords,
            ))

        return facts

    def _split_sentences(self, text: str) -> list[str]:
        """Разбить текст на предложения."""
        # Простой сплиттер по точкам, ! и ?
        sentences = re.split(r'(?<=[.!?])\s+', text)
        # Фильтрация пустых и коротких
        return [s.strip() for s in sentences if len(s.strip()) > 10]

    def _filter_relevant(
        self,
        sentences: list[str],
        query: str,
    ) -> list[str]:
        """Отфильтровать релевантные предложения."""
        query_words = set(query.lower().split())
        scored = []

        for s in sentences:
            s_lower = s.lower()
            # Считаем совпадения слов запроса
            overlap = sum(1 for w in query_words if w in s_lower)
            if overlap > 0:
                scored.append((overlap, s))

        # Сортируем по релевантности
        scored.sort(key=lambda x: x[0], reverse=True)

        # Возвращаем релевантные + остальные (на случай если мало)
        relevant = [s for _, s in scored]
        other = [s for s in sentences if s not in relevant]
        return relevant + other

    def _categorize(self, sentence: str) -> str:
        """Определить категорию факта."""
        if self.PRICE_PATTERN.search(sentence):
            return "price"
        if self.STATISTIC_PATTERN.search(sentence):
            return "statistic"
        if self.DATE_PATTERN.search(sentence):
            return "date"

        s_lower = sentence.lower()
        for marker in self.OPINION_MARKERS:
            if marker in s_lower:
                return "opinion"

        return "general"

    def _extract_keywords(
        self,
        sentence: str,
        query: str = "",
    ) -> list[str]:
        """Извлечь ключевые слова."""
        # Слова из предложения, пересекающиеся с запросом
        words = re.findall(r'\b[а-яёa-z]{3,}\b', sentence.lower())
        query_words = set(re.findall(r'\b[а-яёa-z]{3,}\b', query.lower()))

        keywords = []
        for w in words:
            if w in query_words and w not in keywords:
                keywords.append(w)

        # Добавляем значимые слова из предложения
        stopwords = {
            "это", "что", "как", "для", "при", "или", "the",
            "and", "for", "with", "from", "that", "this",
            "can", "are", "was", "has", "have", "been",
            "его", "она", "они", "нас", "вас", "все",
        }
        for w in words:
            if w not in stopwords and w not in keywords and len(w) > 3:
                keywords.append(w)
                if len(keywords) >= 5:
                    break

        return keywords

    def _estimate_confidence(
        self,
        sentence: str,
        source: SourceInfo,
        category: str,
    ) -> float:
        """Оценить уверенность в факте."""
        base = source.trust_score

        # Факты с цифрами более конкретны
        if category in ("price", "statistic", "date"):
            base = min(1.0, base + 0.1)

        # Мнения менее надёжны
        if category == "opinion":
            base *= 0.8

        # Короткие предложения менее информативны
        if len(sentence) < 30:
            base *= 0.9

        return round(base, 3)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. CONTRADICTION DETECTOR — Обнаружение противоречий
# ═══════════════════════════════════════════════════════════════════════════════


class ContradictionDetector:
    """
    Обнаруживает противоречия между фактами из разных источников.

    Методы детекции:
    - Числовые противоречия (разные цены, даты, статистика)
    - Текстовые противоречия (антонимы, отрицания)
    - Тематическое совпадение + различие в фактах
    """

    # Пары антонимов/отрицаний
    CONTRADICTION_PAIRS: list[tuple[str, str]] = [
        ("да", "нет"),
        ("yes", "no"),
        ("правда", "ложь"),
        ("true", "false"),
        ("рост", "падение"),
        ("increase", "decrease"),
        ("growth", "decline"),
        ("лучше", "хуже"),
        ("better", "worse"),
        ("больше", "меньше"),
        ("more", "less"),
        ("дорогой", "дешёвый"),
        ("expensive", "cheap"),
        ("поддерживает", "не поддерживает"),
        ("supports", "doesn't support"),
        ("бесплатно", "платно"),
        ("free", "paid"),
        ("доступен", "недоступен"),
        ("available", "unavailable"),
    ]

    NEGATION_WORDS = [
        "не", "нет", "без", "никогда", "ничего",
        "not", "no", "never", "none", "neither", "nor",
        "don't", "doesn't", "isn't", "aren't", "won't",
    ]

    def detect(
        self,
        facts: list[ExtractedFact],
        similarity_threshold: float = 0.3,
    ) -> list[Contradiction]:
        """
        Обнаружить противоречия между фактами.

        Args:
            facts: Список фактов
            similarity_threshold: Порог тематического сходства

        Returns:
            Список обнаруженных противоречий
        """
        contradictions: list[Contradiction] = []

        # Сравниваем каждую пару фактов
        for i in range(len(facts)):
            for j in range(i + 1, len(facts)):
                fa, fb = facts[i], facts[j]

                # Пропускаем факты из одного источника
                if fa.source.url == fb.source.url:
                    continue

                # Проверяем тематическое сходство
                similarity = self._topic_similarity(fa, fb)
                if similarity < similarity_threshold:
                    continue

                # Проверяем числовые противоречия
                num_contradiction = self._check_numeric(fa, fb)
                if num_contradiction:
                    contradictions.append(num_contradiction)
                    continue

                # Проверяем текстовые противоречия
                text_contradiction = self._check_textual(fa, fb)
                if text_contradiction:
                    contradictions.append(text_contradiction)

        return contradictions

    def _topic_similarity(self, fa: ExtractedFact, fb: ExtractedFact) -> float:
        """Тематическое сходство между фактами (по keywords)."""
        if not fa.keywords or not fb.keywords:
            return 0.0

        set_a = set(fa.keywords)
        set_b = set(fb.keywords)

        intersection = len(set_a & set_b)
        union = len(set_a | set_b)

        if union == 0:
            return 0.0

        return intersection / union

    def _check_numeric(
        self,
        fa: ExtractedFact,
        fb: ExtractedFact,
    ) -> Contradiction | None:
        """Проверить числовые противоречия."""
        if fa.category not in ("price", "statistic") or \
           fb.category not in ("price", "statistic"):
            return None

        nums_a = re.findall(r'[\d,.]+', fa.text)
        nums_b = re.findall(r'[\d,.]+', fb.text)

        if not nums_a or not nums_b:
            return None

        # Парсим числа
        try:
            val_a = float(nums_a[0].replace(",", ""))
            val_b = float(nums_b[0].replace(",", ""))
        except (ValueError, IndexError):
            return None

        if val_a == 0 or val_b == 0:
            return None

        # Проверяем расхождение > 30%
        diff_ratio = abs(val_a - val_b) / max(val_a, val_b)

        if diff_ratio > 0.3:
            severity = (
                ContradictionSeverity.MAJOR if diff_ratio > 0.5
                else ContradictionSeverity.MODERATE
            )
            return Contradiction(
                fact_a=fa,
                fact_b=fb,
                severity=severity,
                description=(
                    f"Числовое расхождение: {val_a} vs {val_b} "
                    f"(разница {diff_ratio:.0%})"
                ),
            )

        return None

    def _check_textual(
        self,
        fa: ExtractedFact,
        fb: ExtractedFact,
    ) -> Contradiction | None:
        """Проверить текстовые противоречия."""
        text_a = fa.text.lower()
        text_b = fb.text.lower()

        # Проверяем антонимы
        for word_a, word_b in self.CONTRADICTION_PAIRS:
            if word_a in text_a and word_b in text_b:
                return Contradiction(
                    fact_a=fa,
                    fact_b=fb,
                    severity=ContradictionSeverity.MODERATE,
                    description=f"Противоположные утверждения: '{word_a}' vs '{word_b}'",
                )
            if word_b in text_a and word_a in text_b:
                return Contradiction(
                    fact_a=fa,
                    fact_b=fb,
                    severity=ContradictionSeverity.MODERATE,
                    description=f"Противоположные утверждения: '{word_b}' vs '{word_a}'",
                )

        # Проверяем отрицания
        negation_a = any(neg in text_a for neg in self.NEGATION_WORDS)
        negation_b = any(neg in text_b for neg in self.NEGATION_WORDS)

        if negation_a != negation_b:
            # Одно утверждает, другое отрицает
            overlap = set(fa.keywords) & set(fb.keywords)
            if len(overlap) >= 2:
                return Contradiction(
                    fact_a=fa,
                    fact_b=fb,
                    severity=ContradictionSeverity.MINOR,
                    description="Одно утверждение содержит отрицание",
                )

        return None


# ═══════════════════════════════════════════════════════════════════════════════
# 5. FACT SYNTHESIZER — Синтез ответа
# ═══════════════════════════════════════════════════════════════════════════════


class FactSynthesizer:
    """
    Синтезирует итоговый ответ из фактов нескольких источников.

    Стратегии:
    - Weighted voting: факты взвешиваются по trust * confidence
    - Deduplication: удаление дубликатов
    - Citation: ссылки на источники
    """

    def synthesize(
        self,
        query: str,
        facts: list[ExtractedFact],
        sources: list[SourceInfo],
        contradictions: list[Contradiction],
    ) -> SynthesizedAnswer:
        """
        Синтезировать ответ из фактов.

        Args:
            query: Исходный запрос
            facts: Извлечённые факты
            sources: Источники
            contradictions: Найденные противоречия

        Returns:
            SynthesizedAnswer
        """
        if not facts:
            return SynthesizedAnswer(
                query=query,
                summary=f"По запросу «{query}» не найдено достаточно информации.",
                facts=[],
                sources=sources,
                contradictions=contradictions,
                confidence=0.0,
                sources_count=len(sources),
            )

        # 1. Дедупликация фактов
        unique_facts = self._deduplicate(facts)

        # 2. Сортируем по weighted score
        scored = [
            (f, f.confidence * f.source.composite_score)
            for f in unique_facts
        ]
        scored.sort(key=lambda x: x[1], reverse=True)

        # 3. Считаем общую уверенность
        confidence = self._compute_confidence(
            scored, contradictions, len(sources)
        )

        # 4. Собираем summary
        summary = self._build_summary(query, scored, contradictions)

        return SynthesizedAnswer(
            query=query,
            summary=summary,
            facts=[f for f, _ in scored],
            sources=sources,
            contradictions=contradictions,
            confidence=round(confidence, 3),
            sources_count=len(sources),
        )

    def _deduplicate(
        self,
        facts: list[ExtractedFact],
        threshold: float = 0.7,
    ) -> list[ExtractedFact]:
        """Удалить дубликаты (по текстовому сходству)."""
        unique: list[ExtractedFact] = []

        for fact in facts:
            is_dup = False
            for existing in unique:
                if self._text_similarity(fact.text, existing.text) > threshold:
                    # Оставляем факт с большей уверенностью
                    if fact.confidence > existing.confidence:
                        unique.remove(existing)
                        unique.append(fact)
                    is_dup = True
                    break
            if not is_dup:
                unique.append(fact)

        return unique

    def _text_similarity(self, a: str, b: str) -> float:
        """Jaccard similarity по словам."""
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())

        if not words_a or not words_b:
            return 0.0

        intersection = len(words_a & words_b)
        union = len(words_a | words_b)

        return intersection / union if union > 0 else 0.0

    def _compute_confidence(
        self,
        scored_facts: list[tuple[ExtractedFact, float]],
        contradictions: list[Contradiction],
        sources_count: int,
    ) -> float:
        """Вычислить общую уверенность."""
        if not scored_facts:
            return 0.0

        # Среднее взвешенное уверенности
        total_score = sum(s for _, s in scored_facts)
        avg = total_score / len(scored_facts)

        # Бонус за множество источников
        source_bonus = min(0.15, sources_count * 0.03)

        # Штраф за противоречия
        contradiction_penalty = len(contradictions) * 0.1
        major_penalty = sum(
            0.15 for c in contradictions
            if c.severity == ContradictionSeverity.MAJOR
        )

        confidence = avg + source_bonus - contradiction_penalty - major_penalty
        return max(0.0, min(1.0, confidence))

    def _build_summary(
        self,
        query: str,
        scored_facts: list[tuple[ExtractedFact, float]],
        contradictions: list[Contradiction],
    ) -> str:
        """Построить текстовое summary."""
        lines = [f"📋 Результаты исследования: «{query}»\n"]

        # Топ факты
        top_facts = scored_facts[:5]
        if top_facts:
            lines.append("📌 Ключевые факты:")
            for i, (fact, score) in enumerate(top_facts, 1):
                domain = fact.source.domain
                lines.append(
                    f"  {i}. {fact.text[:200]} "
                    f"[{domain}, уверенность: {score:.0%}]"
                )

        # Противоречия
        if contradictions:
            lines.append(f"\n⚠️ Найдено противоречий: {len(contradictions)}")
            for c in contradictions[:3]:
                lines.append(f"  • {c.description}")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. INTERNET REASONING ENGINE — Главный класс
# ═══════════════════════════════════════════════════════════════════════════════


class InternetReasoningEngine:
    """
    Главный класс Internet Reasoning Layer.

    Оркестрирует весь pipeline:
    Query → Expand → Search → Extract → Score → Detect → Synthesize

    Использует Browser Engine для фактического доступа к интернету.
    """

    def __init__(self):
        self._trust_scorer = TrustScorer()
        self._query_expander = QueryExpander()
        self._fact_extractor = FactExtractor()
        self._contradiction_detector = ContradictionDetector()
        self._fact_synthesizer = FactSynthesizer()
        self._stats = ResearchStats()

    @property
    def trust_scorer(self) -> TrustScorer:
        return self._trust_scorer

    @property
    def query_expander(self) -> QueryExpander:
        return self._query_expander

    @property
    def fact_extractor(self) -> FactExtractor:
        return self._fact_extractor

    @property
    def contradiction_detector(self) -> ContradictionDetector:
        return self._contradiction_detector

    @property
    def fact_synthesizer(self) -> FactSynthesizer:
        return self._fact_synthesizer

    @property
    def stats(self) -> ResearchStats:
        return self._stats

    async def research(
        self,
        query: str,
        max_sources: int = 5,
        expand_queries: bool = True,
        max_facts_per_source: int = 5,
    ) -> SynthesizedAnswer:
        """
        Полное исследование вопроса.

        1. Расширяет запрос
        2. Ищет в интернете
        3. Извлекает данные со страниц
        4. Оценивает источники
        5. Извлекает факты
        6. Ищет противоречия
        7. Синтезирует ответ

        Args:
            query: Вопрос для исследования
            max_sources: Максимум источников
            expand_queries: Расширять ли запросы
            max_facts_per_source: Максимум фактов с каждого источника

        Returns:
            SynthesizedAnswer
        """
        import time
        start = time.monotonic()

        from pds_ultimate.core.browser_engine import browser_engine

        # 1. Расширяем запросы
        if expand_queries:
            queries = self._query_expander.expand(query, max_queries=3)
        else:
            queries = [query]

        # 2. Ищем
        all_search_results = []
        seen_urls: set[str] = set()

        for q in queries:
            try:
                results = await browser_engine.web_search(
                    q, max_results=max_sources
                )
                for r in results:
                    if r.url not in seen_urls:
                        all_search_results.append(r)
                        seen_urls.add(r.url)
                self._stats.queries_performed += 1
            except Exception as e:
                logger.warning(f"Search error for '{q}': {e}")

        # 3. Извлекаем данные со страниц
        sources: list[SourceInfo] = []
        all_facts: list[ExtractedFact] = []

        for result in all_search_results[:max_sources]:
            try:
                extracted = await browser_engine.extract_data(result.url)
                self._stats.pages_analyzed += 1

                # Оцениваем источник
                source_info = self._trust_scorer.score_source(
                    url=result.url,
                    title=extracted.title or result.title,
                    content=extracted.text,
                )
                sources.append(source_info)

                # Извлекаем факты
                facts = self._fact_extractor.extract_facts(
                    text=extracted.text,
                    source=source_info,
                    query=query,
                    max_facts=max_facts_per_source,
                )
                all_facts.extend(facts)
                self._stats.facts_extracted += len(facts)

            except Exception as e:
                logger.warning(f"Extract error for {result.url}: {e}")

        # 4. Обнаруживаем противоречия
        contradictions = self._contradiction_detector.detect(all_facts)
        self._stats.contradictions_found += len(contradictions)

        # 5. Синтезируем ответ
        answer = self._fact_synthesizer.synthesize(
            query=query,
            facts=all_facts,
            sources=sources,
            contradictions=contradictions,
        )

        elapsed = int((time.monotonic() - start) * 1000)
        self._stats.total_time_ms += elapsed

        logger.info(
            f"Research '{query[:50]}': "
            f"{len(sources)} sources, {len(all_facts)} facts, "
            f"{len(contradictions)} contradictions, {elapsed}ms"
        )

        return answer

    async def quick_search(
        self,
        query: str,
        max_results: int = 5,
    ) -> SynthesizedAnswer:
        """
        Быстрый поиск без расширения запросов.
        Для простых вопросов.
        """
        return await self.research(
            query=query,
            max_sources=max_results,
            expand_queries=False,
            max_facts_per_source=3,
        )

    async def deep_research(
        self,
        query: str,
        max_sources: int = 10,
    ) -> SynthesizedAnswer:
        """
        Глубокое исследование с расширением и множеством источников.
        Для сложных вопросов.
        """
        return await self.research(
            query=query,
            max_sources=max_sources,
            expand_queries=True,
            max_facts_per_source=8,
        )

    def get_stats(self) -> dict:
        """Статистика исследований."""
        return self._stats.to_dict()

    def reset_stats(self) -> None:
        """Сброс статистики."""
        self._stats = ResearchStats()


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

reasoning_engine = InternetReasoningEngine()
