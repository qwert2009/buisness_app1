"""
PDS-Ultimate Tests — User Manager (Part 1)
=============================================
Тесты для многопользовательской системы и динамического API.

Покрытие:
1. Шифрование/дешифрование API ключей
2. Маскировка ключей
3. Идентификация владельца (имя, алиасы)
4. Регистрация пользователей (owner vs user)
5. Сохранение и чтение API конфигов
6. Автодетект API-ключей из текста
7. Управление API (список, удаление)
8. Onboarding сообщения
9. Кэширование профилей
10. Модели UserProfile и UserAPIConfig
11. ConversationState новые состояния
12. AuthMiddleware multi-user логика
"""

from __future__ import annotations

import json

import pytest

from pds_ultimate.bot.conversation import ConversationState
from pds_ultimate.core.database import UserAPIConfig, UserProfile
from pds_ultimate.core.user_manager import (
    API_KEY_PATTERNS,
    SUPPORTED_APIS,
    UserManager,
    decrypt_value,
    encrypt_value,
    mask_key,
)

# ═══════════════════════════════════════════════════════════════════════════════
# 1. Шифрование / дешифрование
# ═══════════════════════════════════════════════════════════════════════════════


class TestEncryption:
    """Тесты шифрования API ключей."""

    def test_encrypt_decrypt_roundtrip(self):
        """Шифрование и дешифрование возвращают оригинал."""
        original = "sk-9025b951982c474a9c4ab70d31ad98e8"
        encrypted = encrypt_value(original)
        assert encrypted != original
        decrypted = decrypt_value(encrypted)
        assert decrypted == original

    def test_encrypt_different_values(self):
        """Разные значения дают разные шифротексты."""
        enc1 = encrypt_value("key-aaa")
        enc2 = encrypt_value("key-bbb")
        assert enc1 != enc2

    def test_encrypt_empty_string(self):
        """Шифрование пустой строки."""
        encrypted = encrypt_value("")
        decrypted = decrypt_value(encrypted)
        assert decrypted == ""

    def test_encrypt_unicode(self):
        """Шифрование юникода."""
        original = "ключ-API-кириллица-🔑"
        encrypted = encrypt_value(original)
        decrypted = decrypt_value(encrypted)
        assert decrypted == original

    def test_decrypt_invalid_returns_empty(self):
        """Невалидный шифротекст → пустая строка."""
        result = decrypt_value("invalid_garbage_data")
        assert result == ""


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Маскировка ключей
# ═══════════════════════════════════════════════════════════════════════════════

class TestMaskKey:
    """Тесты маскировки API ключей для отображения."""

    def test_mask_normal_key(self):
        """Обычный ключ маскируется: sk-xx...xxxx."""
        result = mask_key("sk-9025b951982c474a9c4ab70d31ad98e8")
        assert result.startswith("sk-9")
        assert result.endswith("98e8")
        assert "..." in result

    def test_mask_short_key(self):
        """Короткий ключ (<= 8 символов) → звёздочки."""
        assert mask_key("abc") == "***"
        assert mask_key("12345678") == "***"

    def test_mask_9_chars(self):
        """9 символов — уже маскируется."""
        result = mask_key("123456789")
        assert "..." in result


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Идентификация владельца
# ═══════════════════════════════════════════════════════════════════════════════

class TestOwnerIdentification:
    """Тесты идентификации владельца по имени."""

    def setup_method(self):
        self.um = UserManager()

    def test_owner_exact_name(self):
        """Точное имя владельца."""
        assert self.um.is_owner("Вячеслав Амбарцумов") is True

    def test_owner_lowercase(self):
        """Имя в нижнем регистре."""
        assert self.um.is_owner("вячеслав амбарцумов") is True

    def test_owner_mixed_case(self):
        """Смешанный регистр."""
        assert self.um.is_owner("ВЯЧЕСЛАВ АМБАРЦУМОВ") is True

    def test_owner_alias_slavik(self):
        """Алиас: Славик."""
        assert self.um.is_owner("славик") is True
        assert self.um.is_owner("Славик") is True

    def test_owner_alias_english(self):
        """Английский алиас."""
        assert self.um.is_owner("vyacheslav ambartsumov") is True

    def test_not_owner(self):
        """Другое имя — не владелец."""
        assert self.um.is_owner("Иван Петров") is False
        assert self.um.is_owner("John Smith") is False

    def test_not_owner_empty(self):
        """Пустое имя — не владелец."""
        assert self.um.is_owner("") is False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Регистрация пользователей
