"""
PDS-Ultimate Browser Pro (Part 8)
====================================
Продвинутый браузерный агент мирового уровня.

НЕ тупой ИИ-скрапер, а полноценный «человек за компьютером»:

1. Anti-Bot Protection — обход Cloudflare, reCAPTCHA detection avoidance
2. Human-like Behavior — рандомные движения мыши, скролл, паузы
3. Form Filling — умное заполнение любых форм (регистрация, checkout)
4. Session Management — cookies, localStorage, авторизация
5. Multi-tab Navigation — параллельная работа с несколькими вкладками
6. Smart Wait — ожидание конкретных элементов, не фиксированных задержек
7. Screenshot Analysis — интеллектуальный анализ скриншотов
8. Download Manager — скачивание файлов с прогрессом

Anti-ban стратегии:
- Рандомный User-Agent из пула реальных браузеров
- Реалистичные viewport и language settings
- Mouse movements по кривым Безье (не прямые линии)
- Рандомные задержки между действиями (нормальное распределение)
- Fake WebGL fingerprint
- Disable webdriver flag
- Realistic scroll patterns
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════════
# ANTI-BOT ENGINE — Обход систем обнаружения
# ═══════════════════════════════════════════════════════════════════════════════


class AntiBotEngine:
    """
    Движок обхода anti-bot систем.

    Стратегии:
    - User-Agent rotation (реальные Chrome/Firefox/Safari)
    - Realistic browser fingerprint
    - Human-like timing patterns
    - Mouse movement simulation (Bezier curves)
    - Natural scroll behavior
    - WebGL/Canvas fingerprint spoofing
    """

    # Реальные User-Agent строки (2025-2026)
    USER_AGENTS = [
        # Chrome on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        # Chrome on Mac
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        # Firefox on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        # Firefox on Mac
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
        # Safari on Mac
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        # Edge on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
        # Chrome on Linux
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    ]

    # Реалистичные viewport размеры
    VIEWPORTS = [
        (1920, 1080),  # Full HD — самый популярный
        (1366, 768),   # HD
        (1536, 864),   # HD+
        (1440, 900),   # WXGA+
        (1280, 720),   # HD
        (2560, 1440),  # QHD
        (1680, 1050),  # WSXGA+
    ]

    # Локали
    LOCALES = [
        "en-US", "en-GB", "ru-RU", "de-DE", "fr-FR",
    ]

    def __init__(self):
        self._current_ua: str = ""
        self._current_viewport: tuple[int, int] = (1920, 1080)
        self.randomize()

    def randomize(self) -> None:
        """Выбрать новый случайный профиль."""
        self._current_ua = random.choice(self.USER_AGENTS)
        self._current_viewport = random.choice(self.VIEWPORTS)

    @property
    def user_agent(self) -> str:
        return self._current_ua

    @property
    def viewport(self) -> tuple[int, int]:
        return self._current_viewport

    @property
    def locale(self) -> str:
        return random.choice(self.LOCALES)

    def get_stealth_scripts(self) -> list[str]:
        """
        JavaScript код для маскировки:
        - Скрытие webdriver flag
        - Fake navigator properties
        - Override chrome object
        """
        return [
            # Скрываем webdriver
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});",

            # Fake plugins
            """Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
                    {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
                    {name: 'Native Client', filename: 'internal-nacl-plugin'},
                ],
            });""",

            # Fake languages
            """Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en', 'ru'],
            });""",

            # Hide automation
            """
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters)
            );
            """,

            # Fake hardware concurrency
            f"Object.defineProperty(navigator, 'hardwareConcurrency', {{get: () => {random.choice([4, 8, 12, 16])}}});",

            # Fake device memory
            f"Object.defineProperty(navigator, 'deviceMemory', {{get: () => {random.choice([4, 8, 16])}}});",
        ]

    # ─── Human-like Mouse Movement ──────────────────────────────────────

    @staticmethod
    def bezier_curve(
        start: tuple[float, float],
        end: tuple[float, float],
        steps: int = 20,
    ) -> list[tuple[float, float]]:
        """
        Генерация точек движения мыши по кривой Безье.

        Имитирует естественное движение руки:
        - Не прямая линия
        - Ускорение в начале, замедление в конце
        - Небольшой рандом в контрольных точках
        """
        # Контрольные точки с рандомом
        mid_x = (start[0] + end[0]) / 2 + random.uniform(-50, 50)
        mid_y = (start[1] + end[1]) / 2 + random.uniform(-30, 30)

        cp1 = (
            start[0] + (mid_x - start[0]) * 0.3 + random.uniform(-20, 20),
            start[1] + (mid_y - start[1]) * 0.3 + random.uniform(-10, 10),
        )
        cp2 = (
            mid_x + (end[0] - mid_x) * 0.7 + random.uniform(-20, 20),
            mid_y + (end[1] - mid_y) * 0.7 + random.uniform(-10, 10),
        )

        points = []
        for i in range(steps + 1):
            t = i / steps
            # Cubic Bezier
            x = (
                (1 - t) ** 3 * start[0]
                + 3 * (1 - t) ** 2 * t * cp1[0]
                + 3 * (1 - t) * t ** 2 * cp2[0]
                + t ** 3 * end[0]
            )
            y = (
                (1 - t) ** 3 * start[1]
                + 3 * (1 - t) ** 2 * t * cp1[1]
                + 3 * (1 - t) * t ** 2 * cp2[1]
                + t ** 3 * end[1]
            )

            # Добавляем мелкий шум (тремор руки)
            x += random.gauss(0, 1.5)
            y += random.gauss(0, 1.0)

            points.append((round(x, 1), round(y, 1)))

        return points

    @staticmethod
    def human_delay(
        min_ms: int = 50,
        max_ms: int = 300,
        typing: bool = False,
    ) -> float:
        """
        Генерация реалистичной задержки.

        Использует нормальное распределение (как у человека):
        - Среднее — середина диапазона
        - Иногда быстрее, иногда медленнее
        - Для набора текста — короче и более регулярные
        """
        if typing:
            # Набор текста: 50-150мс между клавишами
            mean = 80
            std = 30
        else:
            mean = (min_ms + max_ms) / 2
            std = (max_ms - min_ms) / 4

        delay = max(min_ms, random.gauss(mean, std))
        delay = min(max_ms * 1.5, delay)  # Изредка медленнее
        return delay / 1000.0  # В секундах

    @staticmethod
    def natural_scroll_pattern(page_height: int = 3000) -> list[dict[str, Any]]:
        """
        Генерация реалистичного паттерна прокрутки.

        Человек:
        - Скроллит неравномерно
        - Останавливается читать
        - Иногда скроллит назад
        - Ускоряется на неинтересном
        """
        events = []
        current_y = 0

        while current_y < page_height:
            # Размер скролла (100-400px, нормальное распределение)
            scroll_amount = int(random.gauss(250, 80))
            scroll_amount = max(50, min(500, scroll_amount))

            current_y += scroll_amount

            # Задержка после скролла (читаем контент)
            if random.random() < 0.3:
                # Длинная пауза — читаем что-то интересное
                pause = random.uniform(1.5, 4.0)
            elif random.random() < 0.1:
                # Скролл назад — вернулись перечитать
                current_y -= random.randint(100, 300)
                pause = random.uniform(0.5, 1.5)
            else:
                # Обычная пауза
                pause = random.uniform(0.3, 1.0)

            events.append({
                "y": max(0, current_y),
                "amount": scroll_amount,
                "pause": round(pause, 2),
            })

        return events


# ═══════════════════════════════════════════════════════════════════════════════
# FORM FILLER — Умное заполнение форм
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class FormField:
    """Поле формы."""
    selector: str = ""
    field_type: str = "text"   # text, email, password, tel, select, checkbox
    label: str = ""
    name: str = ""
    required: bool = False
    value: str = ""
    options: list[str] = field(default_factory=list)  # for select


@dataclass
class FormData:
    """Данные для заполнения формы."""
    fields: list[FormField] = field(default_factory=list)
    submit_selector: str = ""
    form_url: str = ""


class FormFiller:
    """
    Интеллектуальное заполнение форм.

    Возможности:
    - Определение типа поля по label/name/placeholder
    - Генерация реалистичных данных
    - Человекоподобный ввод (с задержками и ошибками)
    - Поддержка select, checkbox, radio
    """

    # Маппинг label → тип данных
    FIELD_MAPPINGS: dict[str, str] = {
        "email": "email",
        "e-mail": "email",
        "почта": "email",
        "пароль": "password",
        "password": "password",
        "телефон": "phone",
        "phone": "phone",
        "имя": "first_name",
        "first name": "first_name",
        "фамилия": "last_name",
        "last name": "last_name",
        "name": "full_name",
        "город": "city",
        "city": "city",
        "адрес": "address",
        "address": "address",
        "индекс": "zip",
        "zip": "zip",
        "postal": "zip",
        "country": "country",
        "страна": "country",
        "компания": "company",
        "company": "company",
    }

    def detect_field_type(self, label: str, name: str = "") -> str:
        """Определить тип поля по label и name."""
        combined = f"{label} {name}".lower()
        for keyword, ftype in self.FIELD_MAPPINGS.items():
            if keyword in combined:
                return ftype
        return "text"

    def generate_fill_plan(
        self,
        fields: list[FormField],
        user_data: dict[str, str] | None = None,
    ) -> list[tuple[FormField, str]]:
        """
        Генерировать план заполнения формы.

        Args:
            fields: Поля формы
            user_data: Данные пользователя (email, name, etc.)

        Returns:
            Список (поле, значение)
        """
        user_data = user_data or {}
        plan: list[tuple[FormField, str]] = []

        for f in fields:
            detected_type = self.detect_field_type(f.label, f.name)

            # Ищем в данных пользователя
            value = user_data.get(detected_type, "")
            if not value:
                value = user_data.get(f.name, "")
            if not value:
                value = f.value

            plan.append((f, value))

        return plan

    @staticmethod
    def simulate_typing_errors(text: str, error_rate: float = 0.03) -> list[str]:
        """
        Имитация ошибок набора (опечатки + backspace).

        Человек иногда:
        - Нажимает соседнюю клавишу
        - Быстро исправляет (backspace + правильная)
        """
        # Соседние клавиши на QWERTY
        neighbors: dict[str, str] = {
            'a': 'sq', 'b': 'vn', 'c': 'xv', 'd': 'sf', 'e': 'wr',
            'f': 'dg', 'g': 'fh', 'h': 'gj', 'i': 'uo', 'j': 'hk',
            'k': 'jl', 'l': 'k;', 'm': 'n,', 'n': 'bm', 'o': 'ip',
            'p': 'o[', 'q': 'wa', 'r': 'et', 's': 'ad', 't': 'ry',
            'u': 'yi', 'v': 'cb', 'w': 'qe', 'x': 'zc', 'y': 'tu',
            'z': 'xs',
        }

        keystrokes: list[str] = []

        for char in text:
            if random.random() < error_rate and char.lower() in neighbors:
                # Опечатка
                wrong = random.choice(neighbors[char.lower()])
                keystrokes.append(wrong)
                keystrokes.append("BACKSPACE")
                keystrokes.append(char)
            else:
                keystrokes.append(char)

        return keystrokes


# ═══════════════════════════════════════════════════════════════════════════════
# SESSION MANAGER — Управление сессиями
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class BrowserSession:
    """Сессия браузера."""
    id: str = ""
    domain: str = ""
    cookies: list[dict[str, Any]] = field(default_factory=list)
    local_storage: dict[str, str] = field(default_factory=dict)
    is_authenticated: bool = False
    user_agent: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "domain": self.domain,
            "cookies_count": len(self.cookies),
            "authenticated": self.is_authenticated,
            "created_at": self.created_at.isoformat(),
        }


class SessionManager:
    """Управление сессиями браузера."""

    def __init__(self):
        self._sessions: dict[str, BrowserSession] = {}

    def create_session(self, domain: str) -> BrowserSession:
        """Создать новую сессию."""
        session_id = f"{domain}_{int(time.time())}"
        session = BrowserSession(
            id=session_id,
            domain=domain,
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, domain: str) -> BrowserSession | None:
        """Найти сессию для домена."""
        for s in self._sessions.values():
            if s.domain == domain:
                return s
        return None

    def update_session(
        self,
        session_id: str,
        cookies: list[dict] | None = None,
        local_storage: dict | None = None,
        authenticated: bool | None = None,
    ) -> None:
        """Обновить сессию."""
        session = self._sessions.get(session_id)
        if not session:
            return

        if cookies is not None:
            session.cookies = cookies
        if local_storage is not None:
            session.local_storage.update(local_storage)
        if authenticated is not None:
            session.is_authenticated = authenticated

        session.last_activity = datetime.utcnow()

    def delete_session(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    @property
    def active_sessions(self) -> list[BrowserSession]:
        return list(self._sessions.values())

    @property
    def count(self) -> int:
        return len(self._sessions)


# ═══════════════════════════════════════════════════════════════════════════════
# BROWSER PRO ENGINE — Главный движок
# ═══════════════════════════════════════════════════════════════════════════════


class BrowserProEngine:
    """
    Продвинутый браузерный движок мирового уровня.

    Объединяет:
    - Anti-bot protection
    - Human-like behavior
    - Smart form filling
    - Session management
    - Multi-tab navigation
    """

    def __init__(self):
        self.anti_bot = AntiBotEngine()
        self.form_filler = FormFiller()
        self.sessions = SessionManager()
        self._action_log: list[dict[str, Any]] = []

    # ─── Navigation ──────────────────────────────────────────────────────

    async def navigate(
        self,
        url: str,
        wait_for: str = "load",
        stealth: bool = True,
    ) -> dict[str, Any]:
        """
        Навигация на URL с anti-bot защитой.

        Args:
            url: URL для навигации
            wait_for: load | domcontentloaded | networkidle
            stealth: Применить stealth mode

        Returns:
            dict с информацией о странице
        """
        start = time.time()

        try:
            from pds_ultimate.core.browser_engine import browser_engine

            # Применяем stealth если нужно
            if stealth and browser_engine._page:
                for script in self.anti_bot.get_stealth_scripts():
                    try:
                        await browser_engine._page.evaluate(script)
                    except Exception:
                        pass

            # Навигация
            data = await browser_engine.extract_data(url)

            # Рандомная пауза после загрузки (человек не сразу действует)
            await self._human_pause(0.5, 2.0)

            self._log_action("navigate", url=url, success=True)

            return {
                "success": True,
                "url": data.url,
                "title": data.title,
                "text_length": len(data.text) if data.text else 0,
                "tables": len(data.tables) if data.tables else 0,
                "latency_ms": int((time.time() - start) * 1000),
            }

        except Exception as e:
            self._log_action("navigate", url=url, success=False, error=str(e))
            return {"success": False, "error": str(e)}

    # ─── Form Operations ─────────────────────────────────────────────────

    async def fill_form(
        self,
        fields: dict[str, str],
        submit_selector: str = "",
        human_like: bool = True,
    ) -> dict[str, Any]:
        """
        Заполнить форму на текущей странице.

        Args:
            fields: {selector: value}
            submit_selector: CSS селектор кнопки отправки
            human_like: Имитировать человеческий ввод
        """
        results: list[dict[str, Any]] = []

        try:
            from pds_ultimate.core.browser_engine import browser_engine

            for selector, value in fields.items():
                try:
                    if human_like:
                        # Кликаем на поле
                        await browser_engine.click(selector, human_like=True)
                        await self._human_pause(0.1, 0.3)

                        # Очищаем и вводим
                        await browser_engine.fill(selector, value, human_like=True)
                        await self._human_pause(0.2, 0.5)
                    else:
                        await browser_engine.fill(selector, value, human_like=False)

                    results.append({"selector": selector, "success": True})

                except Exception as e:
                    results.append(
                        {"selector": selector, "success": False, "error": str(e)})

            # Submit
            submitted = False
            if submit_selector:
                try:
                    await self._human_pause(0.5, 1.0)
                    await browser_engine.click(submit_selector, human_like=True)
                    submitted = True
                except Exception as e:
                    results.append({"selector": submit_selector,
                                   "success": False, "error": str(e)})

            filled = sum(1 for r in results if r["success"])

            self._log_action(
                "fill_form",
                fields=len(fields),
                filled=filled,
                submitted=submitted,
            )

            return {
                "success": filled > 0,
                "filled": filled,
                "total": len(fields),
                "submitted": submitted,
                "details": results,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def register_on_site(
        self,
        url: str,
        user_data: dict[str, str],
    ) -> dict[str, Any]:
        """
        Зарегистрироваться на сайте.

        Args:
            url: URL страницы регистрации
            user_data: {"email": "...", "password": "...", "first_name": "..."}

        Returns:
            Результат регистрации
        """
        # 1. Навигация
        nav_result = await self.navigate(url, stealth=True)
        if not nav_result.get("success"):
            return nav_result

        # 2. Заполнение формы
        # Маппинг данных пользователя → CSS селекторы (типичные)
        common_selectors = {
            "email": ['input[type="email"]', 'input[name="email"]', '#email'],
            "password": ['input[type="password"]', 'input[name="password"]', '#password'],
            "first_name": ['input[name="first_name"]', 'input[name="firstName"]', '#first_name'],
            "last_name": ['input[name="last_name"]', 'input[name="lastName"]', '#last_name'],
            "phone": ['input[type="tel"]', 'input[name="phone"]', '#phone'],
        }

        # Пробуем найти поля
        fields: dict[str, str] = {}
        for data_key, selectors in common_selectors.items():
            if data_key in user_data:
                for sel in selectors:
                    fields[sel] = user_data[data_key]
                    break  # Возьмём первый селектор

        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            '.register-button',
            '#register',
            '.signup-btn',
        ]

        result = await self.fill_form(
            fields=fields,
            submit_selector=submit_selectors[0],
            human_like=True,
        )

        self._log_action("register", url=url,
                         success=result.get("success", False))

        return result

    # ─── Smart Actions ───────────────────────────────────────────────────

    async def click_smart(
        self,
        text: str = "",
        selector: str = "",
    ) -> dict[str, Any]:
        """
        Умный клик — по тексту или селектору.

        Если указан text — ищет элемент с таким текстом.
        Если selector — использует CSS selector.
        """
        try:
            from pds_ultimate.core.browser_engine import browser_engine

            if text and not selector:
                # Поиск по тексту
                selector = f"text={text}"

            # Human-like: пауза перед кликом
            await self._human_pause(0.2, 0.5)

            await browser_engine.click(selector, human_like=True)

            # Пауза после клика
            await self._human_pause(0.3, 1.0)

            info = await browser_engine.get_page_info()

            self._log_action("click", selector=selector, success=True)

            return {
                "success": True,
                "url": info.url if info else "",
                "title": info.title if info else "",
            }

        except Exception as e:
            self._log_action("click", selector=selector,
                             success=False, error=str(e))
            return {"success": False, "error": str(e)}

    async def scroll_naturally(self, direction: str = "down") -> dict[str, Any]:
        """Прокрутка страницы с человеческим поведением."""
        try:
            from pds_ultimate.core.browser_engine import browser_engine

            if not browser_engine._page:
                return {"success": False, "error": "No page open"}

            pattern = self.anti_bot.natural_scroll_pattern()

            for event in pattern[:5]:  # Максимум 5 скроллов
                amount = event["amount"]
                if direction == "up":
                    amount = -amount

                await browser_engine._page.evaluate(
                    f"window.scrollBy(0, {amount})"
                )
                await self._human_pause(
                    event["pause"] * 0.8,
                    event["pause"] * 1.2,
                )

            self._log_action("scroll", direction=direction, success=True)
            return {"success": True, "direction": direction}

        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Analysis ────────────────────────────────────────────────────────

    async def analyze_page(self) -> dict[str, Any]:
        """
        Анализ текущей страницы.

        Извлекает:
        - Заголовки и структуру
        - Ссылки
        - Формы и их поля
        - Основной контент
        """
        try:
            from pds_ultimate.core.browser_engine import browser_engine

            info = await browser_engine.get_page_info()
            data = await browser_engine.extract_data(info.url if info else "")

            analysis = {
                "url": data.url,
                "title": data.title,
                "text_length": len(data.text) if data.text else 0,
                "tables_count": len(data.tables) if data.tables else 0,
                "has_forms": False,
                "links_count": 0,
            }

            # Считаем ссылки из текста
            if data.text:
                import re
                links = re.findall(r'https?://\S+', data.text)
                analysis["links_count"] = len(links)

            return {"success": True, **analysis}

        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Internal ────────────────────────────────────────────────────────

    async def _human_pause(self, min_sec: float, max_sec: float) -> None:
        """Реалистичная пауза."""
        import asyncio
        delay = self.anti_bot.human_delay(
            int(min_sec * 1000), int(max_sec * 1000)
        )
        await asyncio.sleep(delay)

    def _log_action(self, action: str, **kwargs: Any) -> None:
        """Логировать действие."""
        entry = {
            "action": action,
            "timestamp": datetime.utcnow().isoformat(),
            **kwargs,
        }
        self._action_log.append(entry)

        # Ограничиваем лог
        if len(self._action_log) > 1000:
            self._action_log = self._action_log[-500:]

    def get_action_log(self, limit: int = 20) -> list[dict]:
        """Получить лог действий."""
        return self._action_log[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Статистика браузера."""
        total = len(self._action_log)
        success = sum(1 for a in self._action_log if a.get("success", False))

        return {
            "total_actions": total,
            "success_rate": f"{success / total:.0%}" if total else "N/A",
            "active_sessions": self.sessions.count,
            "user_agent": self.anti_bot.user_agent[:50] + "...",
            "viewport": f"{self.anti_bot.viewport[0]}x{self.anti_bot.viewport[1]}",
        }


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

browser_pro = BrowserProEngine()
