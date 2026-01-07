#!/usr/bin/env python3
from dotenv import load_dotenv
import os
import requests
import time
from datetime import datetime

load_dotenv()

from cute_news import parse, create_final_news
import users as us

OPENAI_KEY = os.getenv('OPENAI_KEY')
ELEVEN_KEY = os.getenv('ELEVEN_KEY')
TELEGRAM_KEY = os.getenv('TELEGRAM_KEY')
ADMIN_ID = os.getenv('admin_id')


def main():
    if not TELEGRAM_KEY:
        print('Missing TELEGRAM_KEY environment variable')
        return

    # generate news and audio
    parse()
    audio_path = create_final_news()
    if not audio_path or not os.path.exists(audio_path):
        print('No audio generated, aborting')
        return

    # read subscribers
    users_file = us.users
    if not os.path.exists(users_file):
        print(f'Users file not found: {users_file}')
        return

    with open(users_file, 'r', encoding='utf-8') as f:
        for line in f:
            uid = line.strip()
            if not uid:
                continue
            try:
                chat_id = int(uid)
            except Exception:
                print(f'Skipping invalid user id: {uid}')
                continue

            url = f'https://api.telegram.org/bot{TELEGRAM_KEY}/sendAudio'
            data = {
                'chat_id': chat_id,
                'title': f'Daily news {datetime.now().strftime("%d.%m.%Y")}',
                'performer': 'Ласковые новостюшки'
            }
            try:
                with open(audio_path, 'rb') as audio_file:
                    files = {'audio': audio_file}
                    resp = requests.post(url, data=data, files=files, timeout=120)
                if resp.ok:
                    print(f'Sent audio to {chat_id}')
                else:
                    print(f'Failed to send to {chat_id}: {resp.status_code} {resp.text}')
            except Exception as e:
                print(f'Error sending to {chat_id}: {e}')

            time.sleep(1)


if __name__ == '__main__':
    main()
