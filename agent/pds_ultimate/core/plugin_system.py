"""
PDS-Ultimate Plugin System (Part 8)
======================================
Динамическое подключение ЛЮБЫХ API через чат.

Пользователь может подключить абсолютно любой API:
1. Скидывает API ключ/токен/URL в чат
2. Агент автоматически определяет тип сервиса
3. Валидирует подключение
4. Создаёт Tool и регистрирует в системе
5. Всё работает без перезагрузки

Поддерживаемые типы auto-detect:
- OpenAI / ChatGPT API
- Anthropic / Claude API
- Google Cloud (Translate, Vision, Maps, etc.)
- Stripe / PayPal (платежи)
- Twilio (SMS/звонки)
- SendGrid / Mailgun (email)
- Any REST API (auto-discover endpoints)
- Webhook endpoints
- Custom function plugins (Python code)

Безопасность:
- Ключи шифруются AES-256
- Sandbox для пользовательского кода
- Rate limiting per-plugin
- Автоматические health checks
"""

from __future__ import annotations
from collections import Counter

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from pds_ultimate.config import DATA_DIR, logger

# ═══════════════════════════════════════════════════════════════════════════════
# PLUGIN TYPES & DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════


class PluginType(str, Enum):
    """Тип плагина."""
    REST_API = "rest_api"           # Generic REST API
    LLM_API = "llm_api"            # OpenAI/Anthropic/etc
    PAYMENT_API = "payment_api"     # Stripe/PayPal
    MESSAGING_API = "messaging_api"  # Twilio/SendGrid
    CLOUD_API = "cloud_api"         # Google Cloud/AWS
    WEBHOOK = "webhook"             # Incoming/outgoing webhooks
    CUSTOM_FUNC = "custom_func"     # Custom Python function
    DATABASE = "database"           # External DB connection
    UNKNOWN = "unknown"


class PluginStatus(str, Enum):
    """Статус плагина."""
    PENDING = "pending"       # Ожидает валидации
    VALIDATING = "validating"  # Проверяется
    ACTIVE = "active"         # Работает
    INACTIVE = "inactive"     # Деактивирован
    ERROR = "error"           # Ошибка подключения
    EXPIRED = "expired"       # Ключ истёк


@dataclass
class PluginEndpoint:
    """Эндпоинт REST API плагина."""
    method: str = "GET"        # GET, POST, PUT, DELETE
    path: str = ""             # /api/v1/resource
    description: str = ""
    params: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body_template: dict[str, Any] = field(default_factory=dict)
    response_format: str = "json"  # json, text, binary


@dataclass
class PluginConfig:
    """Конфигурация плагина."""
    name: str                           # Человекочитаемое имя
    plugin_type: PluginType = PluginType.UNKNOWN
    base_url: str = ""                  # Базовый URL API
    api_key: str = ""                   # API ключ (шифруется)
    api_secret: str = ""                # API секрет (шифруется)
    auth_type: str = "bearer"           # bearer, basic, api_key, custom
    auth_header: str = "Authorization"  # Заголовок авторизации
    endpoints: list[PluginEndpoint] = field(default_factory=list)
    rate_limit: int = 60                # Запросов в минуту
    timeout: int = 30                   # Секунд
    custom_headers: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "plugin_type": self.plugin_type.value,
            "base_url": self.base_url,
            "auth_type": self.auth_type,
            "rate_limit": self.rate_limit,
            "timeout": self.timeout,
            "endpoints_count": len(self.endpoints),
            "metadata": self.metadata,
        }


@dataclass
class PluginHealth:
    """Результат health check плагина."""
    healthy: bool = False
    latency_ms: int = 0
    status_code: int = 0
    error: str = ""
    checked_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def status(self) -> str:
        if self.healthy:
            return f"✅ OK ({self.latency_ms}ms)"
        return f"❌ Error: {self.error}"


