"""
PDS-Ultimate WhatsApp Integration (Green-API)
================================================
Интеграция с WhatsApp через Green-API (REST API).

По ТЗ:
- 3 последних активных чата для анализа стиля
- Чтение исходящих сообщений владельца
- Green-API — облачный сервис, не нужен браузер
- Требует авторизацию через QR-код в консоли Green-API
"""

from __future__ import annotations

from typing import Optional

import httpx

from pds_ultimate.config import config, logger


class WhatsAppClient:
    """
    Клиент WhatsApp через Green-API (REST).

    Жизненный цикл:
        client = WhatsAppClient()
        await client.start()       # Проверяет авторизацию
        messages = await client.get_recent_messages(chat_id, limit=100)
        await client.stop()        # Закрывает HTTP клиент
    """

    def __init__(self):
        self._http: Optional[httpx.AsyncClient] = None
        self._started = False
        self._instance_id = ""
        self._api_token = ""
        self._base_url = ""

    async def start(self) -> None:
        """Инициализировать клиент и проверить авторизацию."""
        if self._started:
            return

        if not config.whatsapp.enabled:
            logger.warning("WhatsApp отключён (WA_ENABLED=false)")
            return

        self._instance_id = config.whatsapp.green_api_instance
        self._api_token = config.whatsapp.green_api_token

        if not self._instance_id or not self._api_token:
            logger.error(
                "Green-API не настроен: "
                "задайте WA_GREEN_API_INSTANCE и WA_GREEN_API_TOKEN в .env"
            )
            return

        self._base_url = (
            f"https://7103.api.greenapi.com"
            f"/waInstance{self._instance_id}"
        )

        # Прокси для обхода блокировок
        proxy_url = config.telegram.proxy if hasattr(
            config, 'telegram') else ""
        http_kwargs: dict = {"timeout": 30.0}
        if proxy_url:
            http_kwargs["proxy"] = proxy_url
        self._http = httpx.AsyncClient(**http_kwargs)

        # Проверяем статус авторизации
        authorized = await self.is_logged_in()
        if not authorized:
            logger.warning(
                "⚠️ WhatsApp Green-API: Status = Not Authorized!\n"
                "   Зайди в console.green-api.com → "
                "Link with QR code → отсканируй QR телефоном"
            )
        else:
            logger.info("✅ WhatsApp Green-API: авторизован и готов")

        self._started = True
        logger.info("WhatsApp Green-API клиент запущен")

    async def stop(self) -> None:
        """Закрыть HTTP клиент."""
        if self._http:
            try:
                await self._http.aclose()
            except Exception:
                pass
        self._http = None
        self._started = False
        logger.info("WhatsApp Green-API клиент остановлен")

    async def is_logged_in(self) -> bool:
        """Проверить авторизацию через Green-API."""
        if not self._http:
            return False

        try:
            resp = await self._http.get(
                f"{self._base_url}/getStateInstance/{self._api_token}"
            )
            data = resp.json()
            state = data.get("stateInstance", "")
            return state == "authorized"
        except Exception as e:
            logger.error(f"Ошибка проверки статуса WA: {e}")
            return False

    async def get_recent_chats(self, limit: int = 3) -> list[dict]:
        """
        Получить последние активные чаты.

        Returns:
            [{"id": "79001234567@c.us", "name": "Имя контакта"}, ...]
        """
        if not self._started or not self._http:
            return []

        try:
            resp = await self._http.get(
                f"{self._base_url}/getChats/{self._api_token}"
            )
            data = resp.json()

            chats = []
            for chat in data[:limit]:
                chat_id = chat.get("id", "")
                name = chat.get("name", "") or chat_id
                if chat_id and "@c.us" in chat_id:  # Только личные чаты
                    chats.append({"id": chat_id, "name": name})

            logger.info(f"WhatsApp: найдено {len(chats)} чатов")
            return chats

        except Exception as e:
            logger.error(f"Ошибка получения чатов WA: {e}")
            return []

    async def get_recent_messages(
        self,
        chat_id: str,
        limit: int = 100,
        outgoing_only: bool = True,
    ) -> list[dict]:
        """
        Получить последние сообщения из чата через Green-API.

        Args:
            chat_id: ID чата (например "79001234567@c.us")
            limit: Максимум сообщений
            outgoing_only: Только исходящие (для анализа стиля)

        Returns:
            [{"text": "...", "timestamp": 1234567890, "is_outgoing": True}, ...]
        """
        if not self._started or not self._http:
            return []

        try:
            resp = await self._http.post(
                f"{self._base_url}/getChatHistory/{self._api_token}",
                json={"chatId": chat_id, "count": limit},
            )
            data = resp.json()

            messages = []
            for msg in data:
                msg_type = msg.get("type", "")
                # Только текстовые
                if msg_type not in ("outgoing", "incoming"):
                    continue

                is_outgoing = msg_type == "outgoing"
                if outgoing_only and not is_outgoing:
                    continue

                text = msg.get("textMessage", "") or ""
                if not text:
                    # Попробуем extendedTextMessage
                    ext = msg.get("extendedTextMessageData", {})
                    text = ext.get("text", "") if ext else ""

                if text:
                    messages.append({
                        "text": text.strip(),
                        "is_outgoing": is_outgoing,
                        "timestamp": msg.get("timestamp", 0),
                    })

            logger.info(
                f"WhatsApp: {len(messages)} сообщений из чата '{chat_id}'"
            )
            return messages

        except Exception as e:
            logger.error(f"Ошибка чтения сообщений WA '{chat_id}': {e}")
            return []

    async def send_message(self, chat_id: str, text: str) -> bool:
        """Отправить текстовое сообщение."""
        if not self._started or not self._http:
            return False

        try:
            resp = await self._http.post(
                f"{self._base_url}/sendMessage/{self._api_token}",
                json={"chatId": chat_id, "message": text},
            )
            data = resp.json()
            success = "idMessage" in data
            if success:
                logger.info(f"WhatsApp: сообщение отправлено в {chat_id}")
            return success
        except Exception as e:
            logger.error(f"Ошибка отправки WA сообщения: {e}")
            return False

    async def get_style_messages(self) -> list[str]:
        """
        Собрать исходящие сообщения из N чатов для анализа стиля.
        По ТЗ: 3 чата, 100 сообщений из каждого.
        """
        if not self._started:
            logger.warning("WhatsApp не запущен")
            return []

        if not await self.is_logged_in():
            logger.warning(
                "WhatsApp не авторизован — "
                "отсканируй QR в console.green-api.com"
            )
            return []

        all_messages: list[str] = []
        chat_count = config.whatsapp.style_analysis_chat_count
        msg_limit = config.whatsapp.messages_per_chat

        chats = await self.get_recent_chats(limit=chat_count)

        for chat in chats:
            messages = await self.get_recent_messages(
                chat["id"], limit=msg_limit, outgoing_only=True,
            )
            for msg in messages:
                if msg.get("text"):
                    all_messages.append(msg["text"])

        logger.info(
            f"WhatsApp: собрано {len(all_messages)} сообщений "
            f"из {len(chats)} чатов для анализа стиля"
        )
        return all_messages


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

wa_client = WhatsAppClient()
