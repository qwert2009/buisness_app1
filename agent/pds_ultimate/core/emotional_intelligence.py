"""
PDS-Ultimate Emotional & Social Intelligence Engine
=====================================================
Эмоциональный и социальный интеллект агента мирового уровня.

Компоненты:
1. SentimentAnalyzer — определение эмоционального тона сообщения
2. EmotionalStateTracker — отслеживание эмоционального состояния пользователя
3. EmpathyEngine — генерация эмпатических реакций
4. SocialContextAdapter — адаптация стиля под социальный контекст
5. EmotionalIntelligenceEngine — главный оркестратор

Без внешних API — полностью на паттернах + DeepSeek для сложных случаев.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum

from pds_ultimate.config import logger

# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS & DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class Emotion(str, Enum):
    """Базовые эмоции (Плутчик + бизнес-контекст)."""
    JOY = "joy"
    TRUST = "trust"
    FEAR = "fear"
    SURPRISE = "surprise"
    SADNESS = "sadness"
    ANGER = "anger"
    ANTICIPATION = "anticipation"
    FRUSTRATION = "frustration"
    CONFUSION = "confusion"
    URGENCY = "urgency"
    GRATITUDE = "gratitude"
    NEUTRAL = "neutral"


class CommunicationStyle(str, Enum):
    """Стиль общения пользователя."""
    FORMAL = "formal"
    INFORMAL = "informal"
    TECHNICAL = "technical"
    EMOTIONAL = "emotional"
    BRIEF = "brief"
    DETAILED = "detailed"


class ResponseTone(str, Enum):
    """Тон ответа агента."""
    PROFESSIONAL = "professional"
    EMPATHETIC = "empathetic"
    ENCOURAGING = "encouraging"
    URGENT = "urgent"
    CALM = "calm"
    CELEBRATORY = "celebratory"
    SUPPORTIVE = "supportive"


@dataclass
class EmotionScore:
    """Оценка эмоции в сообщении."""
    emotion: Emotion
    intensity: float  # 0.0 - 1.0
    confidence: float  # 0.0 - 1.0

    def __repr__(self) -> str:
        return f"{self.emotion.value}({self.intensity:.0%})"


@dataclass
class EmotionalState:
    """Эмоциональное состояние пользователя."""
    primary_emotion: Emotion = Emotion.NEUTRAL
    secondary_emotion: Emotion | None = None
    intensity: float = 0.5
    trend: str = "stable"  # rising, falling, stable
    history: list[Emotion] = field(default_factory=list)
    stress_level: float = 0.0  # 0.0 - 1.0
    satisfaction: float = 0.5  # 0.0 - 1.0
    last_updated: float = 0.0

    def to_dict(self) -> dict:
        return {
            "primary": self.primary_emotion.value,
            "secondary": self.secondary_emotion.value if self.secondary_emotion else None,
            "intensity": round(self.intensity, 2),
            "trend": self.trend,
            "stress": round(self.stress_level, 2),
            "satisfaction": round(self.satisfaction, 2),
            "history_len": len(self.history),
        }


@dataclass
class SocialContext:
    """Социальный контекст взаимодействия."""
    communication_style: CommunicationStyle = CommunicationStyle.INFORMAL
    formality_level: float = 0.5  # 0 = очень неформальный, 1 = очень формальный
    language_complexity: float = 0.5  # 0 = простой, 1 = технический
    urgency_level: float = 0.0
    relationship_depth: float = 0.0  # 0 = новый, 1 = давний пользователь
    interaction_count: int = 0


@dataclass
class EmpathicResponse:
    """Эмпатическая реакция агента."""
    tone: ResponseTone
    prefix: str  # Эмпатическая фраза перед ответом
    style_hints: dict = field(default_factory=dict)
    should_ask_followup: bool = False
    suggested_followup: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# EMOTION PATTERNS (rule-based)
# ═══════════════════════════════════════════════════════════════════════════════

# Русский + English паттерны
EMOTION_PATTERNS: dict[Emotion, list[str]] = {
    Emotion.JOY: [
        r"спасибо|благодар|отлично|супер|класс|круто|замечательно|прекрасно",
        r"ура|ураа|yay|great|awesome|excellent|perfect|wonderful|amazing",
        r"👍|🎉|😊|😄|❤️|🔥|💪|🥳|👏|✨",
    ],
    Emotion.ANGER: [
        r"бесит|злость|раздраж|ненавижу|какого чёрт|damn|angry|furious",
        r"идиот|тупой|дурак|wtf|shit|черт|какого хрен",
        r"😡|🤬|💢|👎",
    ],
    Emotion.FRUSTRATION: [
        r"не работает|опять|снова|уже .* раз|не понимаю зачем",
        r"сколько можно|надоело|достало|устал от|замучил",
        r"doesn.t work|not working|broken|stuck|can.t figure",
        r"😤|😩|🙄|😑",
    ],
    Emotion.SADNESS: [
        r"грустно|печаль|жаль|к сожалению|unfortunately|sad|sorry|lost",
        r"потерял|лишился|не получилось|провал|failed|disappointed",
        r"😢|😭|💔|😞|😔",
    ],
    Emotion.FEAR: [
        r"боюсь|страшно|тревожно|волнуюсь|afraid|scared|worried|anxious",
        r"рискованно|опасно|dangerous|risky|nervous",
        r"😰|😨|😱|🥺",
    ],
    Emotion.SURPRISE: [
        r"ого|вау|wow|неожиданно|серьёзно|really|omg|oh my",
        r"не может быть|не верю|amazing|incredible|unbelievable",
        r"😲|😮|🤯|😳",
    ],
    Emotion.URGENCY: [
        r"срочно|быстро|скорее|немедленно|asap|urgent|hurry|deadline",
        r"горит|пожар|критично|emergency|important|right now",
        r"🆘|⚠️|🚨|‼️|❗",
    ],
    Emotion.CONFUSION: [
        r"не понимаю|запутал|confused|what\?|как это|зачем|why|huh",
        r"не ясно|объясни|explain|unclear|don.t understand|не разбираюсь",
        r"🤔|❓|😕|🤷",
    ],
    Emotion.GRATITUDE: [
        r"спасибо большое|огромное спасибо|thank you so much|thanks a lot",
        r"ты лучший|выручил|помог|appreciate|grateful|thanks|thx",
        r"🙏|💐|🌟",
    ],
    Emotion.ANTICIPATION: [
        r"жду|ожидаю|интересно|curious|looking forward|can.t wait",
        r"когда будет|что дальше|what.s next|excited about",
    ],
    Emotion.TRUST: [
        r"доверяю|полагаюсь|trust|rely|count on|depend on",
        r"уверен что ты|верю что|i believe",
    ],
}

# Маркеры формальности
FORMAL_MARKERS = [
    r"уважаем|пожалуйста|будьте добры|прошу|извините|соблаговол",
    r"please|kindly|would you|could you|I would appreciate",
    r"dear|regards|sincerely|Вы\b|Ваш\b",
]

INFORMAL_MARKERS = [
    r"привет|хай|yo|hey|здарова|чё|ну|типа|короче",
    r"ок|окей|ok|lol|haha|хаха|ахах|😂|🤣",
    r"\bты\b|\bтвой\b|\bтебе\b|bro|dude|man",
]

# Эмпатические фразы по эмоциям
EMPATHY_RESPONSES: dict[Emotion, list[str]] = {
    Emotion.JOY: [
        "Рад, что всё хорошо! ",
        "Отличные новости! ",
        "Приятно слышать! ",
    ],
    Emotion.ANGER: [
        "Понимаю ваше раздражение. ",
        "Я вижу, что ситуация непростая. ",
        "Давайте разберёмся спокойно. ",
    ],
    Emotion.FRUSTRATION: [
        "Понимаю, это может быть неприятно. ",
        "Давайте решим эту проблему. ",
        "Я постараюсь помочь разобраться. ",
    ],
    Emotion.SADNESS: [
        "Мне жаль это слышать. ",
        "Понимаю ваши чувства. ",
        "Давайте посмотрим, что можно сделать. ",
    ],
    Emotion.FEAR: [
        "Не беспокойтесь, разберёмся. ",
        "Понимаю вашу тревогу. Давайте оценим риски. ",
        "Я помогу минимизировать риски. ",
    ],
    Emotion.URGENCY: [
        "Понял, действую быстро! ",
        "Принято! Приоритетная задача. ",
        "Срочно! Начинаю прямо сейчас. ",
    ],
    Emotion.CONFUSION: [
        "Давайте разберёмся по шагам. ",
        "Хороший вопрос, объясню подробнее. ",
        "Понимаю, может быть непонятно. Вот как это работает: ",
    ],
    Emotion.GRATITUDE: [
        "Всегда рад помочь! ",
        "Обращайтесь в любое время! ",
        "Рад, что смог помочь! ",
    ],
    Emotion.NEUTRAL: [
        "",  # Нейтральный — без префикса
    ],
    Emotion.SURPRISE: [
        "Да, это интересный момент! ",
        "Неожиданно, правда? ",
    ],
    Emotion.ANTICIPATION: [
        "Скоро всё будет готово! ",
        "Интересный вопрос, давайте изучим. ",
    ],
    Emotion.TRUST: [
        "Спасибо за доверие! ",
        "Не подведу! ",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SENTIMENT ANALYZER
# ═══════════════════════════════════════════════════════════════════════════════


class SentimentAnalyzer:
    """
    Анализатор эмоций на основе паттернов.
    Быстрый rule-based анализ без внешних API.
    """

    def __init__(self):
        self._compiled_patterns: dict[Emotion, list[re.Pattern]] = {}
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Компилируем regex паттерны."""
        for emotion, patterns in EMOTION_PATTERNS.items():
            self._compiled_patterns[emotion] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]

    def analyze(self, text: str) -> list[EmotionScore]:
        """
        Проанализировать текст на эмоции.

        Returns:
            Список EmotionScore, отсортированный по интенсивности
        """
        if not text or not text.strip():
            return [EmotionScore(Emotion.NEUTRAL, 0.5, 0.9)]

        scores: dict[Emotion, float] = {}
        text_lower = text.lower()
        text_len = len(text_lower.split())

        for emotion, patterns in self._compiled_patterns.items():
            total_matches = 0
            for pattern in patterns:
                matches = pattern.findall(text_lower)
                total_matches += len(matches)

            if total_matches > 0:
                # Нормализуем по длине текста
                raw_intensity = min(1.0, total_matches / max(1, text_len / 5))
                # Эмоджи дают больше уверенности
                emoji_boost = 0.1 if any(
                    c in text for c in "😊😄😡😤😢😰🤔😲🙏❤️🔥"
                ) else 0.0
                scores[emotion] = min(1.0, raw_intensity + emoji_boost)

        if not scores:
            return [EmotionScore(Emotion.NEUTRAL, 0.5, 0.8)]

        # Сортируем по силе
        result = [
            EmotionScore(
                emotion=em,
                intensity=round(score, 2),
                confidence=round(min(0.95, 0.5 + score * 0.4), 2),
            )
            for em, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)
        ]

        return result[:5]  # Топ-5 эмоций

    def detect_primary(self, text: str) -> Emotion:
        """Определить главную эмоцию."""
        scores = self.analyze(text)
        return scores[0].emotion if scores else Emotion.NEUTRAL

    def detect_formality(self, text: str) -> float:
        """
        Определить уровень формальности (0 = неформальный, 1 = формальный).
        """
        text_lower = text.lower()

        formal_count = 0
        for pattern in FORMAL_MARKERS:
            if re.search(pattern, text_lower):
                formal_count += 1

        informal_count = 0
        for pattern in INFORMAL_MARKERS:
            if re.search(pattern, text_lower):
                informal_count += 1

        total = formal_count + informal_count
        if total == 0:
            return 0.5

        return round(formal_count / total, 2)

    def detect_urgency(self, text: str) -> float:
        """Определить уровень срочности (0-1)."""
        scores = self.analyze(text)
        for s in scores:
            if s.emotion == Emotion.URGENCY:
                return s.intensity
        # Доп. проверка на восклицания и caps
        exclamation_ratio = text.count("!") / max(1, len(text.split()))
        caps_ratio = sum(1 for c in text if c.isupper()) / max(1, len(text))
        urgency = min(1.0, exclamation_ratio * 2 + caps_ratio * 0.5)
        return round(urgency, 2)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. EMOTIONAL STATE TRACKER
