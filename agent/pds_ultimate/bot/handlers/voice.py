"""
PDS-Ultimate Voice Handler
==============================
Обработка голосовых сообщений:
1. Скачивание .ogg файла
2. Конвертация в WAV (через ffmpeg)
3. Распознавание Faster-Whisper (локально)
4. Передача текста в Universal Handler
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.orm import Session

from pds_ultimate.bot.conversation import conversation_manager
from pds_ultimate.bot.handlers.universal import _save_to_db, handle_text
from pds_ultimate.config import logger

router = Router(name="voice")


@router.message(F.voice)
async def handle_voice(message: Message, db_session: Session) -> None:
    """
    Голосовое сообщение → текст → обработка как текст.
    """
    chat_id = message.chat.id
    ctx = conversation_manager.get(chat_id)

    await message.bot.send_chat_action(chat_id, "typing")

    tmp_dir = tempfile.mkdtemp(prefix="pds_voice_")
    ogg_path = Path(tmp_dir) / "voice.ogg"
    wav_path = Path(tmp_dir) / "voice.wav"

    try:
        # ─── 1. Скачиваем файл голосового ────────────────────────────
        file = await message.bot.get_file(message.voice.file_id)
        await message.bot.download_file(file.file_path, destination=str(ogg_path))

        logger.info(
            f"Голосовое: {file.file_path}, "
            f"размер: {ogg_path.stat().st_size} байт, "
            f"длительность: {message.voice.duration}с"
        )

        # ─── 2. Конвертация OGG → WAV (ffmpeg) ──────────────────────
        import subprocess

        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(ogg_path), "-ar",
             "16000", "-ac", "1", str(wav_path)],
            capture_output=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.error(f"ffmpeg ошибка: {result.stderr.decode()}")
            await message.answer("❌ Не удалось обработать голосовое. Попробуй ещё раз.")
            return

        # ─── 3. Распознавание Faster-Whisper ─────────────────────────
        from pds_ultimate.utils.parsers import parser

        text = await parser.parse_voice(str(wav_path))

        if not text or text.strip() == "":
            await message.answer("🔇 Не удалось распознать речь. Попробуй ещё раз, говори чётче.")
            return

        logger.info(
            f"Whisper распознал ({message.voice.duration}с): «{text[:100]}...»")

        # Уведомляем пользователя о том что распознано
        preview = text[:200]
        if len(text) > 200:
            preview += "..."

        await message.answer(f"🎤 Распознал: «{preview}»")

        # Сохраняем в историю
        _save_to_db(
            db_session, chat_id, "user",
            f"[голосовое {message.voice.duration}с]: {text}",
        )

        # ─── 4. Обрабатываем как текстовое сообщение ─────────────────
        # Подменяем текст и вызываем обработчик
        message.text = text
        await handle_text(message, db_session)

    except FileNotFoundError:
        logger.error("ffmpeg не найден. Установите: apt install ffmpeg")
        await message.answer(
            "❌ Сервер не настроен для голосовых (нужен ffmpeg). "
            "Напиши текстом, я пойму."
        )

    except Exception as e:
        logger.error(f"Ошибка обработки голосового: {e}", exc_info=True)
        await message.answer("❌ Ошибка при обработке голосового. Попробуй текстом.")

    finally:
        # ─── Очистка временных файлов ────────────────────────────────
        for p in [ogg_path, wav_path]:
            try:
                if p.exists():
                    os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass


@router.message(F.video_note)
async def handle_video_note(message: Message, db_session: Session) -> None:
    """
    Видео-кружок → извлечение аудио → распознавание.
    """
    chat_id = message.chat.id

    await message.bot.send_chat_action(chat_id, "typing")

    tmp_dir = tempfile.mkdtemp(prefix="pds_videonote_")
    video_path = Path(tmp_dir) / "video.mp4"
    wav_path = Path(tmp_dir) / "audio.wav"

    try:
        file = await message.bot.get_file(message.video_note.file_id)
        await message.bot.download_file(file.file_path, destination=str(video_path))

        import subprocess

        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path), "-vn",
             "-ar", "16000", "-ac", "1", str(wav_path)],
            capture_output=True,
            timeout=60,
        )

        if result.returncode != 0:
            await message.answer("❌ Не удалось обработать видео-кружок.")
            return

        from pds_ultimate.utils.parsers import parser

        text = await parser.parse_voice(str(wav_path))

        if not text or text.strip() == "":
            await message.answer("🔇 Не удалось распознать речь из видео-кружка.")
            return

        await message.answer(f"🎤 Распознал из кружка: «{text[:200]}»")

        _save_to_db(
            db_session, chat_id, "user",
            f"[видео-кружок {message.video_note.length}]: {text}",
        )

        message.text = text
        await handle_text(message, db_session)

    except Exception as e:
        logger.error(f"Ошибка обработки видео-кружка: {e}", exc_info=True)
        await message.answer("❌ Ошибка при обработке видео-кружка. Напиши текстом.")

    finally:
        for p in [video_path, wav_path]:
            try:
                if p.exists():
                    os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass
