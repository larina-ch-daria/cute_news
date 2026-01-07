from LxmlSoup import LxmlSoup
import requests
import gpt_prompt
from openai import OpenAI
from elevenlabs.client import ElevenLabs
from elevenlabs import VoiceSettings
from audiostretchy.stretch import stretch_audio

import time
import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_KEY = os.getenv('OPENAI_KEY')
ELEVEN_KEY = os.getenv('ELEVEN_KEY')
TELEGRAM_KEY = os.getenv('TELEGRAM_KEY')
admin_id = os.getenv('admin_id')

def _warn_missing_env():
    missing = []
    if not OPENAI_KEY:
        missing.append('OPENAI_KEY')
    if not ELEVEN_KEY:
        missing.append('ELEVEN_KEY')
    if not TELEGRAM_KEY:
        missing.append('TELEGRAM_KEY')
    if missing:
        print(f"Warning: missing environment variables: {', '.join(missing)}")

_warn_missing_env()

# ########## ПАРСИНГ ###########
# def parse():
#     try:
#         html = requests.get('https://tvrain.tv/news/').text
#     except requests.RequestException as e:
#         print(f"Error fetching news: {e}")
#         return

#     soup = LxmlSoup(html)

#     links = soup.find_all('a', class_='Link-module-root Link-module-isInBlockTitle')

#     all_news = []
#     for i, link in enumerate(links):
#         # safe text extraction for different element types
#         try:
#             news = link.text
#         except Exception:
#             try:
#                 news = link.get_text()
#             except Exception:
#                 news = str(link)
#         news = (news or '').strip()
#         if news:
#             all_news.append(news)
#     # overwrite the list to avoid uncontrolled duplicates
#     with open("news_list.txt", "w", encoding='utf-8') as file:
#         for line in all_news:
#             file.write(line + "\n")
#     print("The news are collected!")

import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from collections import defaultdict

def parse():
    url = "https://meduza.io/rss/all"

    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"parse() failed to fetch data: \"Error fetching news: {e}\"")
        return

    root = ET.fromstring(r.text)

    by_date = defaultdict(list)

    today = datetime.utcnow().date()
    week_ago = today - timedelta(days=7)

    # парсим RSS
    for item in root.findall(".//item"):
        title_el = item.find("title")
        desc_el = item.find("description")
        pub_el = item.find("pubDate")

        if title_el is None or pub_el is None:
            continue

        title = title_el.text or ""
        desc = desc_el.text or ""
        pub = pub_el.text

        # парсим дату
        try:
            date = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z").date()
        except Exception:
            continue

        if date < week_ago:
            continue

        if len(by_date[date]) < 3:
            # сокращаем описание
            short_desc = desc.split(" ")[0:30]
            short_desc = " ".join(short_desc).strip()
            text = f"{title} — {short_desc}"
            by_date[date].append(text)

    sorted_days = sorted(by_date.keys(), reverse=True)

    lines = []
    lines.append("Сводка новостей за неделю:\n")

    for day in sorted_days:
        items = "; ".join(by_date[day])
        lines.append(f"{day.strftime('%Y-%m-%d')}: {items}.\n")

    final_text = "\n".join(lines)

    with open("news_list.txt", "w", encoding="utf-8") as file:
        file.write(final_text)

    print("The weekly digest is collected!")



########## ЧАТ-GPT ###########
def getting_news():
    parse()
    client = OpenAI(
        api_key=f"{OPENAI_KEY}",
        base_url="https://api.proxyapi.ru/openai/v1",
    )
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": f"{gpt_prompt.get_role()}"},
                {"role": "user", "content": f"{gpt_prompt.get_prompt()}"}
            ]
        )
    except Exception as e:
        print(f"Error with OpenAI API: {e}")
        return "Error generating news"

    with open("gpt_news.txt", "w") as file:
        file.write(response.choices[0].message.content)
    final_news = response.choices[0].message.content
    return final_news
#final_news = 'Привет всем слушателям программы Ласковые новостюшки!'

