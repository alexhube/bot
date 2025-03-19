import sqlite3
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import schedule
import time
import threading

# Настройка логирования для консоли
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен вашего Telegram-бота
TOKEN = "8081159733:AAGge9ZDEfJhfx-mD2FOhOzNh4gc0MnGzYk"

# Список переговорных
ROOMS = {
    "Videosecurity": ["Silver", "Gold", "Антикамера"],
    "Victiana": ["Fres", "Trening room", "Conferens", "Mars", "White"]
}

# Время работы переговорных
START_TIME = 8.5  # 08:30
END_TIME = 19.0   # 19:00

def log_request(user_id: int, action: str) -> None:
    """
    Записывает информацию о действии пользователя в файл user_requests.log.
    Добавляет user_id, текст действия и текущее дата-время.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("user_requests.log", "a", encoding="utf-8") as f:
        f.write(f"[{now_str}] User ID: {user_id}, Action: {action}\n")

def init_db():
    """
    Инициализация базы данных и создание таблицы, если её нет.
    """
    try:
        conn = sqlite3.connect("booking.db")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                room TEXT,
                date TEXT,
                time REAL,
                duration REAL
            )
        """)
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
    finally:
        conn.close()

def clear_bookings():
    """
    Функция для обнуления всех бронирований в базе данных.
    """
    try:
        conn = sqlite3.connect("booking.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bookings WHERE date = date('now')")
        conn.commit()
        logger.info("Все бронирования обнулены.")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при обнулении бронирований: {e}")
    finally:
        conn.close()

def schedule_clear_bookings():
    """
    Запланировать обнуление бронирований в 00:00 каждый день.
    """
    schedule.every().day.at("00:00").do(clear_bookings)

def run_schedule():
    """
    Функция для запуска планировщика в отдельном потоке.
    """
    while True:
        schedule.run_pending()
        time.sleep(1)

def format_time_slot(t: float) -> str:
    """
    Форматирует время (в часах, точность — 30 минут).
    Пример: 8.5 -> '08:30', 9.0 -> '09:00', 9.5 -> '09:30'.
    """
    hour = int(t)
    minute = int(round((t - hour) * 60))
    return f"{hour:02d}:{minute:02d}"