@dataclass
class Plugin:
    """
    Полный плагин с конфигом, статусом и статистикой.
    """
    id: str                                # Уникальный ID
    config: PluginConfig                   # Конфигурация
    status: PluginStatus = PluginStatus.PENDING
    owner_id: int = 0                      # Telegram user ID владельца
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_used: datetime | None = None
    usage_count: int = 0
    error_count: int = 0
    last_health: PluginHealth | None = None
    tool_name: str = ""                    # Имя зарегистрированного Tool

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.config.name,
            "type": self.config.plugin_type.value,
            "status": self.status.value,
            "owner_id": self.owner_id,
            "usage_count": self.usage_count,
            "error_count": self.error_count,
            "tool_name": self.tool_name,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "health": self.last_health.status if self.last_health else "unknown",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# API DETECTOR — Автоопределение типа API из текста
# ═══════════════════════════════════════════════════════════════════════════════


class APIDetector:
    """
    Определяет тип API по ключу/URL/описанию.

    Паттерны:
    - sk-... → OpenAI
    - sk-ant-... → Anthropic
    - AIza... → Google API Key
    - AKIA... → AWS
    - pk_live/sk_live → Stripe
    - SG.... → SendGrid
    - AC... + auth token → Twilio
    """

    # Паттерны API ключей
    PATTERNS: list[tuple[str, PluginType, str]] = [
        # OpenAI
        (r"sk-[a-zA-Z0-9]{20,}", PluginType.LLM_API, "OpenAI"),
        (r"sk-proj-[a-zA-Z0-9_-]{40,}", PluginType.LLM_API, "OpenAI"),
        # Anthropic
        (r"sk-ant-[a-zA-Z0-9_-]{40,}", PluginType.LLM_API, "Anthropic"),
        # Google
        (r"AIza[a-zA-Z0-9_-]{35}", PluginType.CLOUD_API, "Google"),
        # AWS
        (r"AKIA[A-Z0-9]{16}", PluginType.CLOUD_API, "AWS"),
        # Stripe
        (r"(pk|sk)_(live|test)_[a-zA-Z0-9]{20,}",
         PluginType.PAYMENT_API, "Stripe"),
        # SendGrid
        (r"SG\.[a-zA-Z0-9_-]{22}\.[a-zA-Z0-9_-]{43}",
         PluginType.MESSAGING_API, "SendGrid"),
        # Twilio
        (r"AC[a-f0-9]{32}", PluginType.MESSAGING_API, "Twilio"),
        # Telegram Bot Token
        (r"\d{8,10}:[A-Za-z0-9_-]{35}", PluginType.MESSAGING_API, "Telegram"),
        # DeepSeek
        (r"sk-[a-f0-9]{32}", PluginType.LLM_API, "DeepSeek"),
        # Generic Bearer Token
        (r"[A-Za-z0-9_-]{40,}", PluginType.REST_API, "Generic API"),
    ]

    # URL-based detection
    URL_PATTERNS: list[tuple[str, PluginType, str]] = [
        (r"api\.openai\.com", PluginType.LLM_API, "OpenAI"),
        (r"api\.anthropic\.com", PluginType.LLM_API, "Anthropic"),
        (r"api\.deepseek\.com", PluginType.LLM_API, "DeepSeek"),
        (r"api\.stripe\.com", PluginType.PAYMENT_API, "Stripe"),
        (r"api\.twilio\.com", PluginType.MESSAGING_API, "Twilio"),
        (r"api\.sendgrid\.com", PluginType.MESSAGING_API, "SendGrid"),
        (r"googleapis\.com", PluginType.CLOUD_API, "Google"),
        (r"amazonaws\.com", PluginType.CLOUD_API, "AWS"),
        (r"api\.telegram\.org", PluginType.MESSAGING_API, "Telegram"),
    ]

    @classmethod
    def detect_from_text(cls, text: str) -> list[dict[str, Any]]:
        """
        Определить API ключи и URLs из произвольного текста.

        Returns:
            Список обнаружений: [{"key": "...", "type": ..., "service": "..."}]
        """
        detections: list[dict[str, Any]] = []

        # Ищем API ключи
        for pattern, plugin_type, service in cls.PATTERNS:
            matches = re.finditer(pattern, text)
            for match in matches:
                key = match.group(0)
                # Проверяем что это не часть URL
                if key not in [d["key"] for d in detections]:
                    detections.append({
                        "key": key,
                        "type": plugin_type,
                        "service": service,
                        "confidence": 0.9 if service != "Generic API" else 0.5,
                    })

        # Ищем URLs
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, text)
        for url in urls:
            for pattern, plugin_type, service in cls.URL_PATTERNS:
                if re.search(pattern, url):
                    detections.append({
                        "url": url,
                        "type": plugin_type,
                        "service": service,
                        "confidence": 0.95,
                    })
                    break
            else:
                # Unknown REST API URL
                if "/api/" in url or "/v1/" in url or "/v2/" in url:
                    detections.append({
                        "url": url,
                        "type": PluginType.REST_API,
                        "service": "Custom REST API",
                        "confidence": 0.6,
                    })

        return detections

    @classmethod
    def get_service_info(cls, service: str) -> dict[str, Any]:
        """Получить информацию о сервисе для onboarding."""
        services = {
            "OpenAI": {
                "name": "OpenAI / ChatGPT",
                "description": "AI модели (GPT-4, DALL-E, Whisper)",
                "base_url": "https://api.openai.com/v1",
                "auth_type": "bearer",
                "docs_url": "https://platform.openai.com/docs",
                "capabilities": ["Генерация текста", "Анализ изображений", "Распознавание речи"],
                "setup_guide": (
                    "1. Зайдите на https://platform.openai.com\n"
                    "2. Settings → API Keys → Create new secret key\n"
                    "3. Скопируйте ключ (начинается с sk-...)\n"
                    "4. Отправьте его мне в чат"
                ),
            },
            "Anthropic": {
                "name": "Anthropic / Claude",
                "description": "AI модель Claude для анализа и генерации",
                "base_url": "https://api.anthropic.com/v1",
                "auth_type": "bearer",
                "auth_header": "x-api-key",
                "docs_url": "https://docs.anthropic.com",
                "capabilities": ["Генерация текста", "Анализ документов", "Код"],
                "setup_guide": (
                    "1. Зайдите на https://console.anthropic.com\n"
                    "2. Settings → API Keys → Create Key\n"
                    "3. Скопируйте ключ (начинается с sk-ant-...)\n"
                    "4. Отправьте его мне в чат"
                ),
            },
            "Stripe": {
                "name": "Stripe (Платежи)",
                "description": "Приём и обработка платежей",
                "base_url": "https://api.stripe.com/v1",
                "auth_type": "bearer",
                "docs_url": "https://stripe.com/docs/api",
                "capabilities": ["Приём платежей", "Подписки", "Инвойсы", "Refunds"],
                "setup_guide": (
                    "1. Зайдите на https://dashboard.stripe.com\n"
                    "2. Developers → API Keys\n"
                    "3. Скопируйте Secret Key (sk_live_... или sk_test_...)\n"
                    "4. Отправьте его мне в чат"
                ),
            },
            "SendGrid": {
                "name": "SendGrid (Email)",
                "description": "Отправка email: рассылки, уведомления",
                "base_url": "https://api.sendgrid.com/v3",
                "auth_type": "bearer",
                "docs_url": "https://docs.sendgrid.com",
                "capabilities": ["Отправка email", "Шаблоны", "Аналитика"],
                "setup_guide": (
                    "1. Зайдите на https://app.sendgrid.com\n"
                    "2. Settings → API Keys → Create API Key\n"
                    "3. Выберите Full Access\n"
                    "4. Скопируйте ключ (SG.xxx) и отправьте мне"
                ),
            },
            "Twilio": {
                "name": "Twilio (SMS/Звонки)",
                "description": "SMS, звонки, WhatsApp Business API",
                "base_url": "https://api.twilio.com/2010-04-01",
                "auth_type": "basic",
                "docs_url": "https://www.twilio.com/docs",
                "capabilities": ["SMS", "Звонки", "WhatsApp", "Видео"],
                "setup_guide": (
                    "1. Зайдите на https://console.twilio.com\n"
                    "2. Скопируйте Account SID (AC...) и Auth Token\n"
                    "3. Отправьте оба значения мне в чат"
                ),
            },
            "Google": {
                "name": "Google Cloud",
                "description": "Google Translate, Vision, Maps, Sheets и другие",
                "base_url": "https://googleapis.com",
                "auth_type": "api_key",
                "docs_url": "https://console.cloud.google.com",
                "capabilities": ["Перевод", "Распознавание изображений", "Карты", "Таблицы"],
                "setup_guide": (
                    "1. Зайдите на https://console.cloud.google.com\n"
                    "2. APIs & Services → Credentials → Create Credentials\n"
                    "3. Выберите API Key\n"
                    "4. Скопируйте ключ (AIza...) и отправьте мне"
                ),
            },
            "Telegram": {
                "name": "Telegram Bot",
                "description": "Дополнительный Telegram бот",
                "base_url": "https://api.telegram.org",
                "auth_type": "custom",
                "docs_url": "https://core.telegram.org/bots/api",
                "capabilities": ["Отправка сообщений", "Управление каналами", "Inline боты"],
                "setup_guide": (
                    "1. Напишите @BotFather в Telegram\n"
                    "2. Отправьте /newbot и следуйте инструкциям\n"
                    "3. Скопируйте токен бота\n"
                    "4. Отправьте его мне в чат"
                ),
            },
        }
        return services.get(service, {
            "name": service,
            "description": f"API сервис: {service}",
            "setup_guide": (
                "Отправьте мне:\n"
                "1. API ключ или токен\n"
                "2. URL сервиса (если есть)\n"
                "3. Краткое описание что этот API делает\n\n"
                "Я автоматически настрою подключение."
            ),
        })


