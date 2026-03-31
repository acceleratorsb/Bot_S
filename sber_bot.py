import asyncio
import requests
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import FSInputFile

# Импорты для веб-сервера
from flask import Flask
import threading

API_TOKEN = '8409242586:AAGeTLoHT2pbOK1n1IiaTNTb8Pvj1YT3_WU'

storage = MemoryStorage()
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=storage)

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    """Создаёт таблицу пользователей, если её нет"""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  first_name TEXT,
                  last_name TEXT,
                  first_completed TEXT,
                  last_completed TEXT,
                  last_reminder_sent TEXT)''')
    conn.commit()
    conn.close()

init_db()

def save_user_completion(user_id, username, first_name, last_name):
    """Сохраняет, что пользователь заполнил анкету"""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    now = datetime.now(timezone(timedelta(hours=3))).isoformat()
    
    c.execute('SELECT first_completed FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    
    if result and result[0]:
        c.execute('''UPDATE users 
                     SET username = ?, first_name = ?, last_name = ?, last_completed = ?
                     WHERE user_id = ?''',
                  (username, first_name, last_name, now, user_id))
    else:
        c.execute('''INSERT INTO users 
                     (user_id, username, first_name, last_name, first_completed, last_completed)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (user_id, username, first_name, last_name, now, now))
    
    conn.commit()
    conn.close()
    print(f"✅ Пользователь {user_id} сохранён в базе")

def get_users_to_notify():
    """Получает пользователей, которым пора отправить напоминание (раз в месяц)"""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''SELECT user_id, first_name FROM users
                 WHERE last_reminder_sent IS NULL 
                    OR datetime(last_reminder_sent) < datetime('now', '-30 days')''')
    users = c.fetchall()
    conn.close()
    return users

def update_last_reminder_sent(user_id):
    """Обновляет дату последнего напоминания"""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    now = datetime.now(timezone(timedelta(hours=3))).isoformat()
    c.execute('UPDATE users SET last_reminder_sent = ? WHERE user_id = ?', (now, user_id))
    conn.commit()
    conn.close()

# ==================== КЛАВИАТУРЫ ====================

start_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🚀 Начать заполнение")]],
    resize_keyboard=True,
    one_time_keyboard=True
)

def get_invest_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, привлекли инвестиции", callback_data="invest_yes")
    builder.button(text="🔄 В процессе привлечения", callback_data="invest_process")
    builder.button(text="❌ Нет, не было инвестиций", callback_data="invest_no")
    builder.adjust(1)
    return builder.as_markup()

def get_pilot_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, запустили пилот", callback_data="pilot_yes")
    builder.button(text="❌ Нет, пилотов не было", callback_data="pilot_no")
    builder.adjust(1)
    return builder.as_markup()

def get_news_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔹 Поделиться новостями", callback_data="news_share")
    builder.button(text="🔸 Нет новостей за месяц", callback_data="news_none")
    builder.adjust(1)
    return builder.as_markup()

def get_edit_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="💼 Инвестиции", callback_data="edit_investments")
    builder.button(text="💰 Выручка и клиенты", callback_data="edit_revenue")
    builder.button(text="✈️ Пилоты", callback_data="edit_pilots")
    builder.button(text="📢 Другие новости", callback_data="edit_news")
    builder.button(text="🔄 Заполнить всё заново", callback_data="edit_restart")
    builder.adjust(1)
    return builder.as_markup()

def get_summary_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Всё верно, отправить", callback_data="summary_confirm")
    builder.button(text="✏️ Редактировать ответ", callback_data="summary_edit")
    builder.adjust(1)
    return builder.as_markup()

# ==================== КЛАСС СОСТОЯНИЙ ====================

class Form(StatesGroup):
    startup_name = State()
    investment_status = State()
    investment_amount = State()
    investment_source = State()
    investment_terms = State()
    revenue = State()
    clients_count = State()
    pilot_status = State()
    pilot_company = State()
    pilot_essence = State()
    pilot_results = State()
    other_news = State()
    summary = State()
    edit_menu = State()

# ==================== ОБРАБОТЧИКИ ====================

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    
    await state.update_data(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )
    
    photo_path = "Картинки для бота/приветствие.png"
    
    welcome_text = (
        f"Здравствуйте, {message.from_user.first_name}! 👋\n\n"
        "Это акселераторы Сбера. 🚀\n\n"
        "Хотим узнать, как обстоят дела с вашим стартапом:\n"
        "есть ли достижения, как развивается стартап, есть ли пилоты и привлекли ли инвестиции?\n\n"
        "Лучшие истории попадут в итоговый дайджест сообщества.\n\n"
        "Заполните, пожалуйста, короткую форму — это займёт не более 2 минут.\n\n"
        "Нажмите кнопку, чтобы начать."
    )
    
    if os.path.exists(photo_path):
        try:
            photo = FSInputFile(photo_path)
            await message.answer_photo(
                photo=photo,
                caption=welcome_text,
                reply_markup=start_keyboard
            )
        except Exception as e:
            print(f"Ошибка отправки фото: {e}")
            await message.answer(welcome_text, reply_markup=start_keyboard)
    else:
        print(f"Файл не найден: {photo_path}")
        await message.answer(welcome_text, reply_markup=start_keyboard)

@dp.message(lambda message: message.text == "🚀 Начать заполнение")
async def handle_start_button(message: types.Message, state: FSMContext):
    await state.set_state(Form.startup_name)
    await message.answer(
        "Укажите название стартапа",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(Form.startup_name)
async def get_startup_name(message: types.Message, state: FSMContext):
    await state.update_data(startup_name=message.text)
    await state.set_state(Form.investment_status)
    await message.answer(
        "💼 Инвестиции\n\n"
        "Были ли у вас инвестиции за последний месяц?",
        reply_markup=get_invest_keyboard()
    )

@dp.callback_query(lambda c: c.data.startswith('invest_'))
async def process_investment(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()    
    data = callback.data
    if data == "invest_yes":
        await state.update_data(investment_status="✅ Да, привлекли инвестиции")
        await state.set_state(Form.investment_amount)
        await callback.message.answer(
            "Укажите сумму инвестиций за последний месяц.\n\n"
            "Введите сумму в миллионах рублей (можно дробные).\n"
            "Например: 5 (это 5 млн), 0,5 (это 500 тыс.)"
        )
    elif data == "invest_process":
        await state.update_data(investment_status="🔄 В процессе привлечения")
        await state.set_state(Form.investment_amount)
        await callback.message.answer(
            "Укажите сумму инвестиций за последний месяц.\n\n"
            "Введите сумму в миллионах рублей (можно дробные).\n"
            "Например: 5 (это 5 млн), 0,5 (это 500 тыс.)"
        )
    elif data == "invest_no":
        await state.update_data(investment_status="❌ Нет, не было инвестиций")
        await state.set_state(Form.revenue)
        await callback.message.answer(
            "💰 Выручка\n\n"
            "Какая выручка у стартапа была за последний месяц?\n\n"
            "Введите сумму в миллионах рублей.\n"
            "Если выручки не было — введите 0\n"
            "Например: 1,5 (это 1,5 млн)"
        )

@dp.message(Form.investment_amount)
async def get_investment_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(',', '.'))
        await state.update_data(investment_amount=amount)
        await state.set_state(Form.investment_source)
        await message.answer("Укажите тип инвестиций\n(Бизнес-ангел, фонд, компания-партнёр и т.д.)\n\nНапример: фонд Восход")
    except ValueError:
        await message.answer("Пожалуйста, введите число (например: 5 или 0,5)")

@dp.message(Form.investment_source)
async def get_investment_source(message: types.Message, state: FSMContext):
    await state.update_data(investment_source=message.text)
    await state.set_state(Form.investment_terms)
    await message.answer("На каких условиях привлечены инвестиции?\n(Доля в компании, конвертируемый займ, грант и т.д.)\n\nНапример: 10% доли")

@dp.message(Form.investment_terms)
async def get_investment_terms(message: types.Message, state: FSMContext):
    await state.update_data(investment_terms=message.text)
    
    data = await state.get_data()
    if data.get('edit_mode') == 'investments':
        await state.update_data(edit_mode=None)
        await show_summary(message, state)
    else:
        await state.set_state(Form.revenue)
        await message.answer(
            "💰 Выручка\n\n"
            "Какая выручка у стартапа была за последний месяц?\n\n"
            "Введите сумму в миллионах рублей.\n"
            "Если выручки не было — введите 0\n"
            "Например: 1,5 (э