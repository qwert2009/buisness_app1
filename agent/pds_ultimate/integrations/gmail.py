"""
PDS-Ultimate Gmail Integration
==================================
Интеграция с Gmail API.

По ТЗ:
- Чтение входящих писем
- Отправка писем (отчёты каждые 3 дня)
- Ответ на письма в стиле владельца
- OAuth2 авторизация через credentials.json
"""

from __future__ import annotations

import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from pds_ultimate.config import config, logger


class GmailClient:
    """
    Клиент Gmail API.

    Жизненный цикл:
        client = GmailClient()
        await client.start()        # OAuth2 авторизация
        emails = await client.get_unread()
        await client.send_email(to, subject, body)
        await client.stop()
    """

    def __init__(self):
        self._service = None
        self._started = False

    async def start(self) -> None:
        """Авторизация в Gmail через OAuth2."""
        if self._started:
            return

        if not config.gmail.enabled:
            logger.warning("Gmail отключён (GMAIL_ENABLED=false)")
            return

        try:
            import asyncio
            # Google API — синхронная библиотека, запускаем в executor
            loop = asyncio.get_event_loop()
            self._service = await loop.run_in_executor(
                None, self._build_service
            )
            self._started = True
            logger.info("Gmail API подключён")

        except Exception as e:
            logger.error(f"Ошибка подключения Gmail: {e}", exc_info=True)

    def _build_service(self):
        """Построить Gmail service (синхронно)."""
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        token_path = config.gmail.token_file

        # Загружаем сохранённый токен
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(
                str(token_path), config.gmail.scopes,
            )

        # Если токена нет или он невалиден
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not config.gmail.credentials_file.exists():
                    raise FileNotFoundError(
                        f"Gmail credentials не найден: "
                        f"{config.gmail.credentials_file}\n"
                        f"Скачайте из Google Cloud Console."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(config.gmail.credentials_file),
                    config.gmail.scopes,
                )
                creds = flow.run_local_server(port=0)

            # Сохраняем токен
            token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(token_path, "w") as f:
                f.write(creds.to_json())

        return build("gmail", "v1", credentials=creds)

    async def stop(self) -> None:
        """Отключение."""
        self._service = None
        self._started = False
        logger.info("Gmail API отключён")

    # ═══════════════════════════════════════════════════════════════════════
    # Чтение почты
    # ═══════════════════════════════════════════════════════════════════════

    async def get_unread(self, max_results: int = 10) -> list[dict]:
        """
        Получить непрочитанные письма.

        Returns:
            [{"id", "from", "subject", "body", "date"}, ...]
        """
        if not self._started:
            return []

        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._fetch_unread, max_results,
        )

    def _fetch_unread(self, max_results: int) -> list[dict]:
        """Синхронная выборка непрочитанных."""
        try:
            result = self._service.users().messages().list(
                userId="me",
                q="is:unread",
                maxResults=max_results,
            ).execute()

            messages = result.get("messages", [])
            emails = []

            for msg_ref in messages:
                msg = self._service.users().messages().get(
                    userId="me",
                    id=msg_ref["id"],
                    format="full",
                ).execute()

                email_data = self._parse_email(msg)
                if email_data:
                    emails.append(email_data)

            logger.info(f"Gmail: получено {len(emails)} непрочитанных")
            return emails

        except Exception as e:
            logger.error(f"Ошибка чтения Gmail: {e}")
            return []

    def _parse_email(self, msg: dict) -> Optional[dict]:
        """Распарсить raw email в dict."""
        headers = {
            h["name"].lower(): h["value"]
            for h in msg.get("payload", {}).get("headers", [])
        }

        # Извлекаем тело
        body = self._extract_body(msg.get("payload", {}))

        return {
            "id": msg["id"],
            "thread_id": msg.get("threadId", ""),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "subject": headers.get("subject", "(без темы)"),
            "date": headers.get("date", ""),
            "body": body[:5000],  # Ограничиваем размер
            "snippet": msg.get("snippet", ""),
        }

    def _extract_body(self, payload: dict) -> str:
        """Извлечь текст из payload (рекурсивно для multipart)."""
        if payload.get("mimeType") == "text/plain":
            data = payload.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

        parts = payload.get("parts", [])
        for part in parts:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

            # Рекурсия для вложенных multipart
            if part.get("parts"):
                result = self._extract_body(part)
                if result:
                    return result

        return ""

    # ═══════════════════════════════════════════════════════════════════════
    # Отправка почты
    # ═══════════════════════════════════════════════════════════════════════

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        html: bool = False,
    ) -> dict:
        """
        Отправить письмо.

        Args:
            to: Адресат
            subject: Тема
            body: Текст письма
            html: HTML-формат или plain text

        Returns:
            {"id": "...", "status": "sent"} или {"error": "..."}
        """
        if not self._started:
            return {"error": "Gmail не подключён"}

        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._send, to, subject, body, html,
        )

    def _send(
        self,
        to: str,
        subject: str,
        body: str,
        html: bool = False,
    ) -> dict:
        """Синхронная отправка."""
        try:
            message = MIMEMultipart()
            message["to"] = to
            message["from"] = config.gmail.owner_email
            message["subject"] = subject

            mime_type = "html" if html else "plain"
            message.attach(MIMEText(body, mime_type, "utf-8"))

            raw = base64.urlsafe_b64encode(
                message.as_bytes()
            ).decode("utf-8")

            result = self._service.users().messages().send(
                userId="me",
                body={"raw": raw},
            ).execute()

            logger.info(f"Gmail: письмо отправлено → {to} ({subject})")
            return {"id": result.get("id", ""), "status": "sent"}

        except Exception as e:
            logger.error(f"Ошибка отправки Gmail: {e}")
            return {"error": str(e)}

    async def reply_to(
        self,
        thread_id: str,
        message_id: str,
        to: str,
        subject: str,
        body: str,
    ) -> dict:
        """Ответить на письмо (в том же треде)."""
        if not self._started:
            return {"error": "Gmail не подключён"}

        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._reply, thread_id, message_id, to, subject, body,
        )

    def _reply(
        self,
        thread_id: str,
        message_id: str,
        to: str,
        subject: str,
        body: str,
    ) -> dict:
        """Синхронный ответ на письмо."""
        try:
            message = MIMEMultipart()
            message["to"] = to
            message["from"] = config.gmail.owner_email
            message["subject"] = f"Re: {subject}" if not subject.startswith(
                "Re:") else subject
            message["In-Reply-To"] = message_id
            message["References"] = message_id

            message.attach(MIMEText(body, "plain", "utf-8"))

            raw = base64.urlsafe_b64encode(
                message.as_bytes()
            ).decode("utf-8")

            result = self._service.users().messages().send(
                userId="me",
                body={"raw": raw, "threadId": thread_id},
            ).execute()

            logger.info(f"Gmail: ответ отправлен → {to}")
            return {"id": result.get("id", ""), "status": "sent"}

        except Exception as e:
            logger.error(f"Ошибка ответа Gmail: {e}")
            return {"error": str(e)}

    async def mark_as_read(self, message_id: str) -> bool:
        """Пометить как прочитанное."""
        if not self._started:
            return False

        import asyncio
        loop = asyncio.get_event_loop()

        try:
            await loop.run_in_executor(
                None,
                lambda: self._service.users().messages().modify(
                    userId="me",
                    id=message_id,
                    body={"removeLabelIds": ["UNREAD"]},
                ).execute(),
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка mark_as_read: {e}")
            return False


# ─── Глобальный экземпляр ────────────────────────────────────────────────────

gmail_client = GmailClient()