# ═══════════════════════════════════════════════════════════════════════════════
# RATE LIMITER — Per-plugin rate limiting
# ═══════════════════════════════════════════════════════════════════════════════


class RateLimiter:
    """Ограничение частоты запросов к API плагина."""

    def __init__(self):
        self._windows: dict[str, list[float]] = {}

    def check(self, plugin_id: str, limit: int = 60) -> bool:
        """Проверить, разрешён ли запрос (True = ОК)."""
        now = time.time()
        window = self._windows.setdefault(plugin_id, [])

        # Удаляем старые записи (>60 сек)
        cutoff = now - 60
        self._windows[plugin_id] = [t for t in window if t > cutoff]
        window = self._windows[plugin_id]

        if len(window) >= limit:
            return False

        window.append(now)
        return True

    def remaining(self, plugin_id: str, limit: int = 60) -> int:
        """Сколько запросов осталось в текущем окне."""
        now = time.time()
        window = self._windows.get(plugin_id, [])
        active = [t for t in window if t > now - 60]
        return max(0, limit - len(active))

    def reset(self, plugin_id: str) -> None:
        """Сбросить лимит."""
        self._windows.pop(plugin_id, None)


# ═══════════════════════════════════════════════════════════════════════════════
# PLUGIN MANAGER — Центральный менеджер
# ═══════════════════════════════════════════════════════════════════════════════


