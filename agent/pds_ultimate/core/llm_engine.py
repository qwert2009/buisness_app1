"""
PDS-Ultimate LLM Engine
=========================
Мозг системы — интерфейс к DeepSeek API.

Возможности:
- Две модели: deepseek-reasoner (мощная) и deepseek-chat (быстрая)
- Автоматический выбор модели по типу задачи
- Retry с экспоненциальным backoff
- Потоковая генерация (streaming)
- Управление контекстом (conversation history)
- Стиль общения (мимикрия) через system prompt
- Универсальный агент: выполняет ЛЮБУЮ задачу
- Структурированный вывод (JSON mode)
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator, Optional

import httpx

from pds_ultimate.config import config, logger

# ─── Системные промпты ──────────────────────────────────────────────────────

SYSTEM_PROMPT_BASE = """Ты — PDS-Ultimate, персональный AI-ассистент высшего класса.
Ты выполняешь ЛЮБЫЕ задачи: бизнес, логистика, финансы, быт, поиск информации,
генерация текстов, расчёты, переводы, работа с файлами и данными.

Ключевые правила:
1. Ты отвечаешь кратко и по делу, если не просят подробнее.
2. Ты всегда на стороне владельца — его интересы превыше всего.
3. Если нужна дополнительная информация — спрашиваешь.
4. Если задача связана с заказами/финансами — следуешь точному протоколу.
5. Ты НЕ говоришь что ты ИИ. Ты — помощник, секретарь, правая рука.
6. Финансовая формула: ДОХОД - ТОВАР = ОСТАТОК - ДОСТАВКА = ЧИСТАЯ ПРИБЫЛЬ.
7. Чистая прибыль делится на: расходы и отложения (проценты задаёт владелец).
8. Налоги и комиссии НЕ считаешь.
9. Курсы: 1 USD = 19.5 TMT, 1 USD = 7.1 CNY, остальные — динамически.
"""

SYSTEM_PROMPT_STYLE_TEMPLATE = """
{base_prompt}

СТИЛЬ ОБЩЕНИЯ ВЛАДЕЛЬЦА (используй при ответах от его имени):
{style_guide}
"""

SYSTEM_PROMPT_ORDER_PARSER = """Ты — парсер заказов. Твоя задача — извлечь из текста
список товарных позиций. Верни СТРОГО JSON массив.

Формат ответа:
[
  {{"name": "название товара", "quantity": число, "unit": "шт/кг/м", "unit_price": цена_или_null, "currency": "USD/CNY/TMT"}},
  ...
]

