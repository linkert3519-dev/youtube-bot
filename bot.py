import os
import re
import yt_dlp
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from openai import OpenAI

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_KEY")

client = OpenAI(api_key=OPENAI_KEY)

MAX_FILE_SIZE = 24 * 1024 * 1024  # 24MB безопасный лимит


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
        'format': 'bestaudio',
        'outtmpl': 'audio.%(ext)s',
        'quiet': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '64',
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    file_name = "audio.mp3"

    if not os.path.exists(file_name):
        file_name = [f for f in os.listdir() if f.endswith(".mp3")][0]

    file_size = os.path.getsize(file_name)

    if file_size > MAX_FILE_SIZE:
        await update.message.reply_text(
            "Видео слишком длинное для обработки (лимит 25MB). "
            "Попробуй более короткое видео."
        )
        os.remove(file_name)
        return

    await update.message.reply_text("Делаю транскрипцию...")

    with open(file_name, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="gpt-4o-transcribe",
            file=audio_file
        )

    full_text = transcript.text
    os.remove(file_name)

    await update.message.reply_text("Анализирую видео...")

    result = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Ты эксперт по бизнес-анализу."},
            {"role": "user", "content": f"""
Проанализируй текст видео и дай:

1. Главную идею
2. 10 ключевых тезисов
3. Бизнес-инсайты
4. Качества предпринимателя
5. Конкретные шаги к успеху
6. Как начинался бизнес (если есть)
            
Текст:
{full_text[:120000]}
"""}
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
