import os
import re
import yt_dlp
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from openai import OpenAI

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_KEY")

client = OpenAI(api_key=OPENAI_KEY)

CHUNK_SIZE = 10000


def extract_url(text):
    match = re.search(r'(https?://\S+)', text)
    return match.group(1) if match else None


def chunk_text(text, size):
    return [text[i:i + size] for i in range(0, len(text), size)]


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

    await update.message.reply_text("Делаю полную транскрипцию...")

    with open(file_name, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file
        )

    full_text = transcript.text
    os.remove(file_name)

    await update.message.reply_text("Обрабатываю текст...")

    chunks = chunk_text(full_text, CHUNK_SIZE)
    partial_summaries = []

    # --- 1 этап: краткое содержание частей ---
    for idx, chunk in enumerate(chunks):
        await update.message.reply_text(f"Обрабатываю часть {idx+1}/{len(chunks)}")

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Сделай краткое содержание этого фрагмента видео."},
                {"role": "user", "content": chunk}
            ],
            temperature=0.3
        )

        partial_summaries.append(response.choices[0].message.content)

    combined_summary = "\n\n".join(partial_summaries)

    # --- 2 этап: финальные тезисы ---
    final_summary = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """
На основе полного содержания видео:
1. Главная тема
2. 8-12 ключевых тезисов
3. Практические выводы
"""
            },
            {"role": "user", "content": combined_summary}
        ],
        temperature=0.4
    )

    # --- 3 этап: аналитика ---
    analysis = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """
Сделай глубокий анализ:
- Логика автора
- Сильные стороны аргументации
- Слабые стороны
- Кому полезно
- Общий вывод
"""
            },
            {"role": "user", "content": combined_summary}
        ],
        temperature=0.4
    )

    # --- 4 этап: ключевые бизнес-цитаты ---
    quotes = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """
Извлеки из текста ключевые цитаты и инсайты, связанные с:
- Началом бизнеса
- Развитием компании
- Качествами предпринимателя
- Личностным ростом бизнесмена
- Стратегиями достижения успеха

Выдели именно сильные формулировки и ценные мысли.
"""
            },
            {"role": "user", "content": combined_summary}
        ],
        temperature=0.5
    )

    # --- 5 этап: как человек стартовал в бизнесе ---
    startup_story = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """
Определи, рассказывается ли в видео о том,
как конкретный человек начал бизнес.

Если да:
- Как он стартовал
- С какими трудностями столкнулся
- Какие первые шаги сделал
- Что стало поворотной точкой

Если нет — так и напиши.
"""
            },
            {"role": "user", "content": combined_summary}
        ],
        temperature=0.4
    )

    # --- Отправка ---
    await update.message.reply_text("📌 ТЕЗИСЫ:\n\n" + final_summary.choices[0].message.content)
    await update.message.reply_text("🧠 АНАЛИЗ:\n\n" + analysis.choices[0].message.content)
    await update.message.reply_text("💬 КЛЮЧЕВЫЕ БИЗНЕС-ИНСАЙТЫ:\n\n" + quotes.choices[0].message.content)
    await update.message.reply_text("🚀 КАК НАЧИНАЛ БИЗНЕС:\n\n" + startup_story.choices[0].message.content)

    # Полная транскрипция файлом
    with open("transcript.txt", "w", encoding="utf-8") as f:
        f.write(full_text)

    with open("transcript.txt", "rb") as f:
        await update.message.reply_document(f)

    os.remove("transcript.txt")


if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
