"""
PDS-Ultimate WhatsApp Integration
====================================
Интеграция с WhatsApp через Playwright (browser automation).

По ТЗ:
- 3 последних активных чата для анализа стиля
- Чтение исходящих сообщений владельца
- Playwright управляет WhatsApp Web
- Headless режим (WA_HEADLESS=true)
- Данные браузера сохраняются для повторных сессий
"""

from __future__ import annotations

import asyncio
from typing import Optional

from pds_ultimate.config import config, logger


class WhatsAppClient:
    """
    Клиент WhatsApp Web через Playwright.

    Жизненный цикл:
        client = WhatsAppClient()
        await client.start()       # Открывает браузер
        messages = await client.get_recent_messages(chat_name, limit=100)
        await client.stop()        # Закрывает браузер
    """

    def __init__(self):
        self._browser = None
        self._context = None
        self._page = None
        self._started = False

    async def start(self) -> None:
        """Запустить браузер и открыть WhatsApp Web."""
        if self._started:
            return

        if not config.whatsapp.enabled:
            logger.warning("WhatsApp отключён (WA_ENABLED=false)")
            return

        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()

            # Убеждаемся что директория для данных браузера существует
            browser_data = config.whatsapp.browser_data_dir
            browser_data.mkdir(parents=True, exist_ok=True)

            self._browser = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(browser_data),
                headless=config.whatsapp.headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )

            self._page = self._browser.pages[0] if self._browser.pages else await self._browser.new_page()

            # Открываем WhatsApp Web
            await self._page.goto(
                "https://web.whatsapp.com",
                wait_until="domcontentloaded",
                timeout=60000,
            )

            # Ждём загрузки (QR-код или основной экран)
            await self._wait_for_load()

            self._started = True
            logger.info("WhatsApp Web запущен")

        except Exception as e:
            logger.error(f"Ошибка запуска WhatsApp: {e}", exc_info=True)
            await self.stop()
            raise

    async def stop(self) -> None:
        """Закрыть браузер."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        if hasattr(self, "_playwright") and self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        self._browser = None
        self._page = None
        self._started = False
        logger.info("WhatsApp Web остановлен")

    async def is_logged_in(self) -> bool:
        """Проверить залогинен ли пользователь."""
        if not self._page:
            return False

        try:
            # Ищем элемент поиска чатов — он есть только после логина
            search = await self._page.query_selector(
                '[data-testid="chat-list-search"],'
                '[aria-label="Search input textbox"],'
                'div[contenteditable="true"][data-tab="3"]'
            )
            return search is not None
        except Exception:
            return False

    async def get_recent_chats(self, limit: int = 3) -> list[str]:
        """
        Получить имена последних активных чатов.
        По ТЗ: 3 чата для анализа стиля.
        """
        if not self._started:
            return []

        try:
            # Ждём загрузки списка чатов
            await self._page.wait_for_selector(
                '[data-testid="cell-frame-container"]',
                timeout=15000,
            )

            chat_elements = await self._page.query_selector_all(
                '[data-testid="cell-frame-container"] '
                'span[dir="auto"][title]'
            )

            chat_names = []
            for elem in chat_elements[:limit]:
                title = await elem.get_attribute("title")
                if title:
                    chat_names.append(title)

            logger.info(f"WhatsApp: найдено {len(chat_names)} чатов")
            return chat_names

        except Exception as e:
            logger.error(f"Ошибка получения чатов WA: {e}")
            return []

    async def get_recent_messages(
        self,
        chat_name: str,
        limit: int = 100,
        outgoing_only: bool = True,
    ) -> list[dict]:
        """
        Получить последние сообщения из чата.

        Args:
            chat_name: Имя чата
            limit: Максимум сообщений
            outgoing_only: Только исходящие (для анализа стиля)

        Returns:
            [{"text": "...", "timestamp": "...", "is_outgoing": True}, ...]
        """
        if not self._started:
            return []

        try:
            # Открываем чат
            await self._open_chat(chat_name)
            await asyncio.sleep(2)  # Ждём загрузки сообщений

            # Прокручиваем вверх для загрузки истории
            for _ in range(3):
                await self._page.evaluate(
                    """() => {
                        const panel = document.querySelector('[data-testid="conversation-panel-messages"]');
                        if (panel) panel.scrollTop = 0;
                    }"""
                )
                await asyncio.sleep(1)

            # Собираем сообщения
            msg_elements = await self._page.query_selector_all(
                'div[data-testid="msg-container"]'
            )

            messages = []
            for elem in msg_elements[-limit:]:
                try:
                    msg_data = await self._parse_message(elem)
                    if msg_data:
                        if outgoing_only and not msg_data.get("is_outgoing"):
                            continue
                        messages.append(msg_data)
                except Exception:
                    continue

            logger.info(
                f"WhatsApp: {len(messages)} сообщений из чата '{chat_name}'"
            )
            return messages

        except Exception as e:
            logger.error(f"Ошибка чтения сообщений WA '{chat_name}': {e}")
            return []

    async def get_style_messages(self) -> list[str]:
        """
        Собрать исходящие сообщения из N чатов для анализа стиля.
        По ТЗ: 3 чата, 100 сообщений из каждого.
        """
        if not self._started or not await self.is_logged_in():
            logger.warning("WhatsApp не готов для анализа стиля")
            return []

        all_messages = []
        chat_count = config.whatsapp.style_analysis_chat_count
        msg_limit = config.whatsapp.messages_per_chat

        chats = await self.get_recent_chats(limit=chat_count)

        for chat_name in chats:
            messages = await self.get_recent_messages(
                chat_name, limit=msg_limit, outgoing_only=True,
            )
            for msg in messages:
                if msg.get("text"):
                    all_messages.append(msg["text"])

        logger.info(
            f"WhatsApp: собрано {len(all_messages)} сообщений "
            f"из {len(chats)} чатов для анализа стиля"
        )
        return all_messages

    # ═══════════════════════════════════════════════════════════════════════
    # Internal
    # ═══════════════════════════════════════════════════════════════════════

    async def _wait_for_load(self, timeout: int = 120) -> None:
        """Ждать загрузки WhatsApp Web (QR или главный экран)."""
        try:
            await self._page.wait_for_selector(
                '[data-testid="chat-list-search"],'
                '[data-testid="qrcode"],'
                'canvas[aria-label="Scan me!"]',
                timeout=timeout * 1000,
            )

            # Проверяем что это не QR-код
            qr = await self._page.query_selector(
                '[data-testid="qrcode"], canvas[aria-label="Scan me!"]'
            )
            if qr:
                logger.warning(
                    "⚠️ WhatsApp Web требует сканирования QR-кода! "
                    "Откройте WA_BROWSER_DATA директорию в браузере "
                    "или запустите с WA_HEADLESS=false"
                )

        except Exception as e:
            logger.warning(f"Таймаут загрузки WhatsApp Web: {e}")

    async def _open_chat(self, chat_name: str) -> None:
        """Открыть чат по имени."""
        # Кликаем на поиск
        search_box = await self._page.wait_for_selector(
            'div[contenteditable="true"][data-tab="3"]',
            timeout=10000,
        )

        # Очищаем и вводим имя чата
        await search_box.click()
        await self._page.keyboard.press("Control+A")
        await self._page.keyboard.type(chat_name, delay=50)
        await asyncio.sleep(1.5)

        # Кликаем на первый результат
        result = await self._page.wait_for_selector(
            f'span[title="{chat_name}"]',
            timeout=10000,
        )
        if result:
            await result.click()
            await asyncio.sleep(1)

    async def _parse_message(self, elem) -> Optional[dict]:
        """Распарсить DOM-элемент сообщения."""
        # Текст
        text_elem = await elem.query_selector(
            'span[dir="ltr"].selectable-text, '
            'span.selectable-text[data-testid="msg-text"]'
        )
        text = ""
        if text_elem:
            text = await text_elem.inner_text()

        if not text:
            return None

        # Исходящее или входящее
        classes = await elem.get_attribute("class") or ""
        is_outgoing = "message-out" in classes

        # Время
        time_elem = await elem.query_selector(
            '[data-testid="msg-meta"] span'
        )
        timestamp = ""
        if time_elem:
            timestamp = await time_elem.inner_text()

        return {
            "text": text.strip(),
            "is_outgoing": is_outgoing,
            "timestamp": timestamp,
        }


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

wa_client = WhatsAppClient()