# ═══════════════════════════════════════════════════════════════════════════════

class TestUserRegistration:
    """Тесты регистрации пользователей."""

    def setup_method(self):
        self.um = UserManager()

    @pytest.mark.asyncio
    async def test_register_owner(self, db_session):
        """Регистрация владельца — роль owner."""
        profile = await self.um.register_user(
            chat_id=1129704360,
            name="Вячеслав Амбарцумов",
            db_session=db_session,
        )
        assert profile["role"] == "owner"
        assert profile["name"] == "Вячеслав Амбарцумов"

    @pytest.mark.asyncio
    async def test_register_regular_user(self, db_session):
        """Регистрация обычного пользователя — роль user."""
        profile = await self.um.register_user(
            chat_id=12345678,
            name="Иван Петров",
            db_session=db_session,
        )
        assert profile["role"] == "user"
        assert profile["name"] == "Иван Петров"
        assert profile["onboarding_complete"] is False

    @pytest.mark.asyncio
    async def test_register_owner_has_apis(self, db_session):
        """Владелец после регистрации имеет предустановленные API."""
        await self.um.register_user(
            chat_id=1129704360,
            name="Вячеслав Амбарцумов",
            db_session=db_session,
        )
        apis = self.um.get_user_apis(1129704360, db_session)
        api_types = [a["api_type"] for a in apis]
        assert "deepseek" in api_types
        assert "telegram_bot" in api_types

    @pytest.mark.asyncio
    async def test_register_regular_user_no_apis(self, db_session):
        """Обычный пользователь после регистрации не имеет API."""
        await self.um.register_user(
            chat_id=99999999,
            name="Тест Юзер",
            db_session=db_session,
        )
        apis = self.um.get_user_apis(99999999, db_session)
        assert len(apis) == 0

    @pytest.mark.asyncio
    async def test_re_register_updates_profile(self, db_session):
        """Повторная регистрация обновляет данные."""
        await self.um.register_user(
            chat_id=55555555,
            name="Старое Имя",
            db_session=db_session,
        )
        profile2 = await self.um.register_user(
            chat_id=55555555,
            name="Новое Имя",
            db_session=db_session,
        )
        assert profile2["name"] == "Новое Имя"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Профиль и проверка регистрации
# ═══════════════════════════════════════════════════════════════════════════════

class TestProfileAndRegistration:
    """Тесты проверки профиля и регистрации."""

    def setup_method(self):
        self.um = UserManager()

    @pytest.mark.asyncio
    async def test_is_registered_true(self, db_session):
        """Зарегистрированный пользователь = True."""
        await self.um.register_user(111, "Тест", db_session)
        assert self.um.is_registered(111, db_session) is True

    def test_is_registered_false(self, db_session):
        """Незарегистрированный пользователь = False."""
        assert self.um.is_registered(999, db_session) is False

    @pytest.mark.asyncio
    async def test_get_profile_exists(self, db_session):
        """Получение профиля существующего пользователя."""
        await self.um.register_user(222, "Аня", db_session)
        profile = self.um.get_profile(222, db_session)
        assert profile is not None
        assert profile["name"] == "Аня"
        assert profile["chat_id"] == 222

    def test_get_profile_not_exists(self, db_session):
        """Получение профиля несуществующего пользователя."""
        profile = self.um.get_profile(999, db_session)
        assert profile is None

    @pytest.mark.asyncio
    async def test_profile_cache(self, db_session):
        """Кэш профилей работает."""
        await self.um.register_user(333, "Кэш Тест", db_session)
        p1 = self.um.get_profile(333, db_session)
        p2 = self.um.get_profile(333, db_session)
        assert p1 is p2  # Тот же объект (из кэша)

    @pytest.mark.asyncio
    async def test_invalidate_cache(self, db_session):
        """Инвалидация кэша работает."""
        await self.um.register_user(444, "Инвалидация", db_session)
        self.um.get_profile(444, db_session)
        assert 444 in self.um._profiles
        self.um.invalidate_cache(444)
        assert 444 not in self.um._profiles


