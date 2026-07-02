#!/usr/bin/env python3
"""
Одноразовая диагностика: какие голоса доступны твоему ключу ElevenLabs.

Запусти вручную (workflow "list-voices"), найди в выводе строку с
category = premade и пропиши её voice_id в Variable ELEVEN_VOICE_ID.
Именно premade-голоса доступны на free-тарифе через API; library — нет.
"""
import os
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

load_dotenv()

key = os.getenv("ELEVEN_KEY")
if not key:
    raise SystemExit("Нет ELEVEN_KEY")

client = ElevenLabs(api_key=key)
resp = client.voices.get_all(show_legacy=True)

print(f"Всего голосов, видимых ключу: {len(resp.voices)}\n")
print(f"{'category':13} {'voice_id':24} name")
print("-" * 60)
for v in resp.voices:
    print(f"{(v.category or '?'):13} {v.voice_id:24} {v.name}")

premade = [v for v in resp.voices if (v.category or "") == "premade"]
print("\n--- premade-голоса (годятся для free-тарифа) ---")
if premade:
    for v in premade:
        print(f"{v.voice_id}  {v.name}")
else:
    print("Ни одного premade не нашлось — возможно, аккаунт на новом наборе "
          "голосов. Возьми любой voice_id из списка выше с category, "
          "отличной от 'library'.")
