# AVI -> MP4 Converter + Telegram Uploader

Скрипт `convert_avi_to_mp4.py` конвертирует видео из `.avi` в `.mp4`, умеет следить за директорией на появление новых `.avi` файлов и отправлять результат в Telegram.

## Возможности

- Конвертация одного `.avi` файла в `.mp4`
- Выбор стандартного выходного разрешения: `source`, `480p`, `720p`, `1080p`, `1440p`, `4k`
- Режим мониторинга директории (`--watch-dir`)
- Отправка готового `.mp4` в Telegram через Bot API
- Загрузка Telegram-параметров из `.env`
- Опциональная очистка файлов после успешной отправки в Telegram

## Необходимая подготовка

1. Установите Python 3.10+ (подойдет и более ранний 3.x, если поддерживает используемые типы).
2. Установите `ffmpeg` и убедитесь, что он доступен в `PATH`:

```bash
ffmpeg -version
```

Если команда не найдена, установите ffmpeg (например, через пакетный менеджер вашей ОС).

3. (Для Telegram) создайте бота через BotFather и получите:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Файлы проекта

- `convert_avi_to_mp4.py` - основной скрипт
- `.env` - файл с переменными окружения (необязательно, но рекомендуется для Telegram)

## Запуск

### 1) Конвертация одного файла

```bash
python convert_avi_to_mp4.py /path/to/video.avi
```

С выбором разрешения:

```bash
python convert_avi_to_mp4.py /path/to/video.avi --resolution 1080p
```

С указанием выходного файла:

```bash
python convert_avi_to_mp4.py /path/to/video.avi --output /path/to/result.mp4
```

### 2) Мониторинг директории

```bash
python convert_avi_to_mp4.py --watch-dir income --resolution 480p
```

По умолчанию обрабатываются только новые файлы, появившиеся после старта скрипта.

Чтобы обработать и уже существующие `.avi` при старте:

```bash
python convert_avi_to_mp4.py --watch-dir income --resolution 480p --process-existing
```

С явной папкой для результатов:

```bash
python convert_avi_to_mp4.py --watch-dir income --output-dir income/converted --resolution 720p
```

## Настройка Telegram через `.env`

Создайте файл `.env` рядом со скриптом:

```env
TELEGRAM_BOT_TOKEN=123456:ABCDEF_your_bot_token
TELEGRAM_CHAT_ID=123456789
```

После этого можно запускать без передачи токена и chat_id в CLI:

```bash
python convert_avi_to_mp4.py --watch-dir income --resolution 480p --process-existing
```

Можно использовать другой файл переменных:

```bash
python convert_avi_to_mp4.py --watch-dir income --env-file /path/to/custom.env
```

## Удаление файлов после отправки в Telegram

Если нужно удалять исходный `.avi` и готовый `.mp4` после успешной отправки в Telegram, используйте:

```bash
python convert_avi_to_mp4.py --watch-dir income --resolution 480p --process-existing --cleanup-after-telegram
```

Важно:
- удаление происходит только после успешной отправки в Telegram
- если отправка не удалась, файлы остаются локально

## Полный перечень аргументов

- `input`
  - Позиционный аргумент: путь к входному `.avi` файлу
  - Используется в режиме обработки одного файла

- `-o, --output`
  - Путь к выходному `.mp4`
  - По умолчанию: рядом с input, с тем же именем и расширением `.mp4`

- `--watch-dir`
  - Папка, которую скрипт периодически проверяет на новые `.avi`

- `--output-dir`
  - Куда сохранять `.mp4` в режиме мониторинга
  - По умолчанию: `<watch-dir>/converted`

- `-r, --resolution`
  - Выходное разрешение: `source`, `480p`, `720p`, `1080p`, `1440p`, `4k`
  - `source` - оставить исходное разрешение

- `--poll-interval`
  - Интервал опроса папки в секундах
  - По умолчанию: `3.0`

- `--telegram-token`
  - Токен Telegram-бота
  - Если не указан, берется из `TELEGRAM_BOT_TOKEN` в `.env`/окружении

- `--telegram-chat-id`
  - Chat ID получателя
  - Если не указан, берется из `TELEGRAM_CHAT_ID` в `.env`/окружении

- `--process-existing`
  - В режиме `--watch-dir`: обработать также файлы, которые уже лежат в папке на момент старта

- `--cleanup-after-telegram`
  - После успешной отправки в Telegram удалить исходный `.avi` и созданный `.mp4`

- `--env-file`
  - Путь к `.env`
  - По умолчанию: `./.env`

## Логика работы режима мониторинга

1. Скрипт стартует и запоминает текущее состояние папки.
2. Каждые `--poll-interval` секунд проверяет наличие новых `.avi`.
3. Для нового файла ждет, пока размер/mtime стабилизируются (файл дозаписался).
4. Конвертирует в `.mp4` с выбранным разрешением.
5. Если есть Telegram-токен и chat_id, отправляет видео в Telegram.
6. Если включен `--cleanup-after-telegram`, удаляет оба файла после успешной отправки.

## Ограничения и важные замечания

- Скрипт обрабатывает только файлы с расширением `.avi`.
- В режиме `--watch-dir` нельзя одновременно передавать `input`.
- Для `--watch-dir` отправка в Telegram обязательна (нужны token + chat_id через `.env` или CLI).
- Если `ffmpeg` не установлен, скрипт завершится с ошибкой.

## Примеры готовых команд

Одиночный файл + отправка в Telegram через `.env`:

```bash
python convert_avi_to_mp4.py /path/to/video.avi --resolution 720p
```

Мониторинг папки + обработка старых файлов + автоудаление после Telegram:

```bash
python convert_avi_to_mp4.py \
  --watch-dir income \
  --output-dir income/converted \
  --resolution 480p \
  --process-existing \
  --cleanup-after-telegram
```

## Диагностика проблем

- `ffmpeg не найден`
  - Установите ffmpeg и проверьте `ffmpeg -version`.

- Скрипт "молчит" в `--watch-dir`
  - Это нормально, если нет новых `.avi`.
  - Добавьте `--process-existing`, если нужно обработать уже лежащие файлы.

- Видео не отправляется в Telegram
  - Проверьте корректность `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID`.
  - Убедитесь, что бот может писать в указанный чат.

- Файлы не удаляются с `--cleanup-after-telegram`
  - Удаление выполняется только после успешной отправки в Telegram.