# # ############## ELEVENLABS ######################

def text_to_speech_file():
    client = ElevenLabs(
    api_key=f"{ELEVEN_KEY}",
    )
    # Calling the text_to_speech conversion API with detailed parameters
    try:
        response = client.text_to_speech.convert(
            voice_id="blxHPCXhpXOsc7mCKk0P",
            optimize_streaming_latency="0",
            output_format="mp3_22050_32",
            text=getting_news(),
            model_id="eleven_multilingual_v2", 
            voice_settings=VoiceSettings(
                stability=0.3,
                similarity_boost=0.53,
                style=0.15,
                use_speaker_boost=False
            ),
        )
    except Exception as e:
        print(f"Error with ElevenLabs API: {e}")
        return None

    save_file_path = f"news.mp3"
    # Writing the audio to a file
    with open(save_file_path, "wb") as f:
        # response may be iterable stream or single bytes object
        try:
            for chunk in response:
                if chunk:
                    f.write(chunk)
        except TypeError:
            # not iterable, try write directly
            if response:
                f.write(response)
    print(f"{save_file_path}: A new audio file was saved successfully!")

    # Return the path of the saved audio file
    return save_file_path

# ########### ДЕЛАЕМ АУДИО СЛУШАБЕЛЬНЫМ ##############

def create_final_news():
    """Generate TTS (news.mp3) and attempt to stretch/convert to news.wav.
    Returns the path to the best-available audio file (wav preferred, else mp3).
    """
    mp3_path = None
    wav_path = None
    try:
        mp3_path = text_to_speech_file()
    except Exception as e:
        print(f"Error generating mp3: {e}")
        return None

    if not mp3_path or not os.path.exists(mp3_path):
        return None

    # Try to create WAV (stretch). If that fails, fall back to MP3.
    try:
        stretch_audio(mp3_path, "news.wav", ratio=1.2)
        wav_path = "news.wav"
        return wav_path
    except Exception as e:
        print(f"Warning: failed to stretch/convert to WAV ({e}), will use MP3 instead")
        return mp3_path

################# BOT ##########################

import time
import logging
import asyncio
from aiogram.types import FSInputFile, Message
from aiogram import Bot, Dispatcher, types, Router
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.filters.command import Command
import users as us
from aiogram import BaseMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
import sys

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_KEY)
dp = Dispatcher()


async def notify_admin(bot: Bot, text: str):
    if not admin_id:
        return
    try:
        await bot.send_message(int(admin_id), text)
    except Exception as e:
        print(f"Failed to notify admin: {e}")

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    us.check_name(message.chat.id, us.users)
    user_full_name = message.from_user.full_name
    # parse()
    logging.info(f'{user_id} {user_full_name} {time.asctime()}')
    await message.reply(f"Привет, {user_full_name}!\nМы рады каждому слушателю!\nВот новости к этому часу:")
    # Ensure audio exists; generate if needed. create_final_news returns preferred file path.
    try:
        audio_path = await asyncio.to_thread(create_final_news)
    except Exception as e:
        audio_path = None
        print(f"Error creating audio for user {user_id}: {e}")
        await message.reply("К сожалению, аудиофайл с новостями недоступен.")
        await notify_admin(bot, f"Error creating audio for user {user_id}: {e}")
        return

    if not audio_path or not os.path.exists(audio_path):
        await message.reply("К сожалению, аудиофайл с новостями недоступен.")
        return

    audio = FSInputFile(audio_path)
    try:
        await bot.send_audio(user_id, audio, title=f'''Daily news {datetime.now().strftime('%d.%m.%Y')}''', performer='Ласковые новостюшки')
    except Exception as e:
        err = f"Error sending audio to {user_id}: {e}"
        print(err)
        await notify_admin(bot, err)


@dp.message(Command("subscribe"))
async def subscribe_handler(message: types.Message):
    us.check_name(message.chat.id, us.users)
    await message.reply("Вы подписаны на рассылку новостей.")


