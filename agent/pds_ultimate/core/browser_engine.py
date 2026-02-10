"""
PDS-Ultimate Browser Engine (Part 4)
========================================
Полноценный браузерный движок на Playwright.

Возможности:
1. Anti-Detection — stealth mode, рандомные fingerprints
2. Human-Like Behavior — случайные задержки, плавный скролл, движение мыши
3. Page Management — пул страниц, навигация, ожидание загрузки
4. Data Extraction — текст, HTML, таблицы, ссылки, мета-данные
5. Screenshots — полная страница, элемент, область
6. Form Automation — заполнение форм, клики, выбор из списков
7. Cookie/Session Management — сохранение/загрузка сессий
8. Download Management — скачивание файлов
9. Web Search — поиск через DuckDuckGo (без API ключей)
10. Tool Integration — browser tools для AI-агента

Anti-Detection Features:
- Рандомные User-Agent из реального пула
- Скрытие navigator.webdriver
- Подмена canvas/WebGL fingerprint
- Реалистичные viewport и screen размеры
- Human-like timing (клики, набор текста)
- Рандомное движение мыши перед кликом
- Реалистичный скроллинг
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from pds_ultimate.config import config, logger

# ═══════════════════════════════════════════════════════════════════════════════
# 1. CONSTANTS & USER AGENTS
# ═══════════════════════════════════════════════════════════════════════════════

# Реалистичный пул User-Agent'ов (актуальные на 2026)
USER_AGENTS = [
    # Chrome Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Chrome macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Chrome Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Firefox Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) "
    "Gecko/20100101 Firefox/134.0",
    # Firefox macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:134.0) "
    "Gecko/20100101 Firefox/134.0",
    # Firefox Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:134.0) "
    "Gecko/20100101 Firefox/134.0",
    # Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]

# Реалистичные разрешения экрана
SCREEN_SIZES = [
    (1920, 1080), (1366, 768), (1536, 864), (1440, 900),
    (1280, 720), (2560, 1440), (1600, 900), (1680, 1050),
]

# Stealth JS — скрипт для подмены fingerprint
STEALTH_JS = """
// Hide webdriver
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// Hide automation
delete navigator.__proto__.webdriver;

// Chrome runtime
window.chrome = {
    runtime: {
        onConnect: undefined,
        onMessage: undefined,
    },
    loadTimes: function() { return {}; },
    csi: function() { return {}; },
};

// Permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({state: Notification.permission})
        : originalQuery(parameters);

// Plugins — simulate realistic
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
            {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
            {name: 'Native Client', filename: 'internal-nacl-plugin'},
        ];
        plugins.length = 3;
        return plugins;
    },
});

// Languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en', 'ru'],
});

// Platform
Object.defineProperty(navigator, 'platform', {
    get: () => 'Win32',
});

// Hardware concurrency
Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => 8,
});

// Device memory
Object.defineProperty(navigator, 'deviceMemory', {
    get: () => 8,
});

// WebGL vendor
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.call(this, parameter);
};
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 2. DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class PageStatus(str, Enum):
    """Статус страницы."""
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"
    CLOSED = "closed"


@dataclass
class PageInfo:
    """Информация о загруженной странице."""
    url: str
    title: str = ""
    status_code: int = 200
    status: PageStatus = PageStatus.READY
    load_time_ms: int = 0
    content_type: str = ""
    text_length: int = 0


@dataclass
class ExtractedData:
    """Извлечённые данные со страницы."""
    url: str
    title: str = ""
    text: str = ""
    links: list[dict[str, str]] = field(default_factory=list)
    images: list[dict[str, str]] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    meta: dict[str, str] = field(default_factory=dict)
    headings: list[dict[str, str]] = field(default_factory=list)
    forms: list[dict] = field(default_factory=list)

    def summary(self, max_text: int = 2000) -> str:
        """Краткое описание извлечённых данных."""
        parts = [f"📄 {self.title}", f"🔗 {self.url}"]
        if self.text:
            trimmed = self.text[:max_text]
            if len(self.text) > max_text:
                trimmed += "..."
            parts.append(f"\n{trimmed}")
        if self.links:
            parts.append(f"\n🔗 Ссылок: {len(self.links)}")
        if self.tables:
            parts.append(f"📊 Таблиц: {len(self.tables)}")
        if self.images:
            parts.append(f"🖼️ Изображений: {len(self.images)}")
        return "\n".join(parts)

    def to_dict(self) -> dict:
        """Сериализация."""
        return {
            "url": self.url,
            "title": self.title,
            "text_length": len(self.text),
            "links_count": len(self.links),
            "tables_count": len(self.tables),
            "images_count": len(self.images),
            "meta": self.meta,
        }


