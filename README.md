# Ласковые новостюшки

Телеграм-бот, который берёт свежие новости, переписывает их нарочито «ласковым»
детским тоном через LLM, озвучивает голосом (ElevenLabs) и присылает подписчикам
аудио. Проект сатирический: смысл — в контрасте между реальными новостями и
приторной подачей, так что воспринимать его стоит как арт-эксперимент, а не как
источник новостей.

## Как это работает

```
RSS Meduza  ->  OpenAI (переписать «ласково»)  ->  ElevenLabs (TTS, PCM)
            ->  обернуть в WAV + замедлить речь  ->  рассылка в Telegram
```

- `parse()` — детерминированно собирает недельную сводку из RSS в `news_list.txt`.
- `getting_news()` — просит LLM выбрать три новости и переписать их по промпту из `gpt_prompt.py`.
- `text_to_speech_wav()` — озвучивает текст, сохраняет сырой PCM как WAV.
- `create_final_news()` — замедляет речь (`audiostretchy`) и отдаёт итоговый `news.wav`.

## Два режима запуска

Репозиторий рассчитан на два независимых входа:

1. **Интерактивный бот** — `cute_news.py`. Long-polling, отвечает на команды
   `/start`, `/subscribe`, `/unsubscribe`, `/remind`, а также `/broadcast_now`
   и `/restart` для админа. Нужен процесс, живущий 24/7 (VPS).
2. **Разовая рассылка** — `send_digest.py`. Генерирует свежий выпуск и рассылает
   всем подписчикам за один прогон. Подходит для запуска по расписанию
   (cron / GitHub Actions), сервер не нужен. См. `.github/workflows/digest.yml`.

## Локальный запуск

1. `python -m venv venv && source venv/bin/activate` (Windows: `venv\Scripts\activate`)
2. `pip install -r requirements.txt`
3. `cp .env.example .env` и вписать свои ключи.
4. `cp user_list.txt.example user_list.txt` и указать свои Telegram chat id.
5. Интерактивный бот: `python cute_news.py`. Разовая рассылка: `python send_digest.py`.

Проверить только парсер, без ключей: `python test_parse.py`.

## Переменные окружения

| Переменная | Обязательна | Назначение |
|---|---|---|
| `TELEGRAM_KEY` | да | токен бота от @BotFather |
| `OPENAI_KEY` | да | ключ для OpenAI-совместимого API |
| `ELEVEN_KEY` | да | ключ ElevenLabs |
| `admin_id` | нет | chat id админа (права на `/broadcast_now`, `/restart`) |
| `OPENAI_MODEL` | нет | модель, по умолчанию `gpt-4o-mini` |
| `OPENAI_BASE_URL` | нет | эндпоинт, по умолчанию прокси proxyapi.ru |
| `ELEVEN_VOICE_ID`, `RSS_URL` | нет | голос и источник новостей |

## Ограничения

- `send_digest.py` в CI берёт подписчиков из секрета `SUBSCRIBERS`, так как
  `user_list.txt` не хранится в репозитории.
- Замедление речи требует, чтобы вход был WAV; на вход из mp3 нужен `ffmpeg` —
  поэтому TTS запрашивается сразу в PCM и оборачивается в WAV штатным `wave`.
- Модель для LLM вынесена в переменную окружения: `gpt-3.5-turbo` выключают
  23.10.2026, а сторонний прокси может убрать её раньше.
