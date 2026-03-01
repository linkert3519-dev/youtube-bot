import os
import re
import yt_dlp
import subprocess
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from openai import OpenAI

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_KEY")

client = OpenAI(api_key=OPENAI_KEY)


def extract_url(text):
    match = re.search(r'(https?://\S+)', text)
    return match.group(1) if match else None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = extract_url(update.message.text)

    if not url:
        await update.message.reply_text("Пришли ссылку на YouTube.")
        return

    await update.message.reply_text("Скачиваю аудио...")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'audio.%(ext)s',
        'quiet': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    original_file = [f for f in os.listdir() if f.startswith("audio.")][0]

    await update.message.reply_text("Сжимаю аудио...")

    compressed_file = "audio_compressed.mp3"

    subprocess.run([
        "ffmpeg",
        "-i", original_file,
        "-b:a", "64k",
        compressed_file
    ])

    await update.message.reply_text("Делаю транскрипцию...")

    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=open(compressed_file, "rb")
    )

    text = transcript.text

    await update.message.reply_text("Создаю тезисы...")

    summary = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Сделай краткие структурированные тезисы по видео."},
            {"role": "user", "content": text[:12000]}
        ]
    )

    await update.message.reply_text("📄 Транскрипция:\n" + text[:3000])
    await update.message.reply_text("🧠 Тезисы:\n" + summary.choices[0].message.content)

    os.remove(original_file)
    os.remove(compressed_file)


if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