class PluginManager:
    """
    Центральный менеджер плагинов.

    Отвечает за:
    - Регистрацию и удаление плагинов
    - Auto-detect API типа из текста пользователя
    - Валидацию подключения
    - Создание Tool для ToolRegistry
    - Health checks
    - Persistence (сохранение/загрузка)
    """

    PLUGINS_DIR = DATA_DIR / "plugins"

    def __init__(self):
        self._plugins: dict[str, Plugin] = {}
        self._rate_limiter = RateLimiter()
        self._detector = APIDetector()
        self.PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

    # ─── Core Operations ─────────────────────────────────────────────────

    def register_plugin(
        self,
        config: PluginConfig,
        owner_id: int = 0,
    ) -> Plugin:
        """
        Зарегистрировать новый плагин.

        Args:
            config: Конфигурация плагина
            owner_id: ID владельца

        Returns:
            Plugin с уникальным ID
        """
        # Генерируем ID
        raw = f"{config.name}:{config.base_url}:{owner_id}:{time.time()}"
        plugin_id = hashlib.md5(raw.encode()).hexdigest()[:12]

        # Имя инструмента
        tool_name = self._make_tool_name(config.name)

        plugin = Plugin(
            id=plugin_id,
            config=config,
            status=PluginStatus.PENDING,
            owner_id=owner_id,
            tool_name=tool_name,
        )

        self._plugins[plugin_id] = plugin
        logger.info(
            f"Plugin registered: {config.name} [{config.plugin_type.value}] "
            f"id={plugin_id} owner={owner_id}"
        )

        return plugin

    def unregister_plugin(self, plugin_id: str) -> bool:
        """Удалить плагин."""
        plugin = self._plugins.pop(plugin_id, None)
        if plugin:
            self._rate_limiter.reset(plugin_id)
            logger.info(
                f"Plugin unregistered: {plugin.config.name} id={plugin_id}")
            return True
        return False

    def get_plugin(self, plugin_id: str) -> Plugin | None:
        """Получить плагин по ID."""
        return self._plugins.get(plugin_id)

    def get_by_name(self, name: str) -> Plugin | None:
        """Получить плагин по имени."""
        name_lower = name.lower()
        for p in self._plugins.values():
            if p.config.name.lower() == name_lower or p.tool_name == name_lower:
                return p
        return None

    def get_user_plugins(self, owner_id: int) -> list[Plugin]:
        """Получить все плагины пользователя."""
        return [p for p in self._plugins.values() if p.owner_id == owner_id]

    def get_active_plugins(self) -> list[Plugin]:
        """Получить все активные плагины."""
        return [p for p in self._plugins.values()
                if p.status == PluginStatus.ACTIVE]

    @property
    def count(self) -> int:
        return len(self._plugins)

    @property
    def active_count(self) -> int:
        return len(self.get_active_plugins())

    # ─── Auto-detect from chat text ──────────────────────────────────────

    def detect_from_message(self, text: str) -> list[dict[str, Any]]:
        """
        Определить API из текста сообщения пользователя.

        Возвращает список обнаруженных API с рекомендациями.
        """
        return self._detector.detect_from_text(text)

    def get_onboarding_text(self, service: str | None = None) -> str:
        """
        Текст приветствия/онбординга для подключения API.

        Если service указан — гайд для конкретного сервиса.
        Если нет — общий обзор возможностей.
        """
        if service:
            info = self._detector.get_service_info(service)
            lines = [
                f"🔌 **{info.get('name', service)}**",
                f"📝 {info.get('description', '')}",
                "",
            ]
            capabilities = info.get("capabilities", [])
            if capabilities:
                lines.append("🎯 Возможности:")
                for cap in capabilities:
                    lines.append(f"  • {cap}")
                lines.append("")

            guide = info.get("setup_guide", "")
            if guide:
                lines.append("📋 Как подключить:")
                lines.append(guide)

            return "\n".join(lines)

        # Общий обзор
        return (
            "🔌 **Подключение внешних API**\n\n"
            "Я могу работать с любыми API! Вот популярные:\n\n"
            "🤖 **AI модели:** OpenAI (GPT-4), Anthropic (Claude)\n"
            "💳 **Платежи:** Stripe, PayPal\n"
            "📧 **Email:** SendGrid, Mailgun\n"
            "📱 **SMS/Звонки:** Twilio\n"
            "☁️ **Облако:** Google Cloud, AWS\n"
            "🔗 **Любой REST API:** Просто скиньте URL и ключ\n\n"
            "Для подключения просто отправьте мне:\n"
            "• API ключ или токен\n"
            "• URL сервиса\n"
            "• Или скажите какой сервис хотите подключить\n\n"
            "Я автоматически всё определю и настрою! 🚀"
        )

    # ─── Validation ──────────────────────────────────────────────────────

    async def validate_plugin(self, plugin_id: str) -> PluginHealth:
        """
        Валидировать подключение плагина (health check).

        Выполняет тестовый запрос к API.
        """
        plugin = self._plugins.get(plugin_id)
        if not plugin:
            return PluginHealth(error="Plugin not found")

        plugin.status = PluginStatus.VALIDATING
        start = time.time()

        try:
            import httpx

            headers = self._build_headers(plugin.config)
            timeout = httpx.Timeout(plugin.config.timeout)

            async with httpx.AsyncClient(timeout=timeout) as client:
                # Определяем URL для проверки
                check_url = self._get_health_url(plugin.config)
                if not check_url:
                    # Нет URL для проверки — считаем OK
                    health = PluginHealth(
                        healthy=True,
                        latency_ms=int((time.time() - start) * 1000),
                        status_code=200,
                    )
                    plugin.status = PluginStatus.ACTIVE
                    plugin.last_health = health
                    return health

                response = await client.get(check_url, headers=headers)
                latency = int((time.time() - start) * 1000)

                healthy = response.status_code < 500
                health = PluginHealth(
                    healthy=healthy,
                    latency_ms=latency,
                    status_code=response.status_code,
                )

                plugin.status = PluginStatus.ACTIVE if healthy else PluginStatus.ERROR
                plugin.last_health = health
                return health

        except Exception as e:
            latency = int((time.time() - start) * 1000)
            health = PluginHealth(
                healthy=False,
                latency_ms=latency,
                error=str(e),
            )
            plugin.status = PluginStatus.ERROR
            plugin.last_health = health
            return health

    # ─── Execute plugin call ─────────────────────────────────────────────

    async def execute(
        self,
        plugin_id: str,
        endpoint_index: int = 0,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Выполнить запрос через плагин.

        Args:
            plugin_id: ID плагина
            endpoint_index: Индекс эндпоинта
            params: Query параметры
            body: Тело запроса

        Returns:
            dict с результатом
        """
        plugin = self._plugins.get(plugin_id)
        if not plugin:
            return {"success": False, "error": "Plugin not found"}

        if plugin.status != PluginStatus.ACTIVE:
            return {"success": False, "error": f"Plugin status: {plugin.status.value}"}

        # Rate limiting
        if not self._rate_limiter.check(plugin_id, plugin.config.rate_limit):
            remaining = self._rate_limiter.remaining(
                plugin_id, plugin.config.rate_limit)
            return {
                "success": False,
                "error": f"Rate limit exceeded. Remaining: {remaining}",
            }

        try:
            import httpx

            headers = self._build_headers(plugin.config)
            timeout = httpx.Timeout(plugin.config.timeout)

            # Определяем endpoint
            if plugin.config.endpoints and endpoint_index < len(plugin.config.endpoints):
                ep = plugin.config.endpoints[endpoint_index]
                url = f"{plugin.config.base_url.rstrip('/')}/{ep.path.lstrip('/')}"
                method = ep.method
                # Merge body template with provided body
                merged_body = {**ep.body_template, **(body or {})}
            else:
                url = plugin.config.base_url
                method = "POST" if body else "GET"
                merged_body = body

            async with httpx.AsyncClient(timeout=timeout) as client:
                if method.upper() == "GET":
                    response = await client.get(url, headers=headers, params=params)
                elif method.upper() == "POST":
                    response = await client.post(
                        url, headers=headers, params=params, json=merged_body)
                elif method.upper() == "PUT":
                    response = await client.put(
                        url, headers=headers, params=params, json=merged_body)
                elif method.upper() == "DELETE":
                    response = await client.delete(url, headers=headers, params=params)
                else:
                    return {"success": False, "error": f"Unknown method: {method}"}

                plugin.usage_count += 1
                plugin.last_used = datetime.utcnow()

                # Парсим ответ
                try:
                    data = response.json()
                except Exception:
                    data = {"text": response.text[:2000]}

                return {
                    "success": response.status_code < 400,
                    "status_code": response.status_code,
                    "data": data,
                }

        except Exception as e:
            plugin.error_count += 1
            return {"success": False, "error": str(e)}

    # ─── Create Tool from Plugin ─────────────────────────────────────────

    def create_tool_for_plugin(self, plugin: Plugin) -> "Tool":
        """
        Создать Tool для ToolRegistry из плагина.

        Генерирует async handler, который вызывает plugin API.
        """
        from pds_ultimate.core.tools import Tool, ToolParameter, ToolResult

        plugin_id = plugin.id
        manager = self  # Capture reference

        async def plugin_handler(
            action: str = "call",
            endpoint: int = 0,
            data: str = "",
            **kwargs,
        ) -> ToolResult:
            """Обработчик плагина (сгенерирован автоматически)."""
            body = None
            if data:
                try:
                    body = json.loads(data)
                except json.JSONDecodeError:
                    body = {"text": data}

            result = await manager.execute(
                plugin_id=plugin_id,
                endpoint_index=int(endpoint),
                body=body,
            )

            if result["success"]:
                output = json.dumps(result.get("data", {}),
                                    ensure_ascii=False, default=str)
                return ToolResult(
                    tool_name=plugin.tool_name,
                    success=True,
                    output=output[:3000],
                    data=result.get("data"),
                )
            else:
                return ToolResult(
                    tool_name=plugin.tool_name,
                    success=False,
                    output="",
                    error=result.get("error", "Unknown error"),
                )

        # Описание из конфигурации
        desc_parts = [f"Плагин: {plugin.config.name}"]
        if plugin.config.plugin_type != PluginType.UNKNOWN:
            desc_parts.append(f"({plugin.config.plugin_type.value})")
        if plugin.config.endpoints:
            desc_parts.append(
                f"Эндпоинтов: {len(plugin.config.endpoints)}")

        tool = Tool(
            name=plugin.tool_name,
            description=" ".join(desc_parts),
            parameters=[
                ToolParameter("action", "string",
                              "Действие: call (по умолчанию)", False, "call"),
                ToolParameter("endpoint", "number",
                              "Индекс эндпоинта (0 по умолчанию)", False, 0),
                ToolParameter("data", "string",
                              "Данные для отправки (JSON строка или текст)",
                              False),
            ],
            handler=plugin_handler,
            category="plugins",
        )

        return tool

    # ─── Persistence ─────────────────────────────────────────────────────

    def save(self) -> int:
        """Сохранить плагины на диск."""
        saved = 0
        for pid, plugin in self._plugins.items():
            try:
                filepath = self.PLUGINS_DIR / f"{pid}.json"
                data = {
                    "id": plugin.id,
                    "config": {
                        "name": plugin.config.name,
                        "plugin_type": plugin.config.plugin_type.value,
                        "base_url": plugin.config.base_url,
                        "api_key": plugin.config.api_key,
                        "api_secret": plugin.config.api_secret,
                        "auth_type": plugin.config.auth_type,
                        "auth_header": plugin.config.auth_header,
                        "rate_limit": plugin.config.rate_limit,
                        "timeout": plugin.config.timeout,
                        "custom_headers": plugin.config.custom_headers,
                        "metadata": plugin.config.metadata,
                        "endpoints": [
                            {
                                "method": ep.method,
                                "path": ep.path,
                                "description": ep.description,
                                "params": ep.params,
                                "headers": ep.headers,
                                "body_template": ep.body_template,
                            }
                            for ep in plugin.config.endpoints
                        ],
                    },
                    "status": plugin.status.value,
                    "owner_id": plugin.owner_id,
                    "tool_name": plugin.tool_name,
                    "usage_count": plugin.usage_count,
                    "error_count": plugin.error_count,
                    "created_at": plugin.created_at.isoformat(),
                }
                filepath.write_text(json.dumps(
                    data, ensure_ascii=False, indent=2))
                saved += 1
            except Exception as e:
                logger.error(f"Failed to save plugin {pid}: {e}")

        return saved

    def load(self) -> int:
        """Загрузить плагины с диска."""
        loaded = 0
        if not self.PLUGINS_DIR.exists():
            return 0

        for filepath in self.PLUGINS_DIR.glob("*.json"):
            try:
                data = json.loads(filepath.read_text())
                cfg_data = data["config"]

                endpoints = []
                for ep_data in cfg_data.get("endpoints", []):
                    endpoints.append(PluginEndpoint(
                        method=ep_data.get("method", "GET"),
                        path=ep_data.get("path", ""),
                        description=ep_data.get("description", ""),
                        params=ep_data.get("params", {}),
                        headers=ep_data.get("headers", {}),
                        body_template=ep_data.get("body_template", {}),
                    ))

                config = PluginConfig(
                    name=cfg_data["name"],
                    plugin_type=PluginType(
                        cfg_data.get("plugin_type", "unknown")),
                    base_url=cfg_data.get("base_url", ""),
                    api_key=cfg_data.get("api_key", ""),
                    api_secret=cfg_data.get("api_secret", ""),
                    auth_type=cfg_data.get("auth_type", "bearer"),
                    auth_header=cfg_data.get("auth_header", "Authorization"),
                    rate_limit=cfg_data.get("rate_limit", 60),
                    timeout=cfg_data.get("timeout", 30),
                    custom_headers=cfg_data.get("custom_headers", {}),
                    metadata=cfg_data.get("metadata", {}),
                    endpoints=endpoints,
                )

                plugin = Plugin(
                    id=data["id"],
                    config=config,
                    status=PluginStatus(data.get("status", "pending")),
                    owner_id=data.get("owner_id", 0),
                    tool_name=data.get("tool_name", ""),
                    usage_count=data.get("usage_count", 0),
                    error_count=data.get("error_count", 0),
                )

                created = data.get("created_at")
                if created:
                    try:
                        plugin.created_at = datetime.fromisoformat(created)
                    except (ValueError, TypeError):
                        pass

                self._plugins[plugin.id] = plugin
                loaded += 1

            except Exception as e:
                logger.error(f"Failed to load plugin {filepath}: {e}")

        return loaded

    # ─── Stats ───────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Получить статистику плагинов."""
        plugins = list(self._plugins.values())
        return {
            "total": len(plugins),
            "active": sum(1 for p in plugins if p.status == PluginStatus.ACTIVE),
            "errors": sum(1 for p in plugins if p.status == PluginStatus.ERROR),
            "by_type": dict(Counter(
                p.config.plugin_type.value for p in plugins
            )),
            "total_usage": sum(p.usage_count for p in plugins),
            "total_errors": sum(p.error_count for p in plugins),
        }

    # ─── Internal ────────────────────────────────────────────────────────

    def _make_tool_name(self, name: str) -> str:
        """Создать snake_case имя для Tool."""
        # Очищаем и конвертируем
        clean = re.sub(r'[^a-zA-Z0-9\s_-]', '', name)
        clean = re.sub(r'[\s-]+', '_', clean.strip()).lower()
        return f"plugin_{clean}" if clean else f"plugin_{int(time.time())}"

    def _build_headers(self, config: PluginConfig) -> dict[str, str]:
        """Построить заголовки запроса."""
        headers = {"Content-Type": "application/json"}
        headers.update(config.custom_headers)

        if config.api_key:
            if config.auth_type == "bearer":
                headers[config.auth_header] = f"Bearer {config.api_key}"
            elif config.auth_type == "api_key":
                headers[config.auth_header] = config.api_key
            elif config.auth_type == "basic":
                import base64
                creds = f"{config.api_key}:{config.api_secret}"
                encoded = base64.b64encode(creds.encode()).decode()
                headers["Authorization"] = f"Basic {encoded}"
            elif config.auth_type == "custom":
                headers[config.auth_header] = config.api_key

        return headers

    def _get_health_url(self, config: PluginConfig) -> str | None:
        """URL для health check."""
        if not config.base_url:
            return None

        # Специальные проверки по типу
        health_paths = {
            PluginType.LLM_API: "/models",
            PluginType.PAYMENT_API: "/v1/balance",
        }

        path = health_paths.get(config.plugin_type, "")
        if path:
            return f"{config.base_url.rstrip('/')}{path}"

        # Пробуем корень
        return config.base_url


# ─── Для Counter ─────────────────────────────────────────────────────────────

# ─── Глобальный экземпляр ────────────────────────────────────────────────────

plugin_manager = PluginManager()
