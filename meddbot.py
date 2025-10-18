import asyncio
from datetime import datetime, timedelta
import sqlite3
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

TOKEN = "8209055726:AAHQY6hwvBlAsk758tOuCvYlkOlCgL9yNRk"

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

DB = "reminders.db"

# ---------- База данных ----------
def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        medicine TEXT,
        count TEXT,
        time_of_day TEXT,
        start_date TEXT,
        days INTEGER,
        active INTEGER DEFAULT 1
    )
    """)
    conn.commit()
    conn.close()

def add_reminder(user_id, medicine, count, time_of_day, days):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reminders (user_id, medicine, count, time_of_day, start_date, days) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, medicine, count, time_of_day, datetime.now().date().isoformat(), days)
    )
    conn.commit()
    conn.close()

def get_user_reminders(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, medicine, count, time_of_day FROM reminders WHERE user_id=? AND active=1", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def stop_reminder(reminder_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("UPDATE reminders SET active=0 WHERE id=?", (reminder_id,))
    conn.commit()
    conn.close()

def stop_all_reminders(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("UPDATE reminders SET active=0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

# ---------- FSM ----------
class CreateState(StatesGroup):
    waiting_med_name = State()
    waiting_count = State()
    waiting_time = State()
    waiting_days = State()

# ---------- Планировщик ----------
async def scheduler():
    while True:
        now = datetime.now().strftime("%H:%M")
        today = datetime.now().date()
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("SELECT id, user_id, medicine, count, time_of_day, start_date, days FROM reminders WHERE active=1")
        rows = cur.fetchall()
        conn.close()
        for rid, user_id, medicine, count, t, start, days in rows:
            start_date = datetime.fromisoformat(start).date()
            if start_date <= today < start_date + timedelta(days=days):
                if now == t:
                    await bot.send_message(user_id, f"💊 Напоминание: принять {medicine} ({count}) в {t}")
        await asyncio.sleep(60)

# ---------- Кнопки интерфейса ----------
def main_menu(user_id):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Добавить новый препарат"))
    kb.add(KeyboardButton("Удалить напоминание"))
    kb.add(KeyboardButton("Удалить все напоминания"))

    reminders = get_user_reminders(user_id)
    if reminders:
        for rid, med, count, time in reminders:
            kb.add(KeyboardButton(f"{rid} - {med} ({count}) в {time}"))
    return kb

# ---------- Хэндлеры ----------
@dp.message_handler(commands=["start"])
async def start(msg: types.Message):
    await msg.answer("Привет! Я бот для напоминаний о лекарствах.", reply_markup=main_menu(msg.from_user.id))

@dp.message_handler(lambda message: message.text == "Добавить новый препарат")
async def add_new(msg: types.Message):
    await CreateState.waiting_med_name.set()
    await msg.answer("Введите название лекарства:", reply_markup=ReplyKeyboardRemove())

@dp.message_handler(state=CreateState.waiting_med_name)
async def med_name(msg: types.Message, state: FSMContext):
    await state.update_data(medicine=msg.text)
    await CreateState.waiting_count.set()
    await msg.answer("Сколько таблеток нужно принять? (в цифрах)")

@dp.message_handler(state=CreateState.waiting_count)
async def med_count(msg: types.Message, state: FSMContext):
    try:
        int(msg.text)
    except ValueError:
        await msg.answer("❌ Введите число таблеток цифрами, например 2")
        return
    await state.update_data(count=msg.text)
    await CreateState.waiting_time.set()
    await msg.answer("Во сколько напомнить (например, 08:30)?")

@dp.message_handler(state=CreateState.waiting_time)
async def med_time(msg: types.Message, state: FSMContext):
    if len(msg.text) != 5 or msg.text[2] != ':' or not msg.text.replace(':','').isdigit():
        await msg.answer("❌ Введите время в формате HH:MM, например 08:30")
        return
    await state.update_data(time_of_day=msg.text)
    await CreateState.waiting_days.set()
    await msg.answer("На сколько дней повторять напоминание? (в цифрах)")

@dp.message_handler(state=CreateState.waiting_days)
async def med_days(msg: types.Message, state: FSMContext):
    try:
        days = int(msg.text)
    except ValueError:
        await msg.answer("❌ Введите количество дней цифрами, например 7")
        return
    data = await state.get_data()
    add_reminder(msg.from_user.id, data["medicine"], data["count"], data["time_of_day"], days)
    await state.finish()
    await msg.answer("✅ Напоминание создано!", reply_markup=main_menu(msg.from_user.id))

# ---------- Удаление одного напоминания ----------
@dp.message_handler(lambda message: any(message.text.startswith(str(r[0])) for r in get_user_reminders(message.from_user.id)))
async def handle_delete(msg: types.Message):
    reminder_id = int(msg.text.split(" - ")[0])
    stop_reminder(reminder_id)
    await msg.answer("✅ Напоминание удалено!", reply_markup=main_menu(msg.from_user.id))

# ---------- Удаление всех напоминаний ----------
@dp.message_handler(lambda message: message.text == "Удалить все напоминания")
async def delete_all(msg: types.Message):
    stop_all_reminders(msg.from_user.id)
    await msg.answer("✅ Все напоминания удалены!", reply_markup=main_menu(msg.from_user.id))

# ---------- Удаление через кнопку "Удалить напоминание" ----------
@dp.message_handler(lambda message: message.text == "Удалить напоминание")
async def delete_prompt(msg: types.Message):
    reminders = get_user_reminders(msg.from_user.id)
    if not reminders:
        await msg.answer("У вас пока нет активных напоминаний.", reply_markup=main_menu(msg.from_user.id))
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for rid, med, count, time in reminders:
        kb.add(KeyboardButton(f"{rid} - {med} ({count}) в {time}"))
    kb.add(KeyboardButton("Отмена"))
    await msg.answer("Выберите напоминание для удаления:", reply_markup=kb)

@dp.message_handler(lambda message: message.text == "Отмена")
async def cancel_delete(msg: types.Message):
    await msg.answer("Отмена действия.", reply_markup=main_menu(msg.from_user.id))

# ---------- Запуск ----------
if __name__ == "__main__":
    init_db()
    loop = asyncio.get_event_loop()
    loop.create_task(scheduler())
    executor.start_polling(dp, skip_updates=True)
