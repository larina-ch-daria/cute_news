import os
import sys
import re
import time
import wave
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

import gpt_prompt
import users as us

load_dotenv()

log = logging.getLogger(__name__)

# ------------------------- КОНФИГ -------------------------
OPENAI_KEY = os.getenv("OPENAI_KEY")
ELEVEN_KEY = os.getenv("ELEVEN_KEY")
TELEGRAM_KEY = os.getenv("TELEGRAM_KEY")
ADMIN_ID = os.getenv("admin_id")

# Имя модели вынесено в конфиг: gpt-3.5-turbo выключают 23.10.2026,
# а прокси мог убрать её и раньше. Меняется без правки кода.
# Через `or`, а не второй аргумент getenv: незаданная GitHub-переменная
# приходит как ПУСТАЯ строка, и getenv(..., default) её бы не подменил.
OPENAI_MODEL = os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or "https://api.proxyapi.ru/openai/v1"

RSS_URL = os.getenv("RSS_URL") or "https://meduza.io/rss/all"
# Дефолт — premade-голос Rachel: доступен на free-тарифе (library-голоса — нет).
VOICE_ID = os.getenv("ELEVEN_VOICE_ID") or "21m00Tcm4TlvDq8ikWAM"


def _env_float(name: str, default: float) -> float:
    """Читает float из окружения; пустое/кривое значение -> default."""
    v = os.getenv(name)
    if v in (None, ""):
        return default
    try:
        return float(v)
    except ValueError:
        log.warning("Переменная %s='%s' не число, беру %s", name, v, default)
        return default


# Настройки голоса — крутятся из GitHub Variables без правки кода.
# stability: ниже = живее/эмоциональнее интонации; style: выше = выразительнее.
ELEVEN_STABILITY = _env_float("ELEVEN_STABILITY", 0.3)
ELEVEN_SIMILARITY = _env_float("ELEVEN_SIMILARITY", 0.53)
ELEVEN_STYLE = _env_float("ELEVEN_STYLE", 0.15)
ELEVEN_SPEAKER_BOOST = (os.getenv("ELEVEN_SPEAKER_BOOST") or "false").lower() in ("1", "true", "yes", "on")

# Замедление речи: 1.2 = как было (речь на 20% длиннее/медленнее); 1.0 = выключено.
STRETCH_RATIO = _env_float("STRETCH_RATIO", 1.2)

NEWS_LIST_FILE = "news_list.txt"
GPT_NEWS_FILE = "gpt_news.txt"
RAW_WAV = "news_raw.wav"      # сырой PCM от ElevenLabs, обёрнутый в WAV
FINAL_WAV = "news.wav"        # замедленный результат, его и отправляем



def _require(name: str, value: str) -> str:
    """Падаем громко и понятно, если обязательной переменной нет."""
    if not value:
        raise RuntimeError(
            f"Не задана переменная окружения {name}. "
            f"Проверь .env локально или Variables в Railway."
        )
    return value


