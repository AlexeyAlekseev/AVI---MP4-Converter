#!/usr/bin/env python3
import argparse
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

STANDARD_RESOLUTIONS = {
    "source": None,
    "480p": "854:480",
    "720p": "1280:720",
    "1080p": "1920:1080",
    "1440p": "2560:1440",
    "4k": "3840:2160",
}


def load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def ensure_ffmpeg_available() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg не найден. Установите ffmpeg и добавьте его в PATH.")


def convert_avi_to_mp4(input_file: Path, output_file: Path, resolution: str) -> None:
    ensure_ffmpeg_available()

    if not input_file.exists():
        raise FileNotFoundError(f"Файл не найден: {input_file}")

    if input_file.suffix.lower() != ".avi":
        raise ValueError("Входной файл должен быть в формате .avi")

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_file),
    ]

    scale_value = STANDARD_RESOLUTIONS[resolution]
    if scale_value is not None:
        cmd.extend(
            [
                "-vf",
                (
                    f"scale={scale_value}:force_original_aspect_ratio=decrease,"
                    f"pad={scale_value}:(ow-iw)/2:(oh-ih)/2"
                ),
            ]
        )

    cmd.extend(
        [
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(output_file),
        ]
    )

    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise RuntimeError("Ошибка конвертации через ffmpeg")


