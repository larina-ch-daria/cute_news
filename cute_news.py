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

# ########## ПАРСИНГ ###########
def parse():
    try:
        html = requests.get('https://qxwaohfvkipwdudt.g2jweym2z70h.live/').text
    except requests.RequestException as e:
        print(f"Error fetching news: {e}")
        return

    soup = LxmlSoup(html)

    links = soup.find_all('a', class_='Link-module-root Link-module-isInBlockTitle')

    all_news = []
    for i, link in enumerate(links):
        news = link.text()  
        all_news.append(f"{news}")
    with open("news_list.txt", "a") as file:
        for line in all_news:
            file.write(line + "\n")
    print("The news are collected!")


########## ЧАТ-GPT ###########
def getting_news():
    parse()
    client = OpenAI(
        api_key= f"{OPENAI_KEY}",
        base_url="https://api.proxyapi.ru/openai/v1",
    )
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": f"{gpt_prompt.role}"},
                {"role": "user", "content": f"{gpt_prompt.prompt}"}
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
        for chunk in response:
            if chunk:
                f.write(chunk)
    print(f"{save_file_path}: A new audio file was saved successfully!")

    # Return the path of the saved audio file
    return save_file_path

# ########### ДЕЛАЕМ АУДИО СЛУШАБЕЛЬНЫМ ##############

def create_final_news():
    text_to_speech_file()
    stretch_audio("news.mp3", "news.wav", ratio=1.2)

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

audio = FSInputFile('news.wav')
logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_KEY)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    us.check_name(message.chat.id, us.users)
    user_full_name = message.from_user.full_name
    # parse()
    logging.info(f'{user_id} {user_full_name} {time.asctime()}')
    await message.reply(f"Привет, {user_full_name}!\nМы рады каждому слушателю!\nВот новости к этому часу:")
    await bot.send_audio(user_id, audio, title = f'''Daily news {datetime.now().strftime('%d.%m.%Y')}''', performer = 'Ласковые новостюшки')

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


async def send_audios(bot: Bot):
    with open(us.users, "r") as file:
        # create_final_news()
        for user in file.readlines():
            user_id = int(user)
            try:
                await bot.send_audio(user_id, audio, title=f'''Daily news {datetime.now().strftime('%d.%m.%Y')}''', performer='Ласковые новостюшки')
            except Exception as e:
                print(f"Error sending audio to user {user_id}: {e}")
            print(f'''Сообщение отправлено пользователю: {user_id}''')
            asyncio.sleep(2)
    
    # Clear the file after sending all messages
    with open(us.users, "w") as file:
        file.write("")


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