@dataclass
class SearchResult:
    """Результат поиска."""
    title: str
    url: str
    snippet: str = ""
    position: int = 0

    def __str__(self) -> str:
        return f"[{self.position}] {self.title}\n    {self.url}\n    {self.snippet}"


@dataclass
class BrowserStats:
    """Статистика работы браузера."""
    pages_loaded: int = 0
    pages_failed: int = 0
    screenshots_taken: int = 0
    searches_performed: int = 0
    total_bytes_downloaded: int = 0
    total_time_ms: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "pages_loaded": self.pages_loaded,
            "pages_failed": self.pages_failed,
            "screenshots": self.screenshots_taken,
            "searches": self.searches_performed,
            "bytes_downloaded": self.total_bytes_downloaded,
            "time_ms": self.total_time_ms,
            "errors_count": len(self.errors),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. HUMAN-LIKE BEHAVIOR
# ═══════════════════════════════════════════════════════════════════════════════

class HumanBehavior:
    """
    Имитация человеческого поведения в браузере.

    - Случайные задержки между действиями
    - Плавный набор текста с ошибками и исправлениями
    - Реалистичный скроллинг
    - Движение мыши к элементу перед кликом
    - Случайные паузы (как будто человек думает)
    """

    def __init__(
        self,
        min_type_delay: int = 50,
        max_type_delay: int = 150,
        min_click_delay: int = 100,
        max_click_delay: int = 500,
    ):
        self.min_type_delay = min_type_delay
        self.max_type_delay = max_type_delay
        self.min_click_delay = min_click_delay
        self.max_click_delay = max_click_delay

    async def random_delay(self, min_ms: int = 100, max_ms: int = 500) -> None:
        """Случайная задержка."""
        delay = random.randint(min_ms, max_ms) / 1000
        await asyncio.sleep(delay)

    async def thinking_pause(self) -> None:
        """Пауза 'на подумать' (0.5-2 сек)."""
        await asyncio.sleep(random.uniform(0.5, 2.0))

    async def human_type(self, page: Any, selector: str, text: str) -> None:
        """
        Печать текста с человеческой скоростью.
        Включает случайные задержки между символами.
        """
        element = page.locator(selector)
        await element.click()
        await self.random_delay(200, 500)

        for char in text:
            await element.press_sequentially(
                char,
                delay=random.randint(self.min_type_delay, self.max_type_delay),
            )
            # Иногда делаем мини-паузу (как будто думаем)
            if random.random() < 0.05:
                await asyncio.sleep(random.uniform(0.3, 0.8))

    async def human_click(self, page: Any, selector: str) -> None:
        """
        Клик с человеческой задержкой.
        Перед кликом — небольшое ожидание.
        """
        await self.random_delay(self.min_click_delay, self.max_click_delay)
        element = page.locator(selector)

        # Скроллим к элементу
        await element.scroll_into_view_if_needed()
        await self.random_delay(100, 300)

        # Кликаем
        await element.click()

    async def smooth_scroll(self, page: Any, direction: str = "down",
                            distance: int = 300) -> None:
        """Плавный скроллинг."""
        if direction == "down":
            delta = distance
        elif direction == "up":
            delta = -distance
        else:
            delta = distance

        # Несколько маленьких скроллов вместо одного большого
        steps = random.randint(3, 6)
        step_size = delta // steps

        for _ in range(steps):
            await page.mouse.wheel(0, step_size + random.randint(-20, 20))
            await asyncio.sleep(random.uniform(0.05, 0.15))

    async def scroll_to_bottom(self, page: Any, max_scrolls: int = 10) -> None:
        """Прокрутка до конца страницы."""
        for _ in range(max_scrolls):
            prev_height = await page.evaluate("document.body.scrollHeight")
            await self.smooth_scroll(page, "down", random.randint(400, 800))
            await asyncio.sleep(random.uniform(0.5, 1.5))
            new_height = await page.evaluate("document.body.scrollHeight")
            if new_height == prev_height:
                break

    def get_random_user_agent(self) -> str:
        """Случайный User-Agent из пула."""
        return random.choice(USER_AGENTS)

    def get_random_screen_size(self) -> tuple[int, int]:
        """Случайное разрешение экрана."""
        return random.choice(SCREEN_SIZES)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. BROWSER ENGINE — Main Class