# ═══════════════════════════════════════════════════════════════════════════════
# 6. API Configuration (save / get / list / remove)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAPIConfig:
    """Тесты управления API конфигурациями."""

    def setup_method(self):
        self.um = UserManager()

    @pytest.mark.asyncio
    async def test_save_and_get_api_config(self, db_session):
        """Сохранение и чтение API конфига."""
        await self.um.register_user(500, "API Тест", db_session)
        self.um._save_api_config(
            500, "openai",
            {"api_key": "sk-test123456789abc", "model": "gpt-4"},
            db_session, validated=True,
        )
        db_session.flush()

        cfg = self.um.get_api_config(500, "openai", db_session)
        assert cfg is not None
        assert cfg["api_key"] == "sk-test123456789abc"
        assert cfg["model"] == "gpt-4"

    @pytest.mark.asyncio
    async def test_api_key_is_encrypted_in_db(self, db_session):
        """API ключ зашифрован в БД."""
        await self.um.register_user(501, "Enc Тест", db_session)
        self.um._save_api_config(
            501, "deepseek",
            {"api_key": "sk-mysecretkey12345"},
            db_session, validated=False,
        )
        db_session.flush()

        # Проверяем сырые данные в БД
        raw = db_session.query(UserAPIConfig).filter_by(
            chat_id=501, api_type="deepseek"
        ).first()
        assert raw is not None
        data = json.loads(raw.config_data)
        # Ключ НЕ должен быть в открытом виде
        assert data["api_key"] != "sk-mysecretkey12345"

    @pytest.mark.asyncio
    async def test_get_user_apis(self, db_session):
        """Получение списка подключённых API."""
        await self.um.register_user(502, "List Тест", db_session)
        self.um._save_api_config(502, "openai", {"api_key": "k1"}, db_session)
        self.um._save_api_config(
            502, "anthropic", {"api_key": "k2"}, db_session)
        db_session.flush()

        apis = self.um.get_user_apis(502, db_session)
        assert len(apis) == 2
        types = [a["api_type"] for a in apis]
        assert "openai" in types
        assert "anthropic" in types

    @pytest.mark.asyncio
    async def test_remove_api(self, db_session):
        """Удаление (деактивация) API."""
        await self.um.register_user(503, "Remove Тест", db_session)
        self.um._save_api_config(503, "openai", {"api_key": "k1"}, db_session)
        db_session.flush()

        assert self.um.remove_api(503, "openai", db_session) is True
        apis = self.um.get_user_apis(503, db_session)
        assert len(apis) == 0

    @pytest.mark.asyncio
    async def test_remove_nonexistent_api(self, db_session):
        """Удаление несуществующего API → False."""
        await self.um.register_user(504, "NoAPI", db_session)
        assert self.um.remove_api(504, "openai", db_session) is False

    @pytest.mark.asyncio
    async def test_upsert_api_config(self, db_session):
        """Повторное сохранение API обновляет конфиг."""
        await self.um.register_user(505, "Upsert", db_session)
        self.um._save_api_config(505, "openai", {"api_key": "old"}, db_session)
        db_session.flush()
        self.um._save_api_config(
            505, "openai", {"api_key": "new-key"}, db_session, validated=True)
        db_session.flush()

        cfg = self.um.get_api_config(505, "openai", db_session)
        assert cfg["api_key"] == "new-key"

        # Должна быть 1 запись, не 2
        count = db_session.query(UserAPIConfig).filter_by(
            chat_id=505, api_type="openai"
        ).count()
        assert count == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Автодетект API ключей из текста