def format_duration(d: float) -> str:
    """
    Форматирует длительность (в часах):
    1.0 -> '1 ч'
    1.5 -> '1 ч 30 мин'
    0.5 -> '30 мин'
    2.0 -> '2 ч'
    """
    hours = int(d)
    minutes = int(round((d - hours) * 60))

    if hours > 0 and minutes > 0:
        return f"{hours} ч {minutes} мин"
    elif hours > 0:
        return f"{hours} ч"
    else:
        return f"{minutes} мин"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда /start: показывает 
    1) Свободные переговорные 
    2) Отменить бронь.
    """
    keyboard = [
        [InlineKeyboardButton("Свободные переговорные", callback_data="available_rooms")],
        [InlineKeyboardButton("Отменить бронь", callback_data="cancel_booking")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        log_request(update.message.from_user.id, "Вызвана команда /start")
        await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
    elif update.callback_query:
        log_request(update.callback_query.from_user.id, "Вернулся в главное меню (/start)")
        await update.callback_query.edit_message_text("Выберите действие:", reply_markup=reply_markup)

async def available_rooms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик кнопки "Свободные переговорные" -> выбор "здания" (Videosecurity или Victiana).
    """
    query = update.callback_query
    await query.answer()

    log_request(query.from_user.id, "Перешёл к выбору здания")

    keyboard = [
        [InlineKeyboardButton("Videosecurity", callback_data="building_1")],
        [InlineKeyboardButton("Victiana", callback_data="building_2")],
        [InlineKeyboardButton("⬅ Назад", callback_data="back_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Выберите здание:", reply_markup=reply_markup)

async def choose_building(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Пользователь выбрал одно из "зданий" (Videosecurity или Victiana) -> список переговорных.
    """
    query = update.callback_query
    await query.answer()

    building_number = query.data.split("_")[1]  # будет "1" или "2"
    if building_number == "1":
        building_key = "Videosecurity"
    else:
        building_key = "Victiana"

    log_request(query.from_user.id, f"Выбрал здание: {building_key}")

    rooms = ROOMS[building_key]

    keyboard = [[InlineKeyboardButton(room, callback_data=f"room_{room}")] for room in rooms]
    keyboard.append([InlineKeyboardButton("⬅ Назад", callback_data="available_rooms")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text("Выберите переговорную:", reply_markup=reply_markup)

async def choose_room(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик выбора переговорной -> список полчасовых слотов для текущей даты.
    """
    query = update.callback_query
    await query.answer()

    room = query.data.split("_")[1]
    context.user_data["room"] = room

    log_request(query.from_user.id, f"Выбрал переговорную: {room}")

    try:
        conn = sqlite3.connect("booking.db")
        cursor = conn.cursor()
        cursor.execute("SELECT time, duration FROM bookings WHERE room = ? AND date = date('now')", (room,))
        bookings = cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении данных: {e}")
        await query.edit_message_text("Произошла ошибка. Попробуйте позже.")
        return
    finally:
        conn.close()

    booked_slots = set()
    for (start_time, duration) in bookings:
        end_time = start_time + duration
        t = start_time
        while t < end_time:
            booked_slots.add(t)
            t += 0.5

    keyboard = []
    t = START_TIME
    while t < END_TIME:
        if t in booked_slots:
            keyboard.append([InlineKeyboardButton(f"❌ {format_time_slot(t)}", callback_data="dummy")])
        else:
            keyboard.append([InlineKeyboardButton(f"{format_time_slot(t)}", callback_data=f"time_{t}")])
        t += 0.5

    keyboard.append([InlineKeyboardButton("⬅ Назад", callback_data="available_rooms")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Выберите время начала:", reply_markup=reply_markup)

async def choose_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Выбор времени начала -> проверка пересечений и формирование длительностей.
    """
    query = update.callback_query
    await query.answer()

    chosen_start = float(query.data.split("_")[1])
    context.user_data["time"] = chosen_start
    room = context.user_data["room"]

    log_request(query.from_user.id, f"Выбрал время начала {format_time_slot(chosen_start)} для {room}")

    try:
        conn = sqlite3.connect("booking.db")
        cursor = conn.cursor()
        cursor.execute("SELECT time, duration FROM bookings WHERE room = ? AND date = date('now')", (room,))
        bookings = cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при чтении бронирований: {e}")
        await query.edit_message_text("Произошла ошибка. Попробуйте позже.")
        return
    finally:
        conn.close()

    intervals = []
    for (start_time, dur) in bookings:
        intervals.append((start_time, start_time + dur))
    intervals.sort(key=lambda x: x[0])

    # Проверяем, занято ли выбранное время
    for (start_i, end_i) in intervals:
        if start_i <= chosen_start < end_i:
            log_request(query.from_user.id, "Выбрал занятое время!")
            keyboard = [[InlineKeyboardButton("⬅ Назад", callback_data="back_to_time_selection")]]
            await query.edit_message_text(
                "Это время уже занято. Пожалуйста, выберите другое время.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

    # Находим ближайшее следующее бронирование
    next_start = END_TIME
    for (start_i, _) in intervals:
        if start_i >= chosen_start:
            next_start = start_i
            break

    max_available = next_start - chosen_start
    if chosen_start >= END_TIME:
        max_available = 0
    else:
        max_available = min(max_available, END_TIME - chosen_start)

    durations = []
    d = 0.5
    while d <= 8 and d <= max_available:
        durations.append(d)
        d += 0.5

    if not durations:
        log_request(query.from_user.id, "Нет доступных вариантов длительности")
        keyboard = [[InlineKeyboardButton("⬅ Назад", callback_data="back_to_time_selection")]]
        await query.edit_message_text(
            text="Нет доступных временных слотов для бронирования.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    keyboard = []
    for dur in durations:
        label = format_duration(dur)
        keyboard.append([InlineKeyboardButton(label, callback_data=f"duration_{dur}")])

    keyboard.append([InlineKeyboardButton("⬅ Назад", callback_data=f"room_{room}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Выберите продолжительность бронирования:", reply_markup=reply_markup)

async def choose_duration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик выбора длительности: записываем бронирование в базу.
    После успеха -> кнопка "Запустить бота".
    """
    query = update.callback_query
    await query.answer()

    duration = float(query.data.split("_")[1])
    room = context.user_data["room"]
    start_time = context.user_data["time"]

    log_request(query.from_user.id,
                f"Выбрал длительность {format_duration(duration)} для {room}, с {format_time_slot(start_time)}")

    try:
        conn = sqlite3.connect("booking.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO bookings (user_id, room, date, time, duration)
            VALUES (?, ?, date('now'), ?, ?)
        """, (query.from_user.id, room, start_time, duration))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при сохранении: {e}")
        await query.edit_message_text("Произошла ошибка сохранения. Попробуйте позже.")
        return
    finally:
        conn.close()

    # Кнопка для возврата к /start
    keyboard = [[InlineKeyboardButton("Запустить бота", callback_data="start_bot")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text=f"✅ Бронь на {room} в {format_time_slot(start_time)} на {format_duration(duration)} успешно создана!",
        reply_markup=reply_markup
    )

async def cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик кнопки "Отменить бронь": показывает список активных бронирований пользователя на сегодня.
    """
    query = update.callback_query
    user_id = query.from_user.id

    log_request(user_id, "Нажал кнопку 'Отменить бронь'")

    try:
        conn = sqlite3.connect("booking.db")
        cursor = conn.cursor()
        cursor.execute("SELECT room, time FROM bookings WHERE user_id = ? AND date = date('now')", (user_id,))
        bookings = cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении бронирований: {e}")
        await query.answer("Произошла ошибка при получении данных.", show_alert=True)
        return
    finally:
        conn.close()

    if not bookings:
        await query.answer("У вас нет активных бронирований.", show_alert=True)
        return

    keyboard = []
    for (room, time) in bookings:
        keyboard.append([InlineKeyboardButton(f"{room} в {format_time_slot(time)}", callback_data=f"delete_{room}_{time}")])
    keyboard.append([InlineKeyboardButton("⬅ Назад", callback_data="back_start")])

    await query.edit_message_text(text="Выберите бронь для отмены:", reply_markup=InlineKeyboardMarkup(keyboard))

async def delete_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик удаления бронирования: удаляет выбранное бронирование из базы данных.
    """
    query = update.callback_query
    _, room, time = query.data.split("_")
    user_id = query.from_user.id

    log_request(user_id, f"Отменил бронь на {room} в {format_time_slot(float(time))}")

    try:
        conn = sqlite3.connect("booking.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bookings WHERE user_id= ? AND room = ? AND time = ? AND date = date('now')",
                       (user_id, room, float(time)))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при удалении бронирования: {e}")
        await query.answer("Произошла ошибка при отмене бронирования.", show_alert=True)
        return
    finally:
        conn.close()

    # Кнопка для возврата к /start
    keyboard = [[InlineKeyboardButton("Запустить бота", callback_data="start_bot")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=f"❌ Бронь на {room} в {format_time_slot(float(time))} отменена.", reply_markup=reply_markup)

async def start_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик кнопки "Запустить бота": возвращает пользователя в главное меню.
    """
    query = update.callback_query
    await query.answer()
    await start(query, context)

async def go_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик кнопки "Назад": возвращает пользователя в главное меню.
    """
    query = update.callback_query
    await query.answer()
    await start(query, context)

def main():
    """
    Основная функция: инициализация базы данных и запуск бота.
    """
    init_db()

    # Запускаем планировщик в отдельном потоке
    threading.Thread(target=run_schedule, daemon=True).start()
    schedule_clear_bookings()

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(available_rooms, pattern="^available_rooms$"))
    application.add_handler(CallbackQueryHandler(choose_building, pattern="^building_"))
    application.add_handler(CallbackQueryHandler(choose_room, pattern="^room_"))
    application.add_handler(CallbackQueryHandler(choose_time, pattern="^time_"))
    application.add_handler(CallbackQueryHandler(choose_duration, pattern="^duration_"))
    application.add_handler(CallbackQueryHandler(cancel_booking, pattern="^cancel_booking$"))
    application.add_handler(CallbackQueryHandler(delete_booking, pattern="^delete_"))
    application.add_handler(CallbackQueryHandler(go_back, pattern="^back_start$"))
    application.add_handler(CallbackQueryHandler(start_bot, pattern="^start_bot$"))

    logger.info("Бот запущен. Нажмите Ctrl+C для остановки.")
    application.run_polling()

if __name__ == "__main__":
    main()