@dp.message(Command("unsubscribe"))
async def unsubscribe_handler(message: types.Message):
    us.remove_user(message.chat.id, us.users)
    await message.reply("Вы отписаны от рассылки.")

#### ТАЙМЕР
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import sys

hello_router = Router(name='hello')

class SchedulerMiddleware(BaseMiddleware):
    def __init__(self, scheduler: AsyncIOScheduler):
        super().__init__()
        self._scheduler = scheduler

    async def __call__(self, handler, event, data):
        # прокидываем в словарь состояния scheduler
        data["scheduler"] = self._scheduler
        return await handler(event, data)
    
@hello_router.message(Command("remind"))
async def hello(message: types.Message, bot: Bot, scheduler: AsyncIOScheduler):
    await message.answer(
        text="Бот будет присылать новости :)"
    )
    scheduler.add_job(send_audios, 'cron', day_of_week='1', hour=20, minute=00, args = (bot,))


@dp.message(Command("broadcast_now"))
async def broadcast_now(message: types.Message):
    # Admin-only
    if not admin_id or str(message.from_user.id) != str(admin_id):
        await message.reply("У вас нет прав для выполнения этой команды.")
        return
    await message.reply("Запускаю форсированную рассылку новостей...")
    try:
        await send_audios(bot)
        await message.reply("Рассылка завершена.")
    except Exception as e:
        err = f"Error during broadcast_now: {e}"
        print(err)
        await notify_admin(bot, err)
        await message.reply("Ошибка при рассылке. Админ оповещён.")


@dp.message(Command("restart"))
async def restart_handler(message: types.Message):
    # Admin-only restart
    if not admin_id or str(message.from_user.id) != str(admin_id):
        await message.reply("У вас нет прав для выполнения этой команды.")
        return
    await message.reply("Перезапускаю бота...")
    await notify_admin(bot, f"Bot restart requested by {message.from_user.id}")
    await asyncio.sleep(1)
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        await message.reply(f"Не удалось перезапустить: {e}")


async def send_audios(bot: Bot):
    # generate fresh audio before sending; use returned path (wav preferred, else mp3)
    try:
        audio_path = create_final_news()
    except Exception as e:
        print(f"Error creating final news audio: {e}")
        audio_path = None

    if not audio_path or not os.path.exists(audio_path):
        print("Audio file not found, aborting send_audios")
        return
    audio = FSInputFile(audio_path)
    with open(us.users, "r", encoding='utf-8') as file:
        for line in file:
            uid = line.strip()
            if not uid:
                continue
            try:
                user_id = int(uid)
            except ValueError:
                print(f"Skipping invalid user id: {uid}")
                continue
            try:
                # open a fresh FSInputFile per user so the stream isn't consumed
                audio_file = FSInputFile(audio_path)
                await bot.send_audio(user_id, audio_file, title=f'''Daily news {datetime.now().strftime('%d.%m.%Y')}''', performer='Ласковые новостюшки')
            except Exception as e:
                print(f"Error sending audio to user {user_id}: {e}")
                await notify_admin(bot, f"Error sending audio to user {user_id}: {e}")
            else:
                print(f'''Сообщение отправлено пользователю: {user_id}''')
            await asyncio.sleep(2)
    # Do not clear the users file automatically; subscriptions persist


# ########## MAIN FUNCTION ###########
async def main():
    scheduler = AsyncIOScheduler(timezone='Europe/Moscow')
    scheduler.start()

    # Schedule the `parse` function to run daily at a specific time (e.g., 9:00 AM)
    scheduler.add_job(parse, 'cron', hour=9, minute=0)

    # Register middleware and routers
    dp.update.middleware(
        SchedulerMiddleware(scheduler=scheduler),
    )
    dp.include_routers(hello_router)

    # Start polling for Telegram bot updates
    await dp.start_polling(bot)

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s - [%(levelname)s] -  %(name)s - "
               "(%(filename)s).%(funcName)s(%(lineno)d) - %(message)s"
    )    
    asyncio.run(main())