# ═══════════════════════════════════════════════════════════════════════════════

class TestAPIDetection:
    """Тесты автоматического определения API из текста."""

    def setup_method(self):
        self.um = UserManager()

    @pytest.mark.asyncio
    async def test_detect_deepseek_key(self, db_session):
        """Распознавание DeepSeek API ключа."""
        await self.um.register_user(600, "Detect", db_session)
        result = await self.um.detect_and_save_api(
            600, "sk-9025b951982c474a9c4ab70d31ad98e8 deepseek", db_session
        )
        assert result is not None
        assert result["api_type"] == "deepseek"

    @pytest.mark.asyncio
    async def test_detect_anthropic_key(self, db_session):
        """Распознавание Anthropic API ключа."""
        await self.um.register_user(601, "Detect2", db_session)
        result = await self.um.detect_and_save_api(
            601, "sk-ant-api03-abcdefghijklmnopqrstuvwxyz123456", db_session
        )
        assert result is not None
        assert result["api_type"] == "anthropic"

    @pytest.mark.asyncio
    async def test_detect_telegram_token(self, db_session):
        """Распознавание Telegram Bot Token."""
        await self.um.register_user(602, "Detect3", db_session)
        result = await self.um.detect_and_save_api(
            602, "8500002088:AAFbWonMQql6XnfbyTARSZ5bPNDAALCNuVA", db_session
        )
        assert result is not None
        assert result["api_type"] == "telegram_bot"

    @pytest.mark.asyncio
    async def test_detect_custom_api_url(self, db_session):
        """Распознавание custom API по URL."""
        await self.um.register_user(603, "Detect4", db_session)
        result = await self.um.detect_and_save_api(
            603, "https://my-api.example.com/v1 api endpoint", db_session
        )
        assert result is not None
        assert result["api_type"] == "custom_api"

    @pytest.mark.asyncio
    async def test_detect_nothing(self, db_session):
        """Обычный текст — ничего не определяется."""
        await self.um.register_user(604, "Detect5", db_session)
        result = await self.um.detect_and_save_api(
            604, "привет, как дела?", db_session
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_detect_json_credentials(self, db_session):
        """Распознавание JSON с OAuth credentials."""
        await self.um.register_user(605, "JSON", db_session)
        creds = json.dumps({
            "client_id": "123.apps.googleusercontent.com",
            "client_secret": "abc123secret",
        })
        result = await self.um.detect_and_save_api(605, creds, db_session)
        assert result is not None
        assert result["api_type"] == "gmail"


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Onboarding сообщения
# ═══════════════════════════════════════════════════════════════════════════════

class TestOnboarding:
    """Тесты onboarding сообщений."""

    def setup_method(self):
        self.um = UserManager()

    def test_onboarding_message(self):
        """Onboarding сообщение содержит инструкции."""
        msg = self.um.get_onboarding_message()
        assert "API" in msg
        assert "DeepSeek" in msg
        assert "подключить" in msg.lower() or "скинь" in msg.lower()

    @pytest.mark.asyncio
    async def test_connected_apis_empty(self, db_session):
        """Сообщение о подключённых API — пустой список."""
        await self.um.register_user(700, "NoAPIs", db_session)
        msg = self.um.get_connected_apis_message(700, db_session)
        assert "ничего не подключено" in msg.lower() or "подключённые" in msg.lower()

    @pytest.mark.asyncio
    async def test_connected_apis_with_entries(self, db_session):
        """Сообщение о подключённых API — есть API."""
        await self.um.register_user(701, "HasAPIs", db_session)
        self.um._save_api_config(
            701, "deepseek", {"api_key": "test"}, db_session, validated=True)
        db_session.flush()
        msg = self.um.get_connected_apis_message(701, db_session)
        assert "DeepSeek" in msg
        assert "✅" in msg

    def test_setup_guide_deepseek(self):
        """Гайд по DeepSeek."""
        guide = self.um.get_api_setup_guide("deepseek")
        assert "deepseek" in guide.lower() or "DeepSeek" in guide

    def test_setup_guide_unknown(self):
        """Гайд для неизвестного API."""
        guide = self.um.get_api_setup_guide("nonexistent_api_xyz")
        assert "❌" in guide or "Неизвестный" in guide


# ═══════════════════════════════════════════════════════════════════════════════
# 9. DB Models: UserProfile, UserAPIConfig
# ═══════════════════════════════════════════════════════════════════════════════

class TestDBModels:
    """Тесты ORM-моделей пользователей."""

    def test_create_user_profile(self, db_session):
        """Создание UserProfile."""
        user = UserProfile(
            chat_id=9999,
            name="Тест Модель",
            role="user",
        )
        db_session.add(user)
        db_session.flush()

        found = db_session.query(UserProfile).filter_by(chat_id=9999).first()
        assert found is not None
        assert found.name == "Тест Модель"
        assert found.role == "user"
        assert found.is_active is True
        assert found.onboarding_complete is False

    def test_create_user_api_config(self, db_session):
        """Создание UserAPIConfig с FK."""
        user = UserProfile(chat_id=8888, name="FK Тест", role="user")
        db_session.add(user)
        db_session.flush()

        api = UserAPIConfig(
            chat_id=8888,
            api_type="openai",
            api_name="OpenAI API",
            config_data='{"api_key": "encrypted"}',
        )
        db_session.add(api)
        db_session.flush()

        found = db_session.query(UserAPIConfig).filter_by(chat_id=8888).first()
        assert found is not None
        assert found.api_type == "openai"
        assert found.is_validated is False

    def test_user_profile_repr(self, db_session):
        """Repr UserProfile."""
        user = UserProfile(chat_id=7777, name="Repr Тест", role="owner")
        assert "Repr Тест" in repr(user)

    def test_user_api_config_repr(self, db_session):
        """Repr UserAPIConfig."""
        api = UserAPIConfig(
            chat_id=7777, api_type="deepseek",
            api_name="DS", config_data="{}",
        )
        assert "deepseek" in repr(api)

    def test_cascade_relationship(self, db_session):
        """Relationship: UserProfile → api_configs."""
        user = UserProfile(chat_id=6666, name="Cascade Тест", role="user")
        db_session.add(user)
        db_session.flush()

        api1 = UserAPIConfig(
            chat_id=6666, api_type="openai",
            api_name="OpenAI", config_data="{}",
        )
        api2 = UserAPIConfig(
            chat_id=6666, api_type="deepseek",
            api_name="DeepSeek", config_data="{}",
        )
        db_session.add_all([api1, api2])
        db_session.flush()

        user = db_session.query(UserProfile).filter_by(chat_id=6666).first()
        assert len(user.api_configs) == 2

    def test_unique_constraint(self, db_session):
        """UniqueConstraint на (chat_id, api_type)."""
        user = UserProfile(chat_id=5555, name="Unique Тест", role="user")
        db_session.add(user)
        db_session.flush()

        api1 = UserAPIConfig(
            chat_id=5555, api_type="openai",
            api_name="OpenAI", config_data="{}",
        )
        db_session.add(api1)
        db_session.flush()

        api2 = UserAPIConfig(
            chat_id=5555, api_type="openai",
            api_name="OpenAI Dupe", config_data="{}",
        )
        db_session.add(api2)
        with pytest.raises(Exception):  # IntegrityError
            db_session.flush()


# ═══════════════════════════════════════════════════════════════════════════════
# 10. ConversationState новые состояния
# ═══════════════════════════════════════════════════════════════════════════════

class TestConversationState:
    """Тесты новых состояний диалога."""

    def test_awaiting_name_state_exists(self):
        """Состояние AWAITING_NAME существует."""
        assert ConversationState.AWAITING_NAME == "awaiting_name"

    def test_awaiting_api_setup_state_exists(self):
        """Состояние AWAITING_API_SETUP существует."""
        assert ConversationState.AWAITING_API_SETUP == "awaiting_api_setup"

    def test_free_state_unchanged(self):
        """FREE состояние не изменилось."""
        assert ConversationState.FREE == "free"

    def test_all_original_states_preserved(self):
        """Все оригинальные состояния сохранены."""
        assert hasattr(ConversationState, "ORDER_INPUT")
        assert hasattr(ConversationState, "ORDER_CONFIRM")
        assert hasattr(ConversationState, "AWAITING_INCOME")
        assert hasattr(ConversationState, "AWAITING_EXPENSE")
        assert hasattr(ConversationState, "AWAITING_TRACK")
        assert hasattr(ConversationState, "AWAITING_STATUS")
        assert hasattr(ConversationState, "AWAITING_DELIVERY")
        assert hasattr(ConversationState, "AWAITING_DELIVERY_TYPE")
        assert hasattr(ConversationState, "FILE_OPERATION")


# ═══════════════════════════════════════════════════════════════════════════════
# 11. SUPPORTED_APIS и API_KEY_PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

class TestSupportedAPIs:
    """Тесты структур данных API."""

    def test_supported_apis_has_deepseek(self):
        """DeepSeek в списке поддерживаемых."""
        assert "deepseek" in SUPPORTED_APIS
        assert SUPPORTED_APIS["deepseek"]["name"] == "DeepSeek API"

    def test_supported_apis_has_openai(self):
        """OpenAI в списке поддерживаемых."""
        assert "openai" in SUPPORTED_APIS

    def test_supported_apis_has_anthropic(self):
        """Anthropic в списке поддерживаемых."""
        assert "anthropic" in SUPPORTED_APIS

    def test_supported_apis_has_custom(self):
        """Custom API в списке поддерживаемых."""
        assert "custom_api" in SUPPORTED_APIS

    def test_all_apis_have_required_fields(self):
        """Все API имеют обязательные поля."""
        for api_type, info in SUPPORTED_APIS.items():
            assert "name" in info, f"{api_type} missing 'name'"
            assert "description" in info, f"{api_type} missing 'description'"
            assert "setup_guide" in info, f"{api_type} missing 'setup_guide'"

    def test_api_key_patterns_is_list(self):
        """API_KEY_PATTERNS — список кортежей."""
        assert isinstance(API_KEY_PATTERNS, list)
        assert len(API_KEY_PATTERNS) > 0

    def test_api_key_patterns_structure(self):
        """Каждый паттерн — кортеж (pattern, api_type, field_name)."""
        for item in API_KEY_PATTERNS:
            assert len(item) == 3
            pattern, api_type, field_name = item
            assert isinstance(pattern, str)
            assert isinstance(api_type, str)
            assert isinstance(field_name, str)

    def test_deepseek_pattern_matches(self):
        """Паттерн sk- матчит DeepSeek ключи."""
        import re
        key = "sk-9025b951982c474a9c4ab70d31ad98e8"
        matched = False
        for pattern, api_type, _ in API_KEY_PATTERNS:
            if re.search(pattern, key):
                matched = True
                break
        assert matched

    def test_telegram_pattern_matches(self):
        """Паттерн Telegram Bot token."""
        import re
        token = "8500002088:AAFbWonMQql6XnfbyTARSZ5bPNDAALCNuVA"
        matched = False
        for pattern, api_type, _ in API_KEY_PATTERNS:
            if re.search(pattern, token):
                matched = True
                assert api_type == "telegram_bot"
                break
        assert matched