# ═══════════════════════════════════════════════════════════════════════════════


class EmotionalStateTracker:
    """
    Отслеживает эмоциональное состояние пользователя во времени.
    Один экземпляр на пользователя.
    """

    MAX_HISTORY = 50

    def __init__(self):
        self._states: dict[int, EmotionalState] = {}  # user_id → state

    def get_state(self, user_id: int) -> EmotionalState:
        """Получить текущее состояние пользователя."""
        if user_id not in self._states:
            self._states[user_id] = EmotionalState()
        return self._states[user_id]

    def update(
        self,
        user_id: int,
        emotions: list[EmotionScore],
    ) -> EmotionalState:
        """
        Обновить состояние на основе новых эмоций.
        Использует EMA (exponential moving average) для сглаживания.
        """
        state = self.get_state(user_id)
        now = time.time()

        if not emotions:
            return state

        primary = emotions[0]
        secondary = emotions[1] if len(emotions) > 1 else None

        # EMA smoothing (alpha = 0.3)
        alpha = 0.3
        new_intensity = alpha * primary.intensity + \
            (1 - alpha) * state.intensity

        # Определяем тренд
        prev = state.primary_emotion
        if primary.emotion == prev:
            if new_intensity > state.intensity + 0.1:
                trend = "rising"
            elif new_intensity < state.intensity - 0.1:
                trend = "falling"
            else:
                trend = "stable"
        else:
            trend = "changed"

        # Обновляем stress
        stress_emotions = {Emotion.ANGER,
                           Emotion.FRUSTRATION, Emotion.FEAR, Emotion.URGENCY}
        if primary.emotion in stress_emotions:
            stress = min(1.0, state.stress_level + 0.15)
        else:
            stress = max(0.0, state.stress_level - 0.05)

        # Обновляем satisfaction
        positive = {Emotion.JOY, Emotion.GRATITUDE, Emotion.TRUST}
        negative = {Emotion.ANGER, Emotion.FRUSTRATION, Emotion.SADNESS}
        if primary.emotion in positive:
            satisfaction = min(1.0, state.satisfaction + 0.1)
        elif primary.emotion in negative:
            satisfaction = max(0.0, state.satisfaction - 0.1)
        else:
            satisfaction = state.satisfaction

        # Обновляем историю
        history = state.history[-self.MAX_HISTORY:] + [primary.emotion]

        new_state = EmotionalState(
            primary_emotion=primary.emotion,
            secondary_emotion=secondary.emotion if secondary else None,
            intensity=round(new_intensity, 2),
            trend=trend,
            history=history,
            stress_level=round(stress, 2),
            satisfaction=round(satisfaction, 2),
            last_updated=now,
        )

        self._states[user_id] = new_state
        return new_state

    def get_mood_summary(self, user_id: int) -> str:
        """Текстовое описание настроения."""
        state = self.get_state(user_id)

        mood_map = {
            Emotion.JOY: "позитивное",
            Emotion.ANGER: "раздражённое",
            Emotion.FRUSTRATION: "разочарованное",
            Emotion.SADNESS: "грустное",
            Emotion.FEAR: "тревожное",
            Emotion.URGENCY: "напряжённое",
            Emotion.CONFUSION: "озадаченное",
            Emotion.GRATITUDE: "благодарное",
            Emotion.NEUTRAL: "нейтральное",
            Emotion.SURPRISE: "удивлённое",
            Emotion.ANTICIPATION: "ожидающее",
            Emotion.TRUST: "доверительное",
        }

        mood = mood_map.get(state.primary_emotion, "неопределённое")
        stress = "высокий" if state.stress_level > 0.6 else \
                 "средний" if state.stress_level > 0.3 else "низкий"

        return f"Настроение: {mood}, стресс: {stress}, тренд: {state.trend}"

    def get_stats(self) -> dict:
        """Статистика трекера."""
        return {
            "tracked_users": len(self._states),
            "states": {
                uid: s.to_dict() for uid, s in self._states.items()
            },
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. EMPATHY ENGINE
# ═══════════════════════════════════════════════════════════════════════════════


class EmpathyEngine:
    """
    Генерирует эмпатические реакции на основе эмоционального состояния.
    """

    def generate_response(
        self,
        state: EmotionalState,
        social: SocialContext,
    ) -> EmpathicResponse:
        """
        Сгенерировать эмпатическую реакцию.

        Args:
            state: Эмоциональное состояние пользователя
            social: Социальный контекст

        Returns:
            EmpathicResponse с тоном и префиксом
        """
        emotion = state.primary_emotion
        intensity = state.intensity

        # Определяем тон ответа
        tone = self._select_tone(emotion, intensity, state.stress_level)

        # Выбираем эмпатическую фразу
        prefixes = EMPATHY_RESPONSES.get(
            emotion, EMPATHY_RESPONSES[Emotion.NEUTRAL])
        prefix_idx = min(len(prefixes) - 1, int(intensity * len(prefixes)))
        prefix = prefixes[prefix_idx]

        # Адаптируем под формальность
        if social.formality_level > 0.7:
            prefix = self._formalize(prefix)

        # Нужен ли follow-up?
        should_followup = (
            emotion in (Emotion.FRUSTRATION,
                        Emotion.CONFUSION, Emotion.SADNESS)
            and intensity > 0.6
        )

        followup = ""
        if should_followup:
            followup = self._generate_followup(emotion)

        # Style hints для LLM
        style_hints = {
            "tone": tone.value,
            "formality": social.formality_level,
            "brevity": social.communication_style == CommunicationStyle.BRIEF,
            "empathy_level": min(1.0, intensity * 1.2),
        }

        return EmpathicResponse(
            tone=tone,
            prefix=prefix,
            style_hints=style_hints,
            should_ask_followup=should_followup,
            suggested_followup=followup,
        )

    def _select_tone(
        self,
        emotion: Emotion,
        intensity: float,
        stress: float,
    ) -> ResponseTone:
        """Выбрать тон ответа."""
        if emotion == Emotion.JOY and intensity > 0.7:
            return ResponseTone.CELEBRATORY
        if emotion == Emotion.URGENCY:
            return ResponseTone.URGENT
        if emotion in (Emotion.ANGER, Emotion.FRUSTRATION):
            return ResponseTone.CALM if stress > 0.5 else ResponseTone.SUPPORTIVE
        if emotion in (Emotion.SADNESS, Emotion.FEAR):
            return ResponseTone.EMPATHETIC
        if emotion == Emotion.CONFUSION:
            return ResponseTone.SUPPORTIVE
        if emotion == Emotion.GRATITUDE:
            return ResponseTone.ENCOURAGING
        return ResponseTone.PROFESSIONAL

    def _formalize(self, text: str) -> str:
        """Повысить формальность фразы."""
        replacements = {
            "Рад,": "Приятно отметить,",
            "Отличные новости!": "Хорошие результаты.",
            "Понял,": "Принято к сведению,",
            "Не беспокойтесь": "Не стоит беспокоиться",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

    def _generate_followup(self, emotion: Emotion) -> str:
        """Сгенерировать уточняющий вопрос."""
        followups = {
            Emotion.FRUSTRATION: "Хотите, чтобы я попробовал другой подход?",
            Emotion.CONFUSION: "Что именно вызывает вопросы? Объясню подробнее.",
            Emotion.SADNESS: "Могу ли я чем-то ещё помочь?",
            Emotion.FEAR: "Хотите, чтобы я оценил все возможные риски?",
        }
        return followups.get(emotion, "Нужна ли дополнительная помощь?")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. SOCIAL CONTEXT ADAPTER
# ═══════════════════════════════════════════════════════════════════════════════


class SocialContextAdapter:
    """
    Адаптирует стиль общения под пользователя.
    Учитывает историю взаимодействий.
    """

    def __init__(self):
        self._contexts: dict[int, SocialContext] = {}

    def get_context(self, user_id: int) -> SocialContext:
        """Получить социальный контекст пользователя."""
        if user_id not in self._contexts:
            self._contexts[user_id] = SocialContext()
        return self._contexts[user_id]

    def update_from_message(
        self,
        user_id: int,
        text: str,
        analyzer: SentimentAnalyzer,
    ) -> SocialContext:
        """Обновить контекст на основе нового сообщения."""
        ctx = self.get_context(user_id)

        # Формальность
        formality = analyzer.detect_formality(text)
        # EMA smoothing
        alpha = 0.4
        ctx.formality_level = round(
            alpha * formality + (1 - alpha) * ctx.formality_level, 2
        )

        # Определяем стиль
        if ctx.formality_level > 0.7:
            ctx.communication_style = CommunicationStyle.FORMAL
        elif ctx.formality_level < 0.3:
            ctx.communication_style = CommunicationStyle.INFORMAL
        elif len(text.split()) < 5:
            ctx.communication_style = CommunicationStyle.BRIEF
        else:
            ctx.communication_style = CommunicationStyle.INFORMAL

        # Сложность языка
        avg_word_len = (
            sum(len(w) for w in text.split()) / max(1, len(text.split()))
        )
        if avg_word_len > 7:
            ctx.language_complexity = min(1.0, ctx.language_complexity + 0.1)
        else:
            ctx.language_complexity = max(0.0, ctx.language_complexity - 0.05)

        # Срочность
        ctx.urgency_level = analyzer.detect_urgency(text)

        # Глубина отношений (растёт с взаимодействиями)
        ctx.interaction_count += 1
        ctx.relationship_depth = min(1.0, ctx.interaction_count / 100)

        return ctx

    def get_style_prompt(self, user_id: int) -> str:
        """Получить промпт для LLM на основе контекста."""
        ctx = self.get_context(user_id)

        parts = []
        if ctx.formality_level > 0.7:
            parts.append("Используй формальный стиль, обращение на «Вы».")
        elif ctx.formality_level < 0.3:
            parts.append(
                "Используй дружеский неформальный стиль, обращение на «ты».")

        if ctx.communication_style == CommunicationStyle.BRIEF:
            parts.append("Будь кратким, давай только суть.")
        elif ctx.communication_style == CommunicationStyle.DETAILED:
            parts.append("Давай подробные развёрнутые ответы.")

        if ctx.urgency_level > 0.6:
            parts.append("Отвечай максимально быстро и по существу.")

        if ctx.relationship_depth > 0.5:
            parts.append(
                "Это постоянный пользователь, можно ссылаться на прошлый опыт.")

        return " ".join(parts) if parts else ""


# ═══════════════════════════════════════════════════════════════════════════════
# 5. EMOTIONAL INTELLIGENCE ENGINE — Главный оркестратор
# ═══════════════════════════════════════════════════════════════════════════════


class EmotionalIntelligenceEngine:
    """
    Главный класс эмоционального интеллекта.

    Оркестрирует:
    - Анализ эмоций → Обновление состояния → Генерация эмпатии → Адаптация стиля
    """

    def __init__(self):
        self._analyzer = SentimentAnalyzer()
        self._tracker = EmotionalStateTracker()
        self._empathy = EmpathyEngine()
        self._social = SocialContextAdapter()

    @property
    def analyzer(self) -> SentimentAnalyzer:
        return self._analyzer

    @property
    def tracker(self) -> EmotionalStateTracker:
        return self._tracker

    @property
    def empathy(self) -> EmpathyEngine:
        return self._empathy

    @property
    def social(self) -> SocialContextAdapter:
        return self._social

    def process_message(
        self,
        user_id: int,
        text: str,
    ) -> EmpathicResponse:
        """
        Полный pipeline обработки сообщения.

        1. Анализируем эмоции
        2. Обновляем состояние
        3. Обновляем социальный контекст
        4. Генерируем эмпатическую реакцию

        Args:
            user_id: ID пользователя
            text: Текст сообщения

        Returns:
            EmpathicResponse с рекомендациями для ответа
        """
        # 1. Анализ эмоций
        emotions = self._analyzer.analyze(text)

        # 2. Обновляем эмоциональное состояние
        state = self._tracker.update(user_id, emotions)

        # 3. Обновляем социальный контекст
        social_ctx = self._social.update_from_message(
            user_id, text, self._analyzer,
        )

        # 4. Генерируем эмпатическую реакцию
        response = self._empathy.generate_response(state, social_ctx)

        logger.debug(
            f"EQ[{user_id}]: {state.primary_emotion.value} "
            f"(intensity={state.intensity}, stress={state.stress_level}) "
            f"→ tone={response.tone.value}"
        )

        return response

    def get_emotional_context(self, user_id: int) -> str:
        """
        Получить эмоциональный контекст для system prompt LLM.
        """
        state = self._tracker.get_state(user_id)
        social = self._social.get_context(user_id)
        mood = self._tracker.get_mood_summary(user_id)
        style = self._social.get_style_prompt(user_id)

        parts = [f"[Эмоциональный контекст пользователя: {mood}]"]

        if state.stress_level > 0.5:
            parts.append(
                "⚠️ Пользователь находится в состоянии стресса — будь особенно внимательным.")

        if state.satisfaction < 0.3:
            parts.append(
                "Удовлетворённость низкая — постарайся улучшить опыт.")

        if style:
            parts.append(f"[Стиль: {style}]")

        return "\n".join(parts)

    def get_stats(self) -> dict:
        """Статистика EQ engine."""
        return {
            "tracked_users": len(self._tracker._states),
            "social_contexts": len(self._social._contexts),
        }


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

emotional_engine = EmotionalIntelligenceEngine()
