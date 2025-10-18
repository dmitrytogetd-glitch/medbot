import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import os
from datetime import datetime, timedelta
import pytz  # Для работы с часовыми поясами

# Получаем токен из переменной окружения
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN не найден. Установите переменную окружения TOKEN.")

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# Подключение к базе данных SQLite
conn = sqlite3.connect("reminders.db")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    medicine TEXT,
    count INTEGER,
    time TEXT,
    days INTEGER,
    created_at TEXT
)
""")
conn.commit()

# Главное меню с кнопками
def main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Добавить препарат"))
    kb.add(KeyboardButton("Удалить напоминание"))
    return kb

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("Привет! Я помогу тебе с напоминаниями о лекарствах.", reply_markup=main_keyboard())

# Словарь для хранения временных данных пользователя
user_data = {}

# Шаги добавления лекарства
@dp.message_handler(lambda message: message.text == "Добавить препарат")
async def add_medicine(message: types.Message):
    user_data[message.chat.id] = {"step": "medicine"}
    await message.answer("Введите название препарата:")

@dp.message_handler(lambda message: message.chat.id in user_data)
async def process_steps(message: types.Message):
    data = user_data[message.chat.id]
    step = data.get("step")

    if step == "medicine":
        data["medicine"] = message.text
        data["step"] = "count"
        await message.answer("Сколько таблеток принимать за раз?")
    elif step == "count":
        if not message.text.isdigit():
            await message.answer("Введите число!")
            return
        data["count"] = int(message.text)
        data["step"] = "time"
        await message.answer("Во сколько напоминать? (по московскому времени, например 08:00)")
    elif step == "time":
        try:
            datetime.strptime(message.text, "%H:%M")
        except ValueError:
            await message.answer("Неверный формат времени! Используйте ЧЧ:ММ (по московскому времени)")
            return
        data["time"] = message.text
        data["step"] = "days"
        await message.answer("На сколько дней установить напоминание?")
    elif step == "days":
        if not message.text.isdigit():
            await message.answer("Введите число дней!")
            return
        data["days"] = int(message.text)
        # Сохраняем в базу
        cursor.execute("INSERT INTO reminders (chat_id, medicine, count, time, days, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                       (message.chat.id, data["medicine"], data["count"], data["time"], data["days"], datetime.now().isoformat()))
        conn.commit()
        await message.answer(f"Напоминание для {data['medicine']} добавлено!", reply_markup=main_keyboard())
        del user_data[message.chat.id]

# Шаг удаления напоминаний
@dp.message_handler(lambda message: message.text == "Удалить напоминание")
async def delete_reminder(message: types.Message):
    cursor.execute("SELECT id, medicine FROM reminders WHERE chat_id = ?", (message.chat.id,))
    rows = cursor.fetchall()
    if not rows:
        await message.answer("У вас нет напоминаний.", reply_markup=main_keyboard())
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for row in rows:
        kb.add(KeyboardButton(f"Удалить {row[1]}"))
    kb.add(KeyboardButton("Отмена"))
    await message.answer("Выберите напоминание для удаления:", reply_markup=kb)

@dp.message_handler(lambda message: message.text.startswith("Удалить "))
async def process_delete(message: types.Message):
    med_name = message.text.replace("Удалить ", "")
    cursor.execute("DELETE FROM reminders WHERE chat_id = ? AND medicine = ?", (message.chat.id, med_name))
    conn.commit()
    await message.answer(f"Напоминание {med_name} удалено!", reply_markup=main_keyboard())

# Московский часовой пояс
moscow_tz = pytz.timezone("Europe/Moscow")

async def scheduler():
    while True:
        now_moscow = datetime.now(moscow_tz).strftime("%H:%M")
        cursor.execute("SELECT chat_id, medicine, count FROM reminders WHERE time = ?", (now_moscow,))
        rows = cursor.fetchall()
        for row in rows:
            chat_id, med, count = row
            await bot.send_message(chat_id, f"Напоминание: принять {count} таблеток {med}")
        await asyncio.sleep(60)  # проверяем каждую минуту

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(scheduler())
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
