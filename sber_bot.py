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
    """Сохраняет или обновляет пользователя в базе"""
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
    """Возвращает пользователей, которым пора отправить напоминание"""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''SELECT user_id, first_name FROM users
                 WHERE last_reminder_sent IS NULL 
                    OR datetime(last_reminder_sent) < datetime('now', '-30 days')''')
    users = c.fetchall()
    conn.close()
    print(f"📊 Найдено пользователей для рассылки: {len(users)}")
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
    builder.button(text="💰 Выручка", callback_data="edit_revenue")
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
        f"Здравствуй, {message.from_user.first_name}! 👋\n\n"
        "Это акселераторы Сбера 🚀\n\n"
        "Хотим узнать, как обстоят дела с твоим стартапом:\n"
        "есть ли достижения, как развивается стартап, есть ли пилоты и привлекли ли инвестиции за последний месяц?\n\n"
        "Лучшие истории попадут в итоговый дайджест сообщества.\n\n"
        "Заполни, пожалуйста, короткую форму — это займёт не более 2 минут.\n\n"
        "Нажми кнопку, чтобы начать."
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
    user_id = message.from_user.id
    
    # Сохраняем пользователя в базу сразу при нажатии кнопки
    save_user_completion(
        user_id=user_id,
        username=message.from_user.username or '',
        first_name=message.from_user.first_name or '',
        last_name=message.from_user.last_name or ''
    )
    
    await state.set_state(Form.startup_name)
    await message.answer(
        "Укажи название стартапа",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(Form.startup_name)
async def get_startup_name(message: types.Message, state: FSMContext):
    await state.update_data(startup_name=message.text)
    await state.set_state(Form.investment_status)
    await message.answer(
        "💼 Инвестиции\n\nБыли ли у тебя инвестиции за последний месяц?",
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
            "Укажи сумму инвестиций за последний месяц.\n\n"
            "Введи сумму в миллионах рублей (можно дробные).\n"
            "Например: 5 (это 5 млн), 0,5 (это 500 тыс.)"
        )
    elif data == "invest_process":
        await state.update_data(investment_status="🔄 В процессе привлечения")
        await state.set_state(Form.investment_amount)
        await callback.message.answer(
            "Укажи сумму инвестиций за последний месяц.\n\n"
            "Введи сумму в миллионах рублей (можно дробные).\n"
            "Например: 5 (это 5 млн), 0,5 (это 500 тыс.)"
        )
    elif data == "invest_no":
        await state.update_data(investment_status="❌ Нет, не было инвестиций")
        await state.set_state(Form.revenue)
        await callback.message.answer(
            "💰 Выручка\n\n"
            "Какая выручка у стартапа была за последний месяц?\n\n"
            "Введи сумму в миллионах рублей.\n"
            "Если выручки не было — введи 0\n"
            "Например: 1,5 (это 1,5 млн)"
        )

@dp.message(Form.investment_amount)
async def get_investment_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(',', '.'))
        await state.update_data(investment_amount=amount)
        await state.set_state(Form.investment_source)
        await message.answer(
            "Укажи источник инвестиций\n(Бизнес-ангел, фонд, компания-партнёр и т.д.)\n\n"
            "Например: фонд Восход"
        )
    except ValueError:
        await message.answer("Пожалуйста, введи число (например: 5 или 0,5)")

@dp.message(Form.investment_source)
async def get_investment_source(message: types.Message, state: FSMContext):
    await state.update_data(investment_source=message.text)
    await state.set_state(Form.investment_terms)
    await message.answer(
        "На каких условиях привлечены инвестиции?\n(Доля в компании, конвертируемый займ и т.д.)\n\n"
        "Например: 10% доли"
    )

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
            "Введи сумму в миллионах рублей.\n"
            "Если выручки не было — введи 0\n"
            "Например: 1,5 (это 1,5 млн)"
        )

@dp.message(Form.revenue)
async def get_revenue(message: types.Message, state: FSMContext):
    try:
        revenue = float(message.text.replace(',', '.'))
        await state.update_data(revenue=revenue)
        await state.set_state(Form.pilot_status)
        await message.answer(
            "✈️ Пилоты и партнёрства\n\n"
            "Были ли новые пилоты с крупными компаниями за последний месяц?",
            reply_markup=get_pilot_keyboard()
        )
    except ValueError:
        await message.answer("Пожалуйста, введи число (например: 1,5 или 0,3)")

@dp.callback_query(lambda c: c.data.startswith('pilot_'))
async def process_pilot(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    if callback.data == "pilot_yes":
        await state.update_data(pilot_status="✅ Да, запустили пилот")
        await state.set_state(Form.pilot_company)
        await callback.message.answer(
            "С какой компанией запустили пилот?\n\n"
            "Например: ПАО СберБанк"
        )
    elif callback.data == "pilot_no":
        await state.update_data(pilot_status="❌ Нет, пилотов не было", pilot_company='', pilot_essence='', pilot_results='')
        
        data = await state.get_data()
        if data.get('edit_mode') == 'pilots':
            await state.update_data(edit_mode=None)
            await show_summary(callback.message, state)
        else:
            await state.set_state(Form.other_news)
            await callback.message.answer(
                "📢 Другие новости\n\n"
                "Поделись тем, что важно для тебя и стартапа:\n\n"
                "- технологические обновления (новый продукт, релиз, патент, pivot)\n"
                "- участие в мероприятиях, награды, партнерства \n"
                "- выход на новые рынки\n"
                "- или другие важные новости для стартапа\n\n"
                "Если новостей нет — выбери вариант ниже.",
                reply_markup=get_news_keyboard()
            )

@dp.message(Form.pilot_company)
async def get_pilot_company(message: types.Message, state: FSMContext):
    await state.update_data(pilot_company=message.text)
    await state.set_state(Form.pilot_essence)
    await message.answer(
        "В чём суть пилота?\n\n"
        "Например: тестирование нашей платформы на 100 сотрудниках"
    )

@dp.message(Form.pilot_essence)
async def get_pilot_essence(message: types.Message, state: FSMContext):
    await state.update_data(pilot_essence=message.text)
    await state.set_state(Form.pilot_results)
    await message.answer(
        "Какие результаты уже есть или ожидаются?\n\n"
        "Например: планируем увеличить продажи на 20%"
    )

@dp.message(Form.pilot_results)
async def get_pilot_results(message: types.Message, state: FSMContext):
    await state.update_data(pilot_results=message.text)
    
    data = await state.get_data()
    if data.get('edit_mode') == 'pilots':
        await state.update_data(edit_mode=None)
        await show_summary(message, state)
    else:
        await state.set_state(Form.other_news)
        await message.answer(
            "📢 Другие новости\n\n"
            "Поделись тем, что важно для тебя и стартапа:\n\n"
            "- технологические обновления (новый продукт, релиз, патент, pivot)\n"
            "- участие в мероприятиях, награды, партнерства\n"
            "- выход на новые рынки\n"
            "- или другие важные новости для стартапа\n\n"
            "Если новостей нет — выбери вариант ниже.",
            reply_markup=get_news_keyboard()
        )

@dp.callback_query(lambda c: c.data.startswith('news_'))
async def process_news(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    if callback.data == "news_share":
        await callback.message.answer(
            "📢 Расскажи, какие новости у тебя были за последний месяц:"
        )
    elif callback.data == "news_none":
        await state.update_data(other_news="Нет новостей")
        
        data = await state.get_data()
        if data.get('edit_mode') == 'news':
            await state.update_data(edit_mode=None)
            await show_summary(callback.message, state)
        else:
            await show_summary(callback.message, state)

@dp.message(Form.other_news)
async def get_other_news_text(message: types.Message, state: FSMContext):
    await state.update_data(other_news=message.text)
    
    data = await state.get_data()
    if data.get('edit_mode') == 'news':
        await state.update_data(edit_mode=None)
        await show_summary(message, state)
    else:
        await show_summary(message, state)

async def show_summary(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    inv_amount = f"{data.get('investment_amount', 0):.2f}".replace('.', ',')
    revenue = f"{data.get('revenue', 0):.2f}".replace('.', ',')
    
    pilot_text = data.get('pilot_status', '—')
    if data.get('pilot_company'):
        pilot_text = f"{pilot_text}\n   Компания: {data['pilot_company']}"
    if data.get('pilot_essence'):
        pilot_text = f"{pilot_text}\n   Суть: {data['pilot_essence']}"
    if data.get('pilot_results'):
        pilot_text = f"{pilot_text}\n   Результаты: {data['pilot_results']}"
    
    text = (
        "📋 Проверьте информацию:\n\n"
        f"📌 Название стартапа: {data.get('startup_name', '—')}\n\n"
        f"💼 Инвестиции:\n"
        f"   Статус: {data.get('investment_status', '—')}\n"
        f"   Сумма: {inv_amount} млн ₽\n"
        f"   Источник: {data.get('investment_source', '—')}\n"
        f"   Условия: {data.get('investment_terms', '—')}\n\n"
        f"💰 Выручка: {revenue} млн ₽\n\n"
        f"✈️ Пилоты: {pilot_text}\n\n"
        f"📢 Новости: {data.get('other_news', '—')}"
    )
    
    await state.set_state(Form.summary)
    await message.answer(text, reply_markup=get_summary_keyboard())

@dp.callback_query(lambda c: c.data.startswith('summary_'))
async def process_summary(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    if callback.data == "summary_confirm":
        await send_to_sheets(callback.message, state)
    elif callback.data == "summary_edit":
        await state.set_state(Form.edit_menu)
        await callback.message.answer(
            "Что хочешь отредактировать?",
            reply_markup=get_edit_keyboard()
        )

@dp.callback_query(lambda c: c.data.startswith('edit_'))
async def process_edit(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    if callback.data == "edit_investments":
        await state.update_data(
            investment_status='',
            investment_amount=0,
            investment_source='',
            investment_terms='',
            edit_mode='investments'
        )
        await state.set_state(Form.investment_status)
        await callback.message.answer(
            "💼 Инвестиции\n\n"
            "Были ли у тебя инвестиции за последний месяц?",
            reply_markup=get_invest_keyboard()
        )
    elif callback.data == "edit_revenue":
        await state.update_data(revenue=0, edit_mode='revenue')
        await state.set_state(Form.revenue)
        await callback.message.answer(
            "💰 Выручка\n\n"
            "Какая выручка у стартапа была за последний месяц?\n\n"
            "Введи сумму в миллионах рублей.\n"
            "Например: 1,5 (это 1,5 млн)"
        )
    elif callback.data == "edit_pilots":
        await state.update_data(
            pilot_status='',
            pilot_company='',
            pilot_essence='',
            pilot_results='',
            edit_mode='pilots'
        )
        await state.set_state(Form.pilot_status)
        await callback.message.answer(
            "✈️ Пилоты\n\n"
            "Были ли новые пилоты за последний месяц?",
            reply_markup=get_pilot_keyboard()
        )
    elif callback.data == "edit_news":
        await state.update_data(other_news='', edit_mode='news')
        await state.set_state(Form.other_news)
        await callback.message.answer(
            "📢 Другие новости\n\n"
            "Поделись новостями или выбери вариант ниже.",
            reply_markup=get_news_keyboard()
        )
    elif callback.data == "edit_restart":
        await state.clear()
        await cmd_start(callback.message, state)

async def send_to_sheets(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id

    if not data.get('first_name'):
        data['first_name'] = message.from_user.first_name
    if not data.get('last_name'):
        data['last_name'] = message.from_user.last_name
    if not data.get('username'):
        data['username'] = message.from_user.username

    save_user_completion(
        user_id=user_id,
        username=data.get('username', ''),
        first_name=data.get('first_name', ''),
        last_name=data.get('last_name', '')
    )

    webhook_url = "https://flow.sokt.io/func/scri4EMJW50Q"

    payload = {
        "user_id": user_id,
        "username": data.get('username', ''),
        "first_name": data.get('first_name', ''),
        "last_name": data.get('last_name', ''),
        "submitted_at": datetime.now(timezone(timedelta(hours=3))).isoformat(),
        "startup_name": data.get('startup_name', ''),
        "investment_status": data.get('investment_status', ''),
        "investment_amount": data.get('investment_amount', 0),
        "investment_source": data.get('investment_source', ''),
        "investment_terms": data.get('investment_terms', ''),
        "revenue": data.get('revenue', 0),
        "pilot_status": data.get('pilot_status', ''),
        "pilot_company": data.get('pilot_company', ''),
        "pilot_essence": data.get('pilot_essence', ''),
        "pilot_results": data.get('pilot_results', ''),
        "other_news": data.get('other_news', '')
    }

    try:
        response = requests.post(webhook_url, json=payload)
        if response.status_code == 200:
            await message.answer(
                "✅ Готово! Спасибо за информацию, мы получили все данные!\n"
                "Дайджест будет опубликован в сообществе выпускников.",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            await message.answer(
                f"⚠️ Ошибка отправки. Код: {response.status_code}",
                reply_markup=ReplyKeyboardRemove()
            )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка соединения: {e}",
            reply_markup=ReplyKeyboardRemove()
        )
        print(f"Ошибка отправки: {e}")

    await state.clear()

# ==================== ФОНОВЫЙ ПИНГ (KEEP-ALIVE) ====================

async def keep_alive():
    """Каждые 10 минут пингует бота, чтобы он не засыпал на Render"""
    while True:
        await asyncio.sleep(600)  # 10 минут
        try:
            requests.get("https://bot-s-tdrx.onrender.com/keepalive", timeout=5)
            print("✅ Пинг выполнен, бот не спит")
        except Exception as e:
            print(f"❌ Ошибка пинга: {e}")

# ==================== ЕЖЕМЕСЯЧНАЯ РАССЫЛКА ====================

async def send_monthly_reminder():
    """Отправляет напоминание всем пользователям, которые давно не заполняли анкету"""
    print("Запускаем ежемесячную рассылку...")
    users = get_users_to_notify()
    print(f"📊 Найдено пользователей для рассылки: {len(users)}")
    
    reminder_text = (
        "📅 Мы собираем дайджест каждый месяц!\n\n"
        "Расскажи, что нового за этот месяц? "
        "Нажми кнопку, чтобы начать заполнение."
    )
    
    success = 0
    failed = 0
    
    for user in users:
        user_id = user[0]
        first_name = user[1] or "Друг"
        try:
            await bot.send_message(
                user_id,
                f"{first_name}, {reminder_text}",
                reply_markup=start_keyboard
            )
            update_last_reminder_sent(user_id)
            success += 1
            print(f"✅ Отправлено напоминание пользователю {user_id}")
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            print(f"❌ Ошибка отправки пользователю {user_id}: {e}")
    
    print(f"📊 Рассылка завершена! Успешно: {success}, Ошибок: {failed}")

async def schedule_monthly_reminder():
    """Планирует рассылку на 3-е число каждого месяца в 10:00 по Москве"""
    while True:
        now = datetime.now(timezone(timedelta(hours=3)))
        
        # Целевая дата: 3-е число текущего месяца в 10:00
        target = now.replace(day=3, hour=10, minute=0, second=0, microsecond=0)
        
        # Если 3-е число уже прошло в этом месяце, берём следующее 3-е число следующего месяца
        if now.day > 3 or (now.day == 3 and now.hour >= 10):
            if now.month == 12:
                target = target.replace(year=now.year + 1, month=1)
            else:
                target = target.replace(month=now.month + 1)
        
        wait_seconds = (target - now).total_seconds()
        print(f"⏰ Следующая рассылка запланирована на {target.strftime('%Y-%m-%d %H:%M')} (через {wait_seconds / 3600:.1f} часов)")
        
        await asyncio.sleep(wait_seconds)
        await send_monthly_reminder()

# ==================== ВЕБ-СЕРВЕР ДЛЯ RENDER ====================

app = Flask(__name__)

@app.route('/')
def health():
    return "Bot is running!", 200

@app.route('/ping')
def ping():
    return "OK", 200

@app.route('/keepalive')
def keepalive():
    """Эндпоинт для поддержания бота в активном состоянии"""
    return "OK", 200

def run_web_server():
    app.run(host='0.0.0.0', port=8000)

# ==================== ЗАПУСК БОТА ====================

async def main():
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("Webhook удалён!")
    except Exception as e:
        print(f"Ошибка удаления вебхука: {e}")
    
    web_thread = threading.Thread(target=run_web_server)
    web_thread.daemon = True
    web_thread.start()
    print("Веб-сервер запущен на порту 8000")
    
    # Запускаем фоновую задачу пинга
    asyncio.create_task(keep_alive())
    print("✅ Фоновая задача пинга запущена (каждые 10 минут)")
    
    # Запускаем планировщик ежемесячной рассылки
    asyncio.create_task(schedule_monthly_reminder())
    print("Планировщик ежемесячной рассылки запущен (каждое 3-е число в 10:00 по Москве)")
    
    print("Бот запущен и работает через start_polling!")
    await dp.start_polling(bot)
#ЭТО ВРЕМЕННО ДЛЯ ПРОВЕРКИ 
@dp.message(Command("db"))
async def show_db(message: types.Message, state: FSMContext):
    if message.from_user.id != 8409242586:
        await message.answer("⛔ Нет прав")
        return
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT user_id, first_name, last_completed FROM users")
    users = c.fetchall()
    conn.close()
    if not users:
        await message.answer("База пуста")
        return
    text = "👥 Пользователи в базе:\n"
    for u in users:
        text += f"ID: {u[0]}, имя: {u[1]}, дата: {u[2]}\n"
    await message.answer(text[:4000])
#ЭТО ВРЕМЕННО ДЛЯ ПРОВЕРКИ 

if __name__ == "__main__":
    asyncio.run(main())