def build_multipart_form(fields: dict[str, str], file_field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = f"----videoconverter-{int(time.time() * 1000)}"
    chunks: list[bytes] = []
    line_break = b"\r\n"

    for name, value in fields.items():
        chunks.append(f"--{boundary}".encode())
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"'.encode()
        )
        chunks.append(b"")
        chunks.append(str(value).encode("utf-8"))

    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    file_bytes = file_path.read_bytes()
    chunks.append(f"--{boundary}".encode())
    chunks.append(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"'.encode()
    )
    chunks.append(f"Content-Type: {mime_type}".encode())
    chunks.append(b"")
    chunks.append(file_bytes)
    chunks.append(f"--{boundary}--".encode())
    chunks.append(b"")

    body = line_break.join(chunks)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def send_video_to_telegram(token: str, chat_id: str, video_path: Path, caption: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendVideo"
    body, content_type = build_multipart_form(
        fields={"chat_id": chat_id, "caption": caption},
        file_field="video",
        file_path=video_path,
    )

    request = urllib.request.Request(
        url=url,
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            response_text = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        error_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram API HTTP {e.code}: {error_text}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ошибка сети при отправке в Telegram: {e}") from e

    parsed = json.loads(response_text)
    if not parsed.get("ok"):
        raise RuntimeError(f"Telegram API вернул ошибку: {response_text}")


def wait_for_file_stable(path: Path, checks: int = 3, delay_seconds: float = 1.0) -> None:
    previous: Optional[tuple[int, float]] = None
    stable_count = 0
    while stable_count < checks:
        stat = path.stat()
        current = (stat.st_size, stat.st_mtime)
        if current == previous:
            stable_count += 1
        else:
            stable_count = 0
            previous = current
        time.sleep(delay_seconds)


def process_single_file(
    input_file: Path,
    output_file: Path,
    resolution: str,
    telegram_token: Optional[str],
    telegram_chat_id: Optional[str],
    cleanup_after_telegram: bool,
) -> None:
    convert_avi_to_mp4(input_file, output_file, resolution)
    if telegram_token and telegram_chat_id:
        caption = f"Конвертация завершена: {output_file.name}"
        send_video_to_telegram(telegram_token, telegram_chat_id, output_file, caption)
        if cleanup_after_telegram:
            input_file.unlink(missing_ok=True)
            output_file.unlink(missing_ok=True)


def watch_directory(
    watch_dir: Path,
    output_dir: Path,
    resolution: str,
    poll_interval: float,
    telegram_token: str,
    telegram_chat_id: str,
    process_existing: bool,
    cleanup_after_telegram: bool,
) -> None:
    if not watch_dir.is_dir():
        raise NotADirectoryError(f"Директория не найдена: {watch_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    known_files = set() if process_existing else {p.resolve() for p in watch_dir.glob("*.avi")}
    print(
        f"Мониторинг директории: {watch_dir} "
        f"(известных файлов: {len(known_files)}, интервал: {poll_interval} сек, "
        f"обрабатывать существующие: {'да' if process_existing else 'нет'})"
    )

    while True:
        current_files = {p.resolve() for p in watch_dir.glob("*.avi")}
        new_files = sorted(current_files - known_files, key=str)
        for input_file in new_files:
            print(f"Новый файл: {input_file.name}")
            try:
                wait_for_file_stable(input_file)
                output_file = output_dir / f"{input_file.stem}.mp4"
                process_single_file(
                    input_file=input_file,
                    output_file=output_file,
                    resolution=resolution,
                    telegram_token=telegram_token,
                    telegram_chat_id=telegram_chat_id,
                    cleanup_after_telegram=cleanup_after_telegram,
                )
                if cleanup_after_telegram:
                    print(f"Готово, отправлено в Telegram и удалено: {input_file.name}, {output_file.name}")
                else:
                    print(f"Готово и отправлено в Telegram: {output_file}")
            except Exception as e:
                print(f"Ошибка обработки {input_file}: {e}", file=sys.stderr)

        known_files = current_files
        time.sleep(poll_interval)


def main() -> int:
    parser = argparse.ArgumentParser(description="Конвертация AVI в MP4 и мониторинг директории")
    parser.add_argument("input", nargs="?", type=Path, help="Путь к входному .avi файлу")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Путь к выходному .mp4 файлу (по умолчанию рядом с входным)",
    )
    parser.add_argument(
        "--watch-dir",
        type=Path,
        help="Директория для мониторинга новых .avi файлов",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Папка для результатов в режиме мониторинга (по умолчанию watch_dir/converted)",
    )
    parser.add_argument(
        "-r",
        "--resolution",
        choices=list(STANDARD_RESOLUTIONS.keys()),
        default="source",
        help="Выходное разрешение: source, 480p, 720p, 1080p, 1440p, 4k",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=3.0,
        help="Интервал проверки директории в секундах (режим --watch-dir)",
    )
    parser.add_argument(
        "--telegram-token",
        type=str,
        help="Токен Telegram-бота (или TELEGRAM_BOT_TOKEN в .env)",
    )
    parser.add_argument(
        "--telegram-chat-id",
        type=str,
        help="Chat ID для отправки результата (или TELEGRAM_CHAT_ID в .env)",
    )
    parser.add_argument(
        "--process-existing",
        action="store_true",
        help="В режиме --watch-dir обработать уже существующие .avi при старте",
    )
    parser.add_argument(
        "--cleanup-after-telegram",
        action="store_true",
        help="После успешной отправки в Telegram удалить исходный .avi и созданный .mp4",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Путь к .env файлу (по умолчанию ./.env)",
    )
    args = parser.parse_args()
    load_dotenv(args.env_file)

    telegram_token = args.telegram_token or os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = args.telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID")

    if args.watch_dir and args.input:
        print("Ошибка: используйте либо input-файл, либо --watch-dir", file=sys.stderr)
        return 1

    if not args.watch_dir and not args.input:
        print("Ошибка: укажите input-файл или --watch-dir", file=sys.stderr)
        return 1

    try:
        if args.watch_dir:
            if not telegram_token or not telegram_chat_id:
                print(
                    "Ошибка: для режима --watch-dir укажите токен/chat_id через .env "
                    "(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID) или через CLI",
                    file=sys.stderr,
                )
                return 1

            watch_dir = args.watch_dir
            output_dir = args.output_dir or (watch_dir / "converted")
            watch_directory(
                watch_dir=watch_dir,
                output_dir=output_dir,
                resolution=args.resolution,
                poll_interval=args.poll_interval,
                telegram_token=telegram_token,
                telegram_chat_id=telegram_chat_id,
                process_existing=args.process_existing,
                cleanup_after_telegram=args.cleanup_after_telegram,
            )
            return 0

        input_file = args.input
        output_file = args.output or input_file.with_suffix(".mp4")
        process_single_file(
            input_file=input_file,
            output_file=output_file,
            resolution=args.resolution,
            telegram_token=telegram_token,
            telegram_chat_id=telegram_chat_id,
            cleanup_after_telegram=args.cleanup_after_telegram,
        )
    except Exception as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1

    if args.cleanup_after_telegram and telegram_token and telegram_chat_id:
        print("Готово: файл отправлен в Telegram и удален локально")
        return 0

    print(f"Готово: {output_file}")
    if telegram_token and telegram_chat_id:
        print("Файл отправлен в Telegram")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