Правила:
- Если единица измерения не указана — ставь "шт"
- Если цена не указана — ставь null
- Если валюта не указана — ставь "USD"
- Переводи сокращения: "шт" = штуки, "кг" = килограммы
- Числа всегда числами, не строками
"""

SYSTEM_PROMPT_SUMMARIZER = """Ты — сумматор сообщений. Создай краткое саммари
(максимум 2-3 предложения) входящего сообщения. Укажи суть и требуемое действие.
Формат:
СУТЬ: ...
ДЕЙСТВИЕ: ... (если требуется)
"""

SYSTEM_PROMPT_TRANSLATOR = """Ты — профессиональный переводчик.
Переводи точно, сохраняя смысл, тон и стиль оригинала.
Не добавляй комментариев — только перевод."""


# ─── Типы задач (для автовыбора модели) ──────────────────────────────────────

class TaskComplexity:
    """Определяет сложность задачи для выбора модели."""
    # Простые задачи → fast_model (deepseek-chat)
    SIMPLE = "simple"
    # Сложные задачи → main model (deepseek-reasoner)
    COMPLEX = "complex"

    # Маппинг типов задач на сложность
    TASK_MAP = {
        "translate": SIMPLE,
        "summarize": SIMPLE,
        "format": SIMPLE,
        "simple_answer": SIMPLE,
        "parse_order": COMPLEX,
        "analyze_style": COMPLEX,
        "financial_calc": COMPLEX,
        "generate_report": COMPLEX,
        "general": COMPLEX,
        "negotiate": COMPLEX,
    }

    @classmethod
    def get_model(cls, task_type: str) -> str:
        """Получить модель для типа задачи."""
        complexity = cls.TASK_MAP.get(task_type, cls.COMPLEX)
        if complexity == cls.SIMPLE:
            return config.deepseek.fast_model
        return config.deepseek.model


# ─── LLM Engine ─────────────────────────────────────────────────────────────

class LLMEngine:
    """
    Движок LLM — центральный интерфейс к DeepSeek API.

    Использование:
        engine = LLMEngine()
        response = await engine.chat("Привет, как дела?")
        parsed = await engine.parse_order("Балаклавы 100 шт, маски 50 шт")
        translation = await engine.translate("Hello", target_lang="ru")
    """

    def __init__(self):
        self._api_key = config.deepseek.api_key
        self._base_url = config.deepseek.base_url.rstrip("/")
        self._model = config.deepseek.model
        self._fast_model = config.deepseek.fast_model
        self._max_tokens = config.deepseek.max_tokens
        self._temperature = config.deepseek.temperature
        self._timeout = config.deepseek.timeout
        self._max_retries = config.deepseek.max_retries

        # Стиль общения (загружается из БД при старте)
        self._style_guide: Optional[str] = None
        self._system_prompt: str = SYSTEM_PROMPT_BASE

        # HTTP клиент (persistent connection)
        self._client: Optional[httpx.AsyncClient] = None

        logger.info(
            f"LLM Engine инициализирован: model={self._model}, "
            f"fast_model={self._fast_model}"
        )

    # ─── Lifecycle ───────────────────────────────────────────────────────

    async def start(self) -> None:
        """Запустить движок (создать HTTP клиент)."""
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(self._timeout, connect=30.0),
        )
        logger.info("LLM Engine запущен")

    async def stop(self) -> None:
        """Остановить движок (закрыть HTTP клиент)."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("LLM Engine остановлен")

    # ─── Стиль общения ──────────────────────────────────────────────────

    def set_style_guide(self, style_guide: str) -> None:
        """Установить стиль общения (мимикрия)."""
        self._style_guide = style_guide
        self._system_prompt = SYSTEM_PROMPT_STYLE_TEMPLATE.format(
            base_prompt=SYSTEM_PROMPT_BASE,
            style_guide=style_guide,
        )
        logger.info("Стиль общения обновлён в LLM Engine")

    # ─── Основные методы ─────────────────────────────────────────────────

    async def chat(
        self,
        message: str,
        history: Optional[list[dict]] = None,
        system_prompt: Optional[str] = None,
        task_type: str = "general",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        """
        Основной метод общения с LLM.

        Args:
            message: Сообщение пользователя
            history: История разговора [{role, content}, ...]
            system_prompt: Кастомный системный промпт (иначе — дефолтный)
            task_type: Тип задачи для автовыбора модели
            temperature: Температура (иначе — из конфига)
            max_tokens: Макс. токенов (иначе — из конфига)
            json_mode: Ответ в формате JSON

        Returns:
            Текст ответа от LLM
        """
        model = TaskComplexity.get_model(task_type)
        messages = self._build_messages(message, history, system_prompt)

        response = await self._request(
            model=model,
            messages=messages,
            temperature=temperature or self._temperature,
            max_tokens=max_tokens or self._max_tokens,
            json_mode=json_mode,
        )

        return response

    async def chat_stream(
        self,
        message: str,
        history: Optional[list[dict]] = None,
        system_prompt: Optional[str] = None,
        task_type: str = "general",
    ) -> AsyncGenerator[str, None]:
        """
        Потоковая генерация ответа.
        Возвращает токены по мере их генерации.
        """
        model = TaskComplexity.get_model(task_type)
        messages = self._build_messages(message, history, system_prompt)

        async for chunk in self._request_stream(
            model=model,
            messages=messages,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        ):
            yield chunk

    # ─── Специализированные методы ───────────────────────────────────────

    async def parse_order(self, text: str) -> list[dict]:
        """
        Парсинг заказа из текста.
        Возвращает список позиций в формате JSON.
        """
        response = await self.chat(
            message=text,
            system_prompt=SYSTEM_PROMPT_ORDER_PARSER,
            task_type="parse_order",
            temperature=0.1,  # Минимальная креативность для точности
            json_mode=True,
        )

        try:
            result = json.loads(response)
            if isinstance(result, list):
                return result
            # Если вернул объект с ключом
            for key in ("items", "positions", "order", "data"):
                if key in result and isinstance(result[key], list):
                    return result[key]
            logger.warning(
                f"Неожиданный формат парсинга заказа: {type(result)}")
            return []
        except json.JSONDecodeError:
            # Попытка извлечь JSON из текста
            return self._extract_json_from_text(response)

    async def summarize(self, text: str) -> str:
        """Создать краткое саммари текста."""
        return await self.chat(
            message=text,
            system_prompt=SYSTEM_PROMPT_SUMMARIZER,
            task_type="summarize",
            temperature=0.3,
        )

    async def translate(
        self,
        text: str,
        target_lang: str = "ru",
        source_lang: Optional[str] = None,
    ) -> str:
        """Перевод текста."""
        lang_info = f"на {target_lang}"
        if source_lang:
            lang_info = f"с {source_lang} {lang_info}"

        prompt = f"Переведи следующий текст {lang_info}:\n\n{text}"

        return await self.chat(
            message=prompt,
            system_prompt=SYSTEM_PROMPT_TRANSLATOR,
            task_type="translate",
            temperature=0.2,
        )

    async def generate_in_style(
        self,
        instruction: str,
        recipient_context: Optional[str] = None,
    ) -> str:
        """
        Генерация текста в стиле владельца (мимикрия).
        Для ответов клиентам, поставщикам и т.д.
        """
        context = ""
        if recipient_context:
            context = f"\nКонтекст о собеседнике: {recipient_context}"

        prompt = f"{instruction}{context}"

        return await self.chat(
            message=prompt,
            system_prompt=self._system_prompt,  # Включает стиль
            task_type="general",
            temperature=0.7,
        )

    async def extract_intent(self, message: str) -> dict:
        """
        Определить намерение пользователя.
        Возвращает: {"intent": "...", "entities": {...}, "confidence": 0.0-1.0}

        Интенты:
        - new_order: Новый заказ
        - order_status: Запрос статуса
        - add_items: Добавить позиции
        - finance_query: Финансовый запрос
        - set_income: Установить доход за заказ
        - set_expense: Установить расход за заказ
        - delivery_cost: Ввод стоимости доставки
        - create_file: Создать файл
        - edit_file: Редактировать файл
        - calendar_event: Событие в календарь
        - contact_note: Заметка о контакте
        - vip_manage: Управление VIP
        - translate: Перевод
        - general: Свободная задача (ЛЮБАЯ)
        """
        system = """Определи намерение (intent) пользователя из сообщения.
Верни СТРОГО JSON:
{
  "intent": "одно из: new_order, order_status, add_items, finance_query,
             set_income, set_expense, delivery_cost, create_file, edit_file,
             calendar_event, contact_note, vip_manage, translate,
             security_emergency, morning_brief, report, general",
  "entities": {
    "order_number": "если упомянут",
    "amount": "если есть сумма",
    "currency": "если указана валюта",
    "contact_name": "если упомянут контакт",
    "date": "если указана дата",
    "file_name": "если упомянут файл",
    "items": "если есть список товаров"
  },
  "confidence": 0.95
}
Поля entities опциональны — заполняй только найденные."""

        response = await self.chat(
            message=message,
            system_prompt=system,
            task_type="parse_order",
            temperature=0.1,
            json_mode=True,
        )

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            extracted = self._extract_json_from_text(response)
            if extracted:
                return extracted[0] if isinstance(extracted, list) else extracted
            return {"intent": "general", "entities": {}, "confidence": 0.5}

    # ─── Внутренние методы ───────────────────────────────────────────────

    def _build_messages(
        self,
        message: str,
        history: Optional[list[dict]] = None,
        system_prompt: Optional[str] = None,
    ) -> list[dict]:
        """Построить массив сообщений для API."""
        messages = [
            {"role": "system", "content": system_prompt or self._system_prompt}
        ]

        if history:
            messages.extend(history)

        messages.append({"role": "user", "content": message})
        return messages

    async def _request(
        self,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        json_mode: bool = False,
    ) -> str:
        """
        Отправить запрос к DeepSeek API с retry.
        """
        if not self._client:
            await self.start()

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        last_error = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._client.post(
                    "/v1/chat/completions",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                logger.debug(
                    f"LLM response: model={model}, "
                    f"tokens={usage.get('total_tokens', '?')}, "
                    f"attempt={attempt}"
                )
                return content.strip()

            except httpx.HTTPStatusError as e:
                last_error = e
                status = e.response.status_code
                if status == 429:
                    # Rate limit — ждём подольше
                    wait = min(2 ** attempt * 5, 60)
                    logger.warning(
                        f"Rate limit, ожидание {wait}с (попытка {attempt})")
                    await asyncio.sleep(wait)
                elif status >= 500:
                    wait = 2 ** attempt
                    logger.warning(
                        f"Серверная ошибка {status}, ожидание {wait}с")
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"HTTP ошибка {status}: {e.response.text}")
                    raise

            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                last_error = e
                wait = 2 ** attempt
                logger.warning(
                    f"Сетевая ошибка: {type(e).__name__}, "
                    f"ожидание {wait}с (попытка {attempt})"
                )
                await asyncio.sleep(wait)

            except Exception as e:
                logger.error(
                    f"Неожиданная ошибка LLM: {type(e).__name__}: {e}")
                raise

        raise ConnectionError(
            f"DeepSeek API недоступен после {self._max_retries} попыток: {last_error}"
        )

    async def _request_stream(
        self,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[str, None]:
        """Потоковый запрос к DeepSeek API."""
        if not self._client:
            await self.start()

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        try:
            async with self._client.stream(
                "POST", "/v1/chat/completions", json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except Exception as e:
            logger.error(f"Ошибка стриминга: {type(e).__name__}: {e}")
            raise

    @staticmethod
    def _extract_json_from_text(text: str) -> list | dict:
        """Извлечь JSON из текста (если LLM вернул его внутри markdown)."""
        import re

        # Попытка 1: найти ```json ... ```
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Попытка 2: найти [...] или {...}
        for pattern in [r"\[[\s\S]*\]", r"\{[\s\S]*\}"]:
            match = re.search(pattern, text)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass

        logger.warning(f"Не удалось извлечь JSON из текста: {text[:200]}")
        return []


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

llm_engine = LLMEngine()
