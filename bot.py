import os
import re
import subprocess
import yt_dlp
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from openai import OpenAI

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_KEY")

client = OpenAI(api_key=OPENAI_KEY)

MAX_CHUNK_SECONDS = 900  # 15 минут на кусок


def extract_url(text):
    match = re.search(r'(https?://\S+)', text)
    return match.group(1) if match else None


def split_audio_by_time(input_file):
    output_pattern = "chunk_%03d.mp3"

    subprocess.run([
        "ffmpeg",
        "-i", input_file,
        "-f", "segment",
        "-segment_time", str(MAX_CHUNK_SECONDS),
        "-c", "copy",
        output_pattern
    ])

    return sorted([f for f in os.listdir() if f.startswith("chunk_")])


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = extract_url(update.message.text)

    if not url:
        await update.message.reply_text("Пришли ссылку на YouTube.")
        return

    await update.message.reply_text("Скачиваю аудио...")

    ydl_opts = {
        'format': 'bestaudio',
        'outtmpl': 'audio.%(ext)s',
        'quiet': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    file_name = [f for f in os.listdir() if f.startswith("audio.")][0]

    await update.message.reply_text("Разбиваю аудио на части...")

    chunks = split_audio_by_time(file_name)

    full_text = ""

    for idx, chunk in enumerate(chunks):
        await update.message.reply_text(f"Транскрибирую часть {idx+1}/{len(chunks)}")

        with open(chunk, "rb") as audio_part:
            transcript = client.audio.transcriptions.create(
                model="gpt-4o-transcribe",
                file=audio_part
            )

        full_text += transcript.text + "\n"
        os.remove(chunk)

    os.remove(file_name)

    await update.message.reply_text("Делаю глубокий анализ...")

    analysis_prompt = f"""
На основе полного текста видео:

1. Главная идея
2. 10 ключевых тезисов
3. Практические выводы
4. Ключевые бизнес-инсайты
5. Как начинался бизнес (если описано)
6. Качества предпринимателя
7. Конкретные шаги к успеху
"""

    result = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Ты аналитик по бизнес-контенту."},
            {"role": "user", "content": analysis_prompt + "\n\n" + full_text[:120000]}
        ],
        temperature=0.4
    )

    await update.message.reply_text(result.choices[0].message.content[:4000])

    with open("transcript.txt", "w", encoding="utf-8") as f:
        f.write(full_text)

    with open("transcript.txt", "rb") as f:
        await update.message.reply_document(f)

    os.remove("transcript.txt")


if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