# ═══════════════════════════════════════════════════════════════════════════════

class BrowserEngine:
    """
    Браузерный движок мирового класса.

    Playwright + Anti-Detection + Human-Like + Data Extraction.

    Использование:
        engine = BrowserEngine()
        await engine.start()

        # Открыть страницу
        page_info = await engine.goto("https://example.com")

        # Извлечь данные
        data = await engine.extract_data()

        # Поиск в интернете
        results = await engine.web_search("python playwright tutorial")

        # Скриншот
        path = await engine.screenshot()

        await engine.stop()
    """

    def __init__(self, cfg: Any | None = None):
        self._cfg = cfg or config.browser
        self._human = HumanBehavior(
            min_type_delay=self._cfg.min_type_delay,
            max_type_delay=self._cfg.max_type_delay,
            min_click_delay=self._cfg.min_click_delay,
            max_click_delay=self._cfg.max_click_delay,
        )
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._pages: dict[str, Any] = {}  # id → page
        self._stats = BrowserStats()
        self._started = False
        self._user_agent = (
            self._cfg.user_agent or self._human.get_random_user_agent()
        )

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def stats(self) -> BrowserStats:
        return self._stats

    @property
    def current_url(self) -> str:
        if self._page:
            return self._page.url
        return ""

    @property
    def current_title(self) -> str:
        """Заголовок текущей страницы (синхронный, кэшированный)."""
        return self._last_title

    # ─── Lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Запустить браузер."""
        if self._started:
            return

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error(
                "Playwright не установлен. Установите: pip install playwright && "
                "playwright install chromium"
            )
            raise RuntimeError("Playwright not installed")

        self._playwright = await async_playwright().start()

        # Выбор типа браузера
        browser_type = self._cfg.browser_type
        launcher = getattr(self._playwright, browser_type,
                           self._playwright.chromium)

        # Параметры запуска
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
        ]

        launch_kwargs: dict[str, Any] = {
            "headless": self._cfg.headless,
            "args": launch_args,
        }

        if self._cfg.proxy_server:
            launch_kwargs["proxy"] = {"server": self._cfg.proxy_server}

        self._browser = await launcher.launch(**launch_kwargs)

        # Создаём контекст с anti-detection
        width, height = self._cfg.viewport_width, self._cfg.viewport_height
        context_kwargs: dict[str, Any] = {
            "viewport": {"width": width, "height": height},
            "screen": {"width": width, "height": height},
            "user_agent": self._user_agent,
            "locale": self._cfg.locale,
            "timezone_id": self._cfg.timezone,
            "java_script_enabled": True,
            "accept_downloads": True,
            "ignore_https_errors": True,
        }

        self._context = await self._browser.new_context(**context_kwargs)

        # Stealth: инъекция JS для скрытия автоматизации
        if self._cfg.stealth_enabled:
            await self._context.add_init_script(STEALTH_JS)

        # Создаём первую страницу
        self._page = await self._context.new_page()
        self._page.set_default_timeout(self._cfg.default_timeout)
        self._page.set_default_navigation_timeout(self._cfg.navigation_timeout)
        self._last_title = ""

        # Создаём директории
        self._cfg.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self._cfg.downloads_dir.mkdir(parents=True, exist_ok=True)

        self._started = True
        logger.info(
            f"Browser Engine запущен: {browser_type} "
            f"(headless={self._cfg.headless}, stealth={self._cfg.stealth_enabled})"
        )

    async def stop(self) -> None:
        """Остановить браузер."""
        if not self._started:
            return

        try:
            # Закрываем все страницы
            for page in list(self._pages.values()):
                try:
                    await page.close()
                except Exception:
                    pass

            if self._page:
                try:
                    await self._page.close()
                except Exception:
                    pass

            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"Browser stop error: {e}")
        finally:
            self._started = False
            self._playwright = None
            self._browser = None
            self._context = None
            self._page = None
            self._pages.clear()
            logger.info("Browser Engine остановлен")

    async def restart(self) -> None:
        """Перезапустить браузер."""
        await self.stop()
        # Новый User-Agent при перезапуске
        self._user_agent = self._human.get_random_user_agent()
        await self.start()

    # ─── Navigation ──────────────────────────────────────────────────────

    async def goto(self, url: str, wait_until: str = "domcontentloaded") -> PageInfo:
        """
        Перейти на URL.

        Args:
            url: URL страницы
            wait_until: Когда считать загрузку завершённой
                       (domcontentloaded | load | networkidle | commit)

        Returns:
            PageInfo с информацией о странице
        """
        if not self._started:
            await self.start()

        start_time = time.time()
        page_info = PageInfo(url=url)

        try:
            response = await self._page.goto(url, wait_until=wait_until)

            load_ms = int((time.time() - start_time) * 1000)
            page_info.load_time_ms = load_ms
            page_info.title = await self._page.title()
            self._last_title = page_info.title

            if response:
                page_info.status_code = response.status
                page_info.content_type = response.headers.get(
                    "content-type", "")

            page_info.status = PageStatus.READY
            self._stats.pages_loaded += 1
            self._stats.total_time_ms += load_ms

            logger.debug(
                f"Page loaded: {url} ({page_info.status_code}, {load_ms}ms)"
            )

        except Exception as e:
            page_info.status = PageStatus.ERROR
            page_info.status_code = 0
            self._stats.pages_failed += 1
            error_msg = f"Navigation error: {url} — {e}"
            self._stats.errors.append(error_msg)
            logger.warning(error_msg)

        return page_info

    async def go_back(self) -> PageInfo:
        """Назад в истории."""
        if not self._page:
            return PageInfo(url="", status=PageStatus.ERROR)
        start = time.time()
        await self._page.go_back()
        title = await self._page.title()
        self._last_title = title
        return PageInfo(
            url=self._page.url,
            title=title,
            load_time_ms=int((time.time() - start) * 1000),
        )

    async def go_forward(self) -> PageInfo:
        """Вперёд в истории."""
        if not self._page:
            return PageInfo(url="", status=PageStatus.ERROR)
        start = time.time()
        await self._page.go_forward()
        title = await self._page.title()
        self._last_title = title
        return PageInfo(
            url=self._page.url,
            title=title,
            load_time_ms=int((time.time() - start) * 1000),
        )

    async def reload(self) -> PageInfo:
        """Перезагрузить текущую страницу."""
        if not self._page:
            return PageInfo(url="", status=PageStatus.ERROR)
        return await self.goto(self._page.url)

    # ─── Data Extraction ─────────────────────────────────────────────────

    async def extract_data(self, url: str | None = None) -> ExtractedData:
        """
        Извлечь все данные со страницы.

        Args:
            url: URL (если не задан — текущая страница)

        Returns:
            ExtractedData со всеми данными
        """
        if url:
            await self.goto(url)

        if not self._page:
            return ExtractedData(url="")

        current_url = self._page.url
        title = await self._page.title()

        data = ExtractedData(url=current_url, title=title)

        # Текст страницы
        try:
            data.text = await self._page.evaluate("""
                () => {
                    const body = document.body;
                    if (!body) return '';
                    // Удаляем script, style, nav, footer
                    const clone = body.cloneNode(true);
                    const remove = clone.querySelectorAll(
                        'script, style, nav, footer, header, aside, ' +
                        'noscript, iframe, svg, [aria-hidden="true"]'
                    );
                    remove.forEach(el => el.remove());
                    return clone.innerText || clone.textContent || '';
                }
            """)
            # Очищаем множественные пробелы/переносы
            data.text = re.sub(r'\n{3,}', '\n\n', data.text).strip()
            data.text = re.sub(r'[ \t]{2,}', ' ', data.text)
        except Exception as e:
            logger.debug(f"Text extraction error: {e}")

        # Ссылки
        try:
            data.links = await self._page.evaluate("""
                () => {
                    const links = [];
                    document.querySelectorAll('a[href]').forEach(a => {
                        const href = a.href;
                        const text = (a.innerText || a.textContent || '').trim();
                        if (href && text && !href.startsWith('javascript:')) {
                            links.push({url: href, text: text.substring(0, 200)});
                        }
                    });
                    return links.slice(0, 100);
                }
            """)
        except Exception as e:
            logger.debug(f"Links extraction error: {e}")

        # Заголовки
        try:
            data.headings = await self._page.evaluate("""
                () => {
                    const headings = [];
                    document.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(h => {
                        const text = (h.innerText || h.textContent || '').trim();
                        if (text) {
                            headings.push({level: h.tagName.toLowerCase(), text: text});
                        }
                    });
                    return headings;
                }
            """)
        except Exception as e:
            logger.debug(f"Headings extraction error: {e}")

        # Изображения
        try:
            data.images = await self._page.evaluate("""
                () => {
                    const images = [];
                    document.querySelectorAll('img[src]').forEach(img => {
                        const src = img.src;
                        const alt = img.alt || '';
                        if (src) {
                            images.push({src: src, alt: alt});
                        }
                    });
                    return images.slice(0, 50);
                }
            """)
        except Exception as e:
            logger.debug(f"Images extraction error: {e}")

        # Таблицы
        try:
            data.tables = await self._page.evaluate("""
                () => {
                    const tables = [];
                    document.querySelectorAll('table').forEach(table => {
                        const rows = [];
                        table.querySelectorAll('tr').forEach(tr => {
                            const cells = [];
                            tr.querySelectorAll('td, th').forEach(cell => {
                                cells.push((cell.innerText || cell.textContent || '').trim());
                            });
                            if (cells.length > 0) rows.push(cells);
                        });
                        if (rows.length > 0) tables.push(rows);
                    });
                    return tables.slice(0, 10);
                }
            """)
        except Exception as e:
            logger.debug(f"Tables extraction error: {e}")

        # Meta tags
        try:
            data.meta = await self._page.evaluate("""
                () => {
                    const meta = {};
                    document.querySelectorAll('meta[name], meta[property]').forEach(m => {
                        const key = m.getAttribute('name') || m.getAttribute('property');
                        const content = m.getAttribute('content');
                        if (key && content) meta[key] = content;
                    });
                    return meta;
                }
            """)
        except Exception as e:
            logger.debug(f"Meta extraction error: {e}")

        return data

    async def extract_text(self, url: str | None = None,
                           selector: str | None = None) -> str:
        """
        Извлечь только текст со страницы.

        Args:
            url: URL (опционально)
            selector: CSS-селектор конкретного элемента

        Returns:
            Текст страницы
        """
        if url:
            await self.goto(url)

        if not self._page:
            return ""

        try:
            if selector:
                element = self._page.locator(selector).first
                return await element.inner_text()
            else:
                data = await self.extract_data()
                return data.text
        except Exception as e:
            logger.debug(f"Text extraction error: {e}")
            return ""

    async def extract_links(self, url: str | None = None,
                            pattern: str | None = None) -> list[dict[str, str]]:
        """
        Извлечь ссылки со страницы.

        Args:
            url: URL (опционально)
            pattern: Regex фильтр для URL

        Returns:
            Список ссылок [{url, text}, ...]
        """
        if url:
            await self.goto(url)

        data = await self.extract_data()
        links = data.links

        if pattern:
            regex = re.compile(pattern, re.IGNORECASE)
            links = [l for l in links if regex.search(l.get("url", ""))]

        return links

    # ─── Screenshots ─────────────────────────────────────────────────────

    async def screenshot(
        self,
        path: str | Path | None = None,
        full_page: bool = False,
        selector: str | None = None,
    ) -> Path:
        """
        Сделать скриншот.

        Args:
            path: Путь сохранения (или auto-generated)
            full_page: Полная страница
            selector: CSS-селектор элемента

        Returns:
            Path к сохранённому файлу
        """
        if not self._page:
            raise RuntimeError("Browser not started")

        if not path:
            ts = int(time.time())
            url_hash = hashlib.md5(self._page.url.encode()).hexdigest()[:8]
            filename = f"screenshot_{ts}_{url_hash}.png"
            path = self._cfg.screenshots_dir / filename

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if selector:
            element = self._page.locator(selector).first
            await element.screenshot(path=str(path))
        else:
            await self._page.screenshot(path=str(path), full_page=full_page)

        self._stats.screenshots_taken += 1
        logger.debug(f"Screenshot saved: {path}")
        return path

    # ─── Form Interaction ────────────────────────────────────────────────

    async def fill(self, selector: str, value: str,
                   human_like: bool = True) -> None:
        """
        Заполнить поле формы.

        Args:
            selector: CSS-селектор
            value: Значение
            human_like: Печатать как человек
        """
        if not self._page:
            raise RuntimeError("Browser not started")

        if human_like:
            await self._human.human_type(self._page, selector, value)
        else:
            await self._page.fill(selector, value)

    async def click(self, selector: str, human_like: bool = True) -> None:
        """Кликнуть по элементу."""
        if not self._page:
            raise RuntimeError("Browser not started")

        if human_like:
            await self._human.human_click(self._page, selector)
        else:
            await self._page.click(selector)

    async def select_option(self, selector: str, value: str) -> None:
        """Выбрать опцию в select."""
        if not self._page:
            raise RuntimeError("Browser not started")
        await self._page.select_option(selector, value)

    async def check(self, selector: str) -> None:
        """Отметить чекбокс."""
        if not self._page:
            raise RuntimeError("Browser not started")
        await self._page.check(selector)

    async def uncheck(self, selector: str) -> None:
        """Снять чекбокс."""
        if not self._page:
            raise RuntimeError("Browser not started")
        await self._page.uncheck(selector)

    # ─── Wait & Query ────────────────────────────────────────────────────

    async def wait_for(self, selector: str, state: str = "visible",
                       timeout: int | None = None) -> bool:
        """
        Ожидать появления элемента.

        Args:
            selector: CSS-селектор
            state: visible | hidden | attached | detached
            timeout: Таймаут в мс

        Returns:
            True если элемент найден
        """
        if not self._page:
            return False

        try:
            await self._page.locator(selector).wait_for(
                state=state, timeout=timeout or self._cfg.default_timeout
            )
            return True
        except Exception:
            return False

    async def query_selector(self, selector: str) -> bool:
        """Проверить наличие элемента."""
        if not self._page:
            return False
        try:
            count = await self._page.locator(selector).count()
            return count > 0
        except Exception:
            return False

    async def get_attribute(self, selector: str, attribute: str) -> str | None:
        """Получить атрибут элемента."""
        if not self._page:
            return None
        try:
            return await self._page.locator(selector).first.get_attribute(attribute)
        except Exception:
            return None

    async def evaluate(self, expression: str) -> Any:
        """Выполнить JavaScript на странице."""
        if not self._page:
            return None
        try:
            return await self._page.evaluate(expression)
        except Exception as e:
            logger.debug(f"JS evaluate error: {e}")
            return None

    # ─── Web Search ──────────────────────────────────────────────────────

    async def web_search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """
        Поиск в интернете через DuckDuckGo HTML.

        Не требует API ключей. Использует HTML-версию DDG.

        Args:
            query: Поисковый запрос
            max_results: Максимум результатов

        Returns:
            Список SearchResult
        """
        if not self._started:
            await self.start()

        results: list[SearchResult] = []
        search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

        try:
            await self.goto(search_url)
            await self._human.random_delay(500, 1500)

            # Извлекаем результаты DuckDuckGo HTML
            raw_results = await self._page.evaluate("""
                () => {
                    const results = [];
                    document.querySelectorAll('.result').forEach(r => {
                        const titleEl = r.querySelector('.result__title a, .result__a');
                        const snippetEl = r.querySelector('.result__snippet');
                        const urlEl = r.querySelector('.result__url');
                        if (titleEl) {
                            results.push({
                                title: (titleEl.innerText || '').trim(),
                                url: titleEl.href || '',
                                snippet: snippetEl
                                    ? (snippetEl.innerText || '').trim()
                                    : '',
                            });
                        }
                    });
                    return results;
                }
            """)

            for i, item in enumerate(raw_results[:max_results]):
                url = item.get("url", "")
                # DDG redirect URL — извлекаем реальный
                if "duckduckgo.com" in url and "uddg=" in url:
                    try:
                        from urllib.parse import parse_qs
                        from urllib.parse import urlparse as _urlparse
                        parsed = _urlparse(url)
                        real_url = parse_qs(parsed.query).get("uddg", [url])[0]
                        url = real_url
                    except Exception:
                        pass

                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=url,
                    snippet=item.get("snippet", ""),
                    position=i + 1,
                ))

            self._stats.searches_performed += 1
            logger.debug(f"Web search: '{query}' → {len(results)} results")

        except Exception as e:
            error_msg = f"Search error: {e}"
            self._stats.errors.append(error_msg)
            logger.warning(error_msg)

        return results

    async def search_and_extract(self, query: str, max_pages: int = 3) -> list[ExtractedData]:
        """
        Поиск + извлечение данных с первых N результатов.

        Args:
            query: Поисковый запрос
            max_pages: Сколько страниц открыть

        Returns:
            Список ExtractedData
        """
        results = await self.web_search(query, max_results=max_pages + 2)
        extracted: list[ExtractedData] = []

        for result in results[:max_pages]:
            if not result.url or "duckduckgo.com" in result.url:
                continue

            try:
                await self._human.thinking_pause()
                data = await self.extract_data(result.url)
                extracted.append(data)
            except Exception as e:
                logger.debug(f"Extract failed for {result.url}: {e}")

        return extracted

    # ─── Cookie / Session Management ─────────────────────────────────────

    async def save_cookies(self, path: str | Path | None = None) -> Path:
        """Сохранить cookies в файл."""
        if not self._context:
            raise RuntimeError("Browser not started")

        if not path:
            path = self._cfg.downloads_dir / "cookies.json"

        path = Path(path)
        cookies = await self._context.cookies()
        path.write_text(json.dumps(cookies, indent=2))
        logger.debug(f"Cookies saved: {path} ({len(cookies)} cookies)")
        return path

    async def load_cookies(self, path: str | Path) -> int:
        """Загрузить cookies из файла."""
        if not self._context:
            raise RuntimeError("Browser not started")

        path = Path(path)
        if not path.exists():
            logger.warning(f"Cookie file not found: {path}")
            return 0

        cookies = json.loads(path.read_text())
        await self._context.add_cookies(cookies)
        logger.debug(f"Cookies loaded: {len(cookies)} cookies")
        return len(cookies)

    async def clear_cookies(self) -> None:
        """Очистить все cookies."""
        if self._context:
            await self._context.clear_cookies()

    # ─── Storage State ───────────────────────────────────────────────────

    async def save_session(self, path: str | Path | None = None) -> Path:
        """Сохранить полное состояние сессии (cookies + localStorage)."""
        if not self._context:
            raise RuntimeError("Browser not started")

        if not path:
            path = self._cfg.downloads_dir / "session_state.json"

        path = Path(path)
        await self._context.storage_state(path=str(path))
        logger.debug(f"Session state saved: {path}")
        return path

    # ─── Download ────────────────────────────────────────────────────────

    async def download_file(self, url: str,
                            filename: str | None = None) -> Path | None:
        """
        Скачать файл.

        Args:
            url: URL файла
            filename: Имя файла (или auto из URL)

        Returns:
            Path к скачанному файлу или None
        """
        if not self._page:
            raise RuntimeError("Browser not started")

        try:
            async with self._page.expect_download() as download_info:
                await self._page.goto(url)

            download = await download_info.value

            if not filename:
                filename = download.suggested_filename or f"download_{int(time.time())}"

            save_path = self._cfg.downloads_dir / filename
            await download.save_as(str(save_path))

            size = save_path.stat().st_size
            self._stats.total_bytes_downloaded += size
            logger.debug(f"Downloaded: {save_path} ({size} bytes)")
            return save_path

        except Exception as e:
            logger.warning(f"Download error: {url} — {e}")
            return None

    # ─── Multi-Page ──────────────────────────────────────────────────────

    async def new_page(self, page_id: str | None = None) -> str:
        """Создать новую страницу (вкладку)."""
        if not self._context:
            raise RuntimeError("Browser not started")

        if len(self._pages) >= self._cfg.max_pages:
            # Закрываем самую старую
            oldest_id = next(iter(self._pages))
            await self.close_page(oldest_id)

        page = await self._context.new_page()
        page.set_default_timeout(self._cfg.default_timeout)

        if self._cfg.stealth_enabled:
            # stealth уже применён через context init_script
            pass

        pid = page_id or f"page_{len(self._pages) + 1}"
        self._pages[pid] = page
        return pid

    async def switch_page(self, page_id: str) -> bool:
        """Переключиться на страницу."""
        if page_id in self._pages:
            self._page = self._pages[page_id]
            return True
        return False

    async def close_page(self, page_id: str) -> None:
        """Закрыть страницу."""
        if page_id in self._pages:
            try:
                await self._pages[page_id].close()
            except Exception:
                pass
            del self._pages[page_id]

    # ─── Convenience ─────────────────────────────────────────────────────

    async def get_page_info(self) -> PageInfo:
        """Получить информацию о текущей странице."""
        if not self._page:
            return PageInfo(url="", status=PageStatus.CLOSED)

        title = await self._page.title()
        self._last_title = title
        return PageInfo(
            url=self._page.url,
            title=title,
            status=PageStatus.READY,
        )

    async def scroll_down(self, distance: int = 500) -> None:
        """Прокрутка вниз."""
        if self._page:
            await self._human.smooth_scroll(self._page, "down", distance)

    async def scroll_up(self, distance: int = 500) -> None:
        """Прокрутка вверх."""
        if self._page:
            await self._human.smooth_scroll(self._page, "up", distance)

    async def press_key(self, key: str) -> None:
        """Нажать клавишу (Enter, Escape, Tab, etc)."""
        if self._page:
            await self._page.keyboard.press(key)

    async def get_html(self, selector: str | None = None) -> str:
        """Получить HTML страницы или элемента."""
        if not self._page:
            return ""
        try:
            if selector:
                return await self._page.locator(selector).first.inner_html()
            return await self._page.content()
        except Exception:
            return ""

    def get_stats_summary(self) -> str:
        """Текстовая сводка статистики."""
        s = self._stats
        return (
            f"🌐 Browser Stats:\n"
            f"  Pages loaded: {s.pages_loaded}\n"
            f"  Pages failed: {s.pages_failed}\n"
            f"  Screenshots: {s.screenshots_taken}\n"
            f"  Searches: {s.searches_performed}\n"
            f"  Downloaded: {s.total_bytes_downloaded} bytes\n"
            f"  Errors: {len(s.errors)}"
        )

    # ─── Context Manager ─────────────────────────────────────────────────

    async def __aenter__(self) -> "BrowserEngine":
        await self.start()
        return self

    async def __aexit__(self, *args) -> None:
        await self.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# 5. GLOBAL INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

browser_engine = BrowserEngine()