# ------------------------- ПАРСИНГ (RSS Meduza) -------------------------
def parse() -> bool:
    """Собирает недельную сводку в news_list.txt (до 3 новостей на день).

    Возвращает True при успехе. При недоступности RSS (например, «Медуза»
    заблокирована в РФ и запрос с локального IP не проходит) возвращает False
    и НЕ трогает news_list.txt — чтобы наверх не ушли протухшие старые новости.
    """
    try:
        r = requests.get(RSS_URL, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        log.error("parse(): не удалось получить RSS: %s", e)
        return False

    # r.content (байты), а не r.text — корректно с XML-декларацией кодировки
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError as e:
        log.error("parse(): не удалось разобрать XML: %s", e)
        return False

    by_date = defaultdict(list)
    today = datetime.now(timezone.utc).date()
    week_ago = today - timedelta(days=7)

    for item in root.findall(".//item"):
        title_el = item.find("title")
        desc_el = item.find("description")
        pub_el = item.find("pubDate")

        if title_el is None or pub_el is None:
            continue

        title = title_el.text or ""
        desc = desc_el.text or ""

        try:
            date = datetime.strptime(pub_el.text, "%a, %d %b %Y %H:%M:%S %z").date()
        except (TypeError, ValueError):
            continue

        if date < week_ago:
            continue

        if len(by_date[date]) < 3:
            short_desc = " ".join(desc.split(" ")[:30]).strip()
            by_date[date].append(f"{title} — {short_desc}")

    if not by_date:
        # RSS открылся, но свежих новостей за неделю нет — не перезаписываем старьё
        log.error("parse(): в ленте нет новостей за последнюю неделю.")
        return False

    lines = ["Сводка новостей за неделю:\n"]
    for day in sorted(by_date.keys(), reverse=True):
        lines.append(f"{day.strftime('%Y-%m-%d')}: {'; '.join(by_date[day])}.\n")

    with open(NEWS_LIST_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    log.info("Недельная сводка собрана (%d дней).", len(by_date))
    return True


# ------------------------- ChatGPT -------------------------
def _extract_broadcast(text: str) -> str:
    """Достаёт из ответа модели только реплику эфира, отбрасывая рассуждения.

    Не полагаемся на послушность модели: чистим детерминированно.
    1) вырезаем <think>…</think> (reasoning-модели рассуждают вслух);
    2) если эфир обёрнут в [ЭФИР]…[/ЭФИР] — берём то, что между метками;
    3) иначе отрезаем всё до предписанной первой фразы «Приветик…»;
    4) если зацепок нет — возвращаем как есть.
    """
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    m = re.search(r"\[ЭФИР\](.*?)\[/ЭФИР\]", text, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    idx = text.find("Приветик")
    if idx != -1:
        return text[idx:].strip()
    return text.strip()


def getting_news() -> str:
    """Парсит новости и переписывает их «ласково» через OpenAI-совместимый API."""
    if not parse():
        # RSS недоступен/пуст — не кормим LLM старым файлом, честно выходим
        log.error("getting_news(): свежих новостей нет, генерация отменена.")
        return ""

    from openai import OpenAI  # локальный импорт: не тянем SDK, если просто читаем модуль

    client = OpenAI(
        api_key=_require("OPENAI_KEY", OPENAI_KEY),
        base_url=OPENAI_BASE_URL,
    )
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": gpt_prompt.get_role()},
                {"role": "user", "content": gpt_prompt.get_prompt()},
            ],
        )
    except Exception as e:
        log.error("Ошибка OpenAI API: %s", e)
        return ""

    final_news = _extract_broadcast(response.choices[0].message.content or "")
    with open(GPT_NEWS_FILE, "w", encoding="utf-8") as f:
        f.write(final_news)
    return final_news


# ------------------------- ElevenLabs (TTS) -------------------------
def text_to_speech_wav(text: str) -> str | None:
    """
    Озвучивает текст и сохраняет как WAV (RAW_WAV).

    Просим у ElevenLabs сырой PCM (pcm_22050) и оборачиваем его в WAV штатным
    модулем `wave`. Так последующий stretch работает БЕЗ ffmpeg/pydub — раньше
    мы просили mp3, а audiostretchy не умеет читать mp3 без этих зависимостей,
    поэтому замедление молча отваливалось.
    """
    if not text:
        log.error("text_to_speech_wav(): пустой текст, пропускаю озвучку.")
        return None

    from elevenlabs.client import ElevenLabs
    from elevenlabs import VoiceSettings

    client = ElevenLabs(api_key=_require("ELEVEN_KEY", ELEVEN_KEY))
    # convert() у ElevenLabs ленивый: сам HTTP-запрос уходит при переборе ответа,
    # поэтому и вызов, и перебор держим в одном try — иначе ошибка API (402, лимит
    # символов и т.п.) вылетит сырым трейсбеком мимо обработчика.
    pcm = bytearray()
    try:
        response = client.text_to_speech.convert(
            voice_id=VOICE_ID,
            output_format="pcm_22050",   # сырой PCM 22050 Hz, 16-bit, mono
            text=text,
            model_id="eleven_multilingual_v2",
            voice_settings=VoiceSettings(
                stability=ELEVEN_STABILITY,
                similarity_boost=ELEVEN_SIMILARITY,
                style=ELEVEN_STYLE,
                use_speaker_boost=ELEVEN_SPEAKER_BOOST,
            ),
        )
        try:
            for chunk in response:
                if chunk:
                    pcm.extend(chunk)
        except TypeError:
            if response:
                pcm.extend(response)
    except Exception as e:
        log.error("Ошибка ElevenLabs API: %s", e)
        return None

    if not pcm:
        log.error("ElevenLabs вернул пустой звук.")
        return None

    with wave.open(RAW_WAV, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)          # 16-bit
        w.setframerate(22050)
        w.writeframes(pcm)

    log.info("Озвучка сохранена: %s (%d байт PCM)", RAW_WAV, len(pcm))
    return RAW_WAV


# ------------------------- Замедляем речь -------------------------
def create_final_news() -> str | None:
    """
    Полный цикл: текст -> озвучка (WAV) -> замедление до FINAL_WAV.
    Возвращает путь к файлу для отправки (замедленный WAV, иначе сырой WAV).
    """
    news_text = getting_news()
    raw_path = text_to_speech_wav(news_text)
    if not raw_path or not os.path.exists(raw_path):
        return None

    # STRETCH_RATIO <= 1.0 — замедление выключено, шлём исходный WAV
    if STRETCH_RATIO <= 1.0:
        return raw_path

    try:
        from audiostretchy.stretch import stretch_audio
        stretch_audio(raw_path, FINAL_WAV, ratio=STRETCH_RATIO)
        return FINAL_WAV
    except Exception as e:
        # замедление — не критично: если упало, отдаём неизменённый WAV
        log.warning("Не удалось замедлить речь (%s), отправлю исходный WAV.", e)
        return raw_path


# ------------------------- BOT -------------------------
from aiogram import Bot, Dispatcher, types, Router, BaseMiddleware
from aiogram.types import FSInputFile
from aiogram.filters.command import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler

dp = Dispatcher()
hello_router = Router(name="hello")


async def notify_admin(bot: Bot, text: str):
    if not ADMIN_ID:
        return
    try:
        await bot.send_message(int(ADMIN_ID), text)
    except Exception as e:
        log.error("Не удалось оповестить админа: %s", e)


def _is_admin(message: types.Message) -> bool:
    return bool(ADMIN_ID) and str(message.from_user.id) == str(ADMIN_ID)


@dp.message(Command("start"))
async def start_handler(message: types.Message, bot: Bot):
    us.check_name(message.chat.id, us.users)
    user_id = message.from_user.id
    log.info("start: %s %s %s", user_id, message.from_user.full_name, time.asctime())
    await message.reply(
        f"Привет, {message.from_user.full_name}!\n"
        f"Мы рады каждому слушателю!\nВот новости к этому часу:"
    )

    try:
        audio_path = await asyncio.to_thread(create_final_news)
    except Exception as e:
        log.error("Ошибка генерации аудио для %s: %s", user_id, e)
        await message.reply("К сожалению, аудиофайл с новостями недоступен.")
        await notify_admin(bot, f"Ошибка генерации аудио для {user_id}: {e}")
        return

    if not audio_path or not os.path.exists(audio_path):
        await message.reply("К сожалению, аудиофайл с новостями недоступен.")
        return

    try:
        await bot.send_audio(
            user_id,
            FSInputFile(audio_path),
            title=f"Daily news {datetime.now().strftime('%d.%m.%Y')}",
            performer="Ласковые новостюшки",
        )
    except Exception as e:
        log.error("Ошибка отправки аудио %s: %s", user_id, e)
        await notify_admin(bot, f"Ошибка отправки аудио {user_id}: {e}")


@dp.message(Command("subscribe"))
async def subscribe_handler(message: types.Message):
    us.check_name(message.chat.id, us.users)
    await message.reply("Вы подписаны на рассылку новостей.")


@dp.message(Command("unsubscribe"))
async def unsubscribe_handler(message: types.Message):
    us.remove_user(message.chat.id, us.users)
    await message.reply("Вы отписаны от рассылки.")


@hello_router.message(Command("remind"))
async def remind_handler(message: types.Message, bot: Bot, scheduler: AsyncIOScheduler):
    await message.answer("Бот будет присылать новости :)")
    # id + replace_existing, чтобы повторные /remind не плодили дубли задач
    scheduler.add_job(
        send_audios, "cron", day_of_week="mon", hour=20, minute=0,
        args=(bot,), id="weekly_digest", replace_existing=True,
    )


@dp.message(Command("broadcast_now"))
async def broadcast_now(message: types.Message, bot: Bot):
    if not _is_admin(message):
        await message.reply("У вас нет прав для выполнения этой команды.")
        return
    await message.reply("Запускаю форсированную рассылку новостей...")
    try:
        await send_audios(bot)
        await message.reply("Рассылка завершена.")
    except Exception as e:
        log.error("Ошибка broadcast_now: %s", e)
        await notify_admin(bot, f"Ошибка broadcast_now: {e}")
        await message.reply("Ошибка при рассылке. Админ оповещён.")


@dp.message(Command("restart"))
async def restart_handler(message: types.Message, bot: Bot):
    if not _is_admin(message):
        await message.reply("У вас нет прав для выполнения этой команды.")
        return
    await message.reply("Перезапускаю бота...")
    await notify_admin(bot, f"Перезапуск запрошен пользователем {message.from_user.id}")
    await asyncio.sleep(1)
    os.execv(sys.executable, [sys.executable] + sys.argv)


async def send_audios(bot: Bot):
    """Генерирует свежее аудио и рассылает всем подписчикам."""
    try:
        audio_path = await asyncio.to_thread(create_final_news)
    except Exception as e:
        log.error("Ошибка генерации аудио для рассылки: %s", e)
        return

    if not audio_path or not os.path.exists(audio_path):
        log.error("Аудио не создано, рассылка отменена.")
        return

    with open(us.users, "r", encoding="utf-8") as f:
        user_ids = [line.strip() for line in f if line.strip()]

    for uid in user_ids:
        try:
            user_id = int(uid)
        except ValueError:
            log.warning("Пропускаю некорректный id: %s", uid)
            continue
        try:
            # свежий FSInputFile на каждого — чтобы поток файла не «съедался»
            await bot.send_audio(
                user_id,
                FSInputFile(audio_path),
                title=f"Daily news {datetime.now().strftime('%d.%m.%Y')}",
                performer="Ласковые новостюшки",
            )
            log.info("Сообщение отправлено пользователю: %s", user_id)
        except Exception as e:
            log.error("Ошибка отправки %s: %s", user_id, e)
            await notify_admin(bot, f"Ошибка отправки аудио {user_id}: {e}")
        await asyncio.sleep(2)


class SchedulerMiddleware(BaseMiddleware):
    def __init__(self, scheduler: AsyncIOScheduler):
        super().__init__()
        self._scheduler = scheduler

    async def __call__(self, handler, event, data):
        data["scheduler"] = self._scheduler
        return await handler(event, data)


# ------------------------- MAIN -------------------------
async def main():
    # Bot создаём здесь, а не на уровне модуля: иначе импорт падал без токена
    bot = Bot(token=_require("TELEGRAM_KEY", TELEGRAM_KEY))

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.start()

    dp.update.middleware(SchedulerMiddleware(scheduler=scheduler))
    dp.include_router(hello_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s - [%(levelname)s] - %(name)s - "
               "(%(filename)s).%(funcName)s(%(lineno)d) - %(message)s",
    )
    asyncio.run(main())