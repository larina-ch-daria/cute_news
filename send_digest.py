#!/usr/bin/env python3
"""
Разовая рассылка недельного дайджеста (для cron / GitHub Actions).

Генерирует свежее аудио и рассылает всем подписчикам через Telegram Bot API.
Список подписчиков берётся из user_list.txt, а если файла нет (например, в CI) —
из переменной окружения SUBSCRIBERS (id через запятую или перевод строки).
"""
import os
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

from cute_news import create_final_news
import users as us

load_dotenv()

TELEGRAM_KEY = os.getenv("TELEGRAM_KEY")


def load_subscribers() -> list[str]:
    if os.path.exists(us.users):
        with open(us.users, encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip()]
    raw = os.getenv("SUBSCRIBERS", "")
    return [x.strip() for x in raw.replace(",", "\n").splitlines() if x.strip()]


def main():
    if not TELEGRAM_KEY:
        print("Не задана переменная окружения TELEGRAM_KEY")
        sys.exit(1)

    subscribers = load_subscribers()
    if not subscribers:
        print("Список подписчиков пуст (нет ни user_list.txt, ни SUBSCRIBERS)")
        sys.exit(1)

    # create_final_news внутри сам парсит новости и озвучивает — отдельный parse() не нужен
    audio_path = create_final_news()
    if not audio_path or not os.path.exists(audio_path):
        print("Аудио не создано, рассылка отменена (RSS/LLM/ElevenLabs недоступны?)")
        sys.exit(1)

    url = f"https://api.telegram.org/bot{TELEGRAM_KEY}/sendAudio"
    title = f"Daily news {datetime.now().strftime('%d.%m.%Y')}"

    for uid in subscribers:
        try:
            chat_id = int(uid)
        except ValueError:
            print(f"Пропускаю некорректный id: {uid}")
            continue
        try:
            with open(audio_path, "rb") as audio_file:
                resp = requests.post(
                    url,
                    data={"chat_id": chat_id, "title": title,
                          "performer": "Ласковые новостюшки"},
                    files={"audio": audio_file},
                    timeout=120,
                )
            if resp.ok:
                print(f"Отправлено: {chat_id}")
            else:
                print(f"Не удалось {chat_id}: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"Ошибка отправки {chat_id}: {e}")
        time.sleep(1)


if __name__ == "__main__":
    main()
