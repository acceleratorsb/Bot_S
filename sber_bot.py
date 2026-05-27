import asyncio
import requests
import os
import re
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
from flask import Flask
import threading
 
API_TOKEN = '8409242586:AAGeTLoHT2pbOK1n1IiaTNTb8Pvj1YT3_WU'
 
storage = MemoryStorage()
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=storage)
 
ADMIN_IDS = [
    1123186704,
]
 
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
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    now = datetime.now(timezone(timedelta(hours=3))).isoformat()
    c.execute('SELECT first_completed FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    if result and result[0]:
        c.execute('''UPDATE users SET username=?, first_name=?, last_name=?, last_completed=?
                     WHERE user_id=?''', (username, first_name, last_name, now, user_id))
    else:
        c.execute('''INSERT INTO users (user_id, username, first_name, last_name, first_completed, last_completed)
                     VALUES (?, ?, ?, ?, ?, ?)''', (user_id, username, first_name, last_name, now, now))
    conn.commit()
    conn.close()
    print(f"✅ Пользователь {user_id} сохранён в базе")
 
def get_all_users():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT user_id, first_name, username FROM users")
    users = c.fetchall()
    conn.close()
    return users
 
def update_last_reminder_sent(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    now = datetime.now(timezone(timedelta(hours=3))).isoformat()
    c.execute('UPDATE users SET last_reminder_sent=? WHERE user_id=?', (now, user_id))
    conn.commit()
    conn.close()
 
# ==================== АВТОБЭКАП ====================
 
async def auto_backup():
    """Каждые 3 дня отправляет бэкап базы всем админам"""
    while True:
        await asyncio.sleep(3 * 24 * 3600)  # 3 дня
        if os.path.exists('users.db'):
            now_str = datetime.now(timezone(timedelta(hours=3))).strftime('%Y-%m-%d')
            for admin_id in ADMIN_IDS:
                try:
                    with open('users.db', 'rb') as f:
                        await bot.send_document(
                            admin_id,
                            types.BufferedInputFile(f.read(), filename=f'users_{now_str}.db'),
                            caption=f"🗄 Автобэкап базы пользователей за {now_str}"
                        )
                except Exception as e:
                    print(f"❌ Ошибка автобэкапа для {admin_id}: {e}")
        print("✅ Автобэкап выполнен")
 
# ==================== ПАРСЕР СУММЫ ====================
 
def parse_amount(text: str):
    text = text.strip().lower()
    text = re.sub(r'(\d)\s+(\d)', r'\1\2', text)
    number_match = re.search(r'[\d]+[.,]?[\d]*', text)
    if not number_match:
        return None
    number = float(number_match.group().replace(',', '.'))
    if any(w in text for w in ['млрд', 'миллиард']):
        return number * 1000
    elif any(w in text for w in ['млн', 'миллион']):
        return number
    elif any(w in text for w in ['тыс', 'тысяч', ' k', 'к ']):
        return number / 1000
    elif number >= 100_000:
        return number / 1_000_000
    else:
        return number
 
def format_amount(amount_mln: float) -> str:
    if amount_mln == 0:
        return "0 млн ₽"
    elif amount_mln < 1:
        thousands = amount_mln * 1000
        if thousands == int(thousands):
            return f"{int(thousands)} тыс ₽"
        else:
            return f"{thousands:.0f} тыс ₽"
    elif amount_mln >= 1000:
        bln = amount_mln / 1000
        return f"{bln:g} млрд ₽"
    else:
        if amount_mln == int(amount_mln):
            return f"{int(amount_mln)} млн ₽"
        else:
            return f"{amount_mln:g} млн ₽"
 
# ==================== КЛАВИАТУРЫ ====================
 
start_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🚀 Начать заполнение")]],
    resize_keyboard=True,
    one_time_keyboard=True
)
 
def get_invest_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, привлекли инвестиции (не гранты)", callback_data="invest_yes")
    builder.button(text="🔄 Веду переговоры, сделка ещё не закрыта", callback_data="invest_process")
    builder.button(text="❌ Нет, не было инвестиций", callback_data="invest_no")
    builder.adjust(1)
    return builder.as_markup()
 
def get_amount_confirm_keyboard(field: str):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Верно, продолжить", callback_data=f"amount_ok_{field}")
    builder.button(text="✏️ Исправить", callback_data=f"amount_fix_{field}")
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
 
def get_broadcast_confirm_keyboard():
    """Кнопки подтверждения рассылки для админа"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, запустить рассылку", callback_data="broadcast_yes")
    builder.button(text="❌ Нет, отменить", callback_data="broadcast_no")
    builder.adjust(1)
    return builder.as_markup()
 
# ==================== КЛАСС СОСТОЯНИЙ ====================
 
class Form(StatesGroup):
    startup_name = State()
    investment_status = State()
    investment_amount = State()
    investment_amount_confirm = State()
    investment_source = State()
    investment_terms = State()
    invest_process_amount = State()
    invest_process_amount_confirm = State()
    revenue = State()
    revenue_confirm = State()
    pilot_status = State()
    pilot_company = State()
    pilot_essence = State()
    pilot_results = State()
    other_news = State()
    summary = State()
    edit_menu = State()
 
# ==================== СТАРТ ====================
 
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
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Это акселераторы Сбера 🚀\n\n"
        "Хотим узнать, как дела у твоего стартапа за этот месяц: "
        "какие успехи, пилоты, инвестиции?\n\n"
        "Лучшие истории попадут в дайджест сообщества.\n\n"
        "Заполни короткую форму — это займёт не больше 2 минут. "
        "Жми на кнопку, поехали! 👇"
    )
 
    if os.path.exists(photo_path):
        try:
            photo = FSInputFile(photo_path)
            await message.answer_photo(photo=photo, caption=welcome_text, reply_markup=start_keyboard)
        except Exception as e:
            print(f"Ошибка отправки фото: {e}")
            await message.answer(welcome_text, reply_markup=start_keyboard)
    else:
        await message.answer(welcome_text, reply_markup=start_keyboard)
 
@dp.message(lambda message: message.text == "🚀 Начать заполнение")
async def handle_start_button(message: types.Message, state: FSMContext):
    save_user_completion(
        user_id=message.from_user.id,
        username=message.from_user.username or '',
        first_name=message.from_user.first_name or '',
        last_name=message.from_user.last_name or ''
    )
    await state.set_state(Form.startup_name)
    await message.answer("Укажи название стартапа", reply_markup=ReplyKeyboardRemove())
 
@dp.message(Form.startup_name)
async def get_startup_name(message: types.Message, state: FSMContext):
    await state.update_data(startup_name=message.text)
    await state.set_state(Form.investment_status)
    await message.answer(
        "💼 Инвестиции\n\n"
        "Был ли у вас договор о привлечении инвестиций за последний месяц?\n\n"
        "⚠️ Важно: гранты (Сколково, Фонд содействия и др.) сюда не относятся — "
        "их указывай в разделе «Другие новости».\n\n"
        "Выбери свой вариант 👇",
        reply_markup=get_invest_keyboard()
    )
 
# ==================== ВЕТКА А — ПРИВЛЕКЛИ ====================
 
@dp.callback_query(lambda c: c.data == "invest_yes")
async def process_invest_yes(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(investment_status="✅ Да, привлекли инвестиции")
    await state.set_state(Form.investment_amount)
    await callback.message.answer(
        "💰 Отлично! 🎉\n\n"
        "Какую сумму привлекли за последний месяц?\n\n"
        "Можно писать как удобно: <b>5 млн</b>, <b>500 тыс</b>, <b>5 000 000</b> или просто <b>5</b>",
        parse_mode="HTML"
    )
 
@dp.message(Form.investment_amount)
async def get_investment_amount(message: types.Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer(
            "Не смог распознать сумму 🤔\n\n"
            "Попробуй написать иначе, например: <b>5 млн</b>, <b>500 тыс</b> или просто <b>5</b>",
            parse_mode="HTML"
        )
        return
    await state.update_data(investment_amount=amount)
    await state.set_state(Form.investment_amount_confirm)
    await message.answer(
        f"Я понял так: <b>{format_amount(amount)}</b> — верно?",
        parse_mode="HTML",
        reply_markup=get_amount_confirm_keyboard("inv")
    )
 
@dp.callback_query(lambda c: c.data == "amount_ok_inv")
async def investment_amount_confirmed(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(Form.investment_source)
    await callback.message.answer(
        "🏦 Отлично! Теперь укажи источник инвестиций: фонд, бизнес-ангел, компания-партнёр?\n\n"
        "Можешь написать название или ФИО.\n\n"
        "⚠️ Гранты по-прежнему не вписываем сюда 🙂"
    )
 
@dp.callback_query(lambda c: c.data == "amount_fix_inv")
async def investment_amount_fix(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(Form.investment_amount)
    await callback.message.answer(
        "Введи сумму снова — только цифру в млн:\n\n"
        "Например: <b>5</b> для 5 млн или <b>0,5</b>, если это 500 тысяч",
        parse_mode="HTML"
    )
 
@dp.message(Form.investment_source)
async def get_investment_source(message: types.Message, state: FSMContext):
    await state.update_data(investment_source=message.text)
    await state.set_state(Form.investment_terms)
    await message.answer(
        "📄 На каких условиях привлекли инвестиции?\n\n"
        "Например: доля 10%, конвертируемый займ, опцион и т.д."
    )
 
@dp.message(Form.investment_terms)
async def get_investment_terms(message: types.Message, state: FSMContext):
    await state.update_data(investment_terms=message.text)
    data = await state.get_data()
    if data.get('edit_mode') == 'investments':
        await state.update_data(edit_mode=None)
        await show_summary(message, state)
    else:
        await ask_revenue(message, state)
 
# ==================== ВЕТКА Б — В ПРОЦЕССЕ ====================
 
@dp.callback_query(lambda c: c.data == "invest_process")
async def process_invest_process(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(
        investment_status="🔄 Веду переговоры, сделка не закрыта",
        invest_process_stage="",
        investment_source="В процессе переговоров",
        investment_terms="—"
    )
    await state.set_state(Form.invest_process_amount)
    await callback.message.answer(
        "🤝 Понял, переговоры в процессе!\n\n"
        "Какой примерный объём раунда планируете?\n\n"
        "Можно писать как удобно: <b>5 млн</b>, <b>500 тыс</b>, <b>5 000 000</b>\n"
        "Если пока неизвестно — введи <b>0</b>",
        parse_mode="HTML"
    )
 
@dp.message(Form.invest_process_amount)
async def get_invest_process_amount(message: types.Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer(
            "Не смог распознать сумму 🤔\n\n"
            "Попробуй написать иначе, например: <b>5 млн</b>, <b>500 тыс</b> или <b>0</b> если неизвестно",
            parse_mode="HTML"
        )
        return
    await state.update_data(invest_process_amount=amount)
    if amount == 0:
        await state.update_data(investment_amount=0)
        await ask_revenue(message, state)
    else:
        await state.set_state(Form.invest_process_amount_confirm)
        await message.answer(
            f"Понял: планируемый объём раунда <b>{format_amount(amount)}</b> — верно?",
            parse_mode="HTML",
            reply_markup=get_amount_confirm_keyboard("proc")
        )
 
@dp.callback_query(lambda c: c.data == "amount_ok_proc")
async def invest_process_amount_confirmed(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await state.update_data(investment_amount=data.get('invest_process_amount', 0))
    await ask_revenue(callback.message, state)
 
@dp.callback_query(lambda c: c.data == "amount_fix_proc")
async def invest_process_amount_fix(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(Form.invest_process_amount)
    await callback.message.answer(
        "Введи сумму снова — только цифру в млн:\n\n"
        "Например: <b>5</b> для 5 млн или <b>0,5</b>, если это 500 тысяч",
        parse_mode="HTML"
    )
 
# ==================== ВЕТКА В — НЕТ ИНВЕСТИЦИЙ ====================
 
@dp.callback_query(lambda c: c.data == "invest_no")
async def process_invest_no(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(
        investment_status="❌ Нет, не было инвестиций",
        investment_amount=0,
        investment_source="—",
        investment_terms="—",
        invest_process_stage=""
    )
    await ask_revenue(callback.message, state)
 
# ==================== ВЫРУЧКА ====================
 
async def ask_revenue(message: types.Message, state: FSMContext):
    await state.set_state(Form.revenue)
    await message.answer(
        "💰 Выручка\n\n"
        "Какая выручка у стартапа была за последний месяц?\n\n"
        "Можно писать как удобно: <b>1,5 млн</b>, <b>500 тыс</b>, <b>1 500 000</b>\n"
        "Если выручки не было — введи <b>0</b>",
        parse_mode="HTML"
    )
 
@dp.message(Form.revenue)
async def get_revenue(message: types.Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer(
            "Не смог распознать сумму 🤔\n\n"
            "Попробуй написать иначе, например: <b>1,5 млн</b>, <b>500 тыс</b> или <b>0</b>",
            parse_mode="HTML"
        )
        return
    await state.update_data(revenue=amount)
    if amount == 0:
        await ask_pilots(message, state)
    else:
        await state.set_state(Form.revenue_confirm)
        await message.answer(
            f"Я понял: выручка <b>{format_amount(amount)}</b> — верно?",
            parse_mode="HTML",
            reply_markup=get_amount_confirm_keyboard("rev")
        )
 
@dp.callback_query(lambda c: c.data == "amount_ok_rev")
async def revenue_confirmed(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    if data.get('edit_mode') == 'revenue':
        await state.update_data(edit_mode=None)
        await show_summary(callback.message, state)
    else:
        await ask_pilots(callback.message, state)
 
@dp.callback_query(lambda c: c.data == "amount_fix_rev")
async def revenue_fix(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(Form.revenue)
    await callback.message.answer(
        "Введи сумму снова — только цифру в млн:\n\n"
        "Например: <b>5</b> для 5 млн или <b>0,5</b>, если это 500 тысяч",
        parse_mode="HTML"
    )
 
# ==================== ПИЛОТЫ ====================
 
async def ask_pilots(message: types.Message, state: FSMContext):
    await state.set_state(Form.pilot_status)
    await message.answer(
        "✈️ Пилоты и партнёрства\n\n"
        "Были ли новые пилоты с крупными компаниями за последний месяц?",
        reply_markup=get_pilot_keyboard()
    )
 
@dp.callback_query(lambda c: c.data.startswith('pilot_'))
async def process_pilot(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data == "pilot_yes":
        await state.update_data(pilot_status="✅ Да, запустили пилот")
        await state.set_state(Form.pilot_company)
        await callback.message.answer(
            "🏢 Отлично! С какой компанией запустили пилот?\n\n"
            "Например: ПАО Сбербанк, Ozon, Яндекс"
        )
    elif callback.data == "pilot_no":
        await state.update_data(
            pilot_status="❌ Нет, пилотов не было",
            pilot_company='', pilot_essence='', pilot_results=''
        )
        data = await state.get_data()
        if data.get('edit_mode') == 'pilots':
            await state.update_data(edit_mode=None)
            await show_summary(callback.message, state)
        else:
            await ask_other_news(callback.message, state)
 
@dp.message(Form.pilot_company)
async def get_pilot_company(message: types.Message, state: FSMContext):
    await state.update_data(pilot_company=message.text)
    await state.set_state(Form.pilot_essence)
    await message.answer(
        "🎯 В чём суть пилота?\n\n"
        "Например: тестирование платформы на 100 сотрудниках"
    )
 
@dp.message(Form.pilot_essence)
async def get_pilot_essence(message: types.Message, state: FSMContext):
    await state.update_data(pilot_essence=message.text)
    await state.set_state(Form.pilot_results)
    await message.answer(
        "📊 Какие результаты уже есть или ожидаются?\n\n"
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
        await ask_other_news(message, state)
 
# ==================== НОВОСТИ ====================
 
async def ask_other_news(message: types.Message, state: FSMContext):
    await state.set_state(Form.other_news)
    await message.answer(
        "📢 Другие новости\n\n"
        "Расскажи, что важно для тебя и стартапа:\n"
        "— технологические обновления (релиз, патент, pivot)\n"
        "— участие в мероприятиях, награды\n"
        "— выход на новые рынки\n"
        "— гранты (Сколково, Фонд содействия и др.)\n"
        "— другие важные события\n\n"
        "Если новостей нет — нажми кнопку ниже 👇",
        reply_markup=get_news_keyboard()
    )
 
@dp.callback_query(lambda c: c.data.startswith('news_'))
async def process_news(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data == "news_share":
        await callback.message.answer("📢 Расскажи, какие новости у тебя были за последний месяц:")
    elif callback.data == "news_none":
        await state.update_data(other_news="Нет новостей")
        data = await state.get_data()
        if data.get('edit_mode') == 'news':
            await state.update_data(edit_mode=None)
        await show_summary(callback.message, state)
 
@dp.message(Form.other_news)
async def get_other_news_text(message: types.Message, state: FSMContext):
    await state.update_data(other_news=message.text)
    data = await state.get_data()
    if data.get('edit_mode') == 'news':
        await state.update_data(edit_mode=None)
    await show_summary(message, state)
 
# ==================== САММАРИ ====================
 
async def show_summary(message: types.Message, state: FSMContext):
    data = await state.get_data()
 
    inv_status = data.get('investment_status', '—')
    if "переговоры" in inv_status.lower() or "процессе" in inv_status.lower():
        inv_amount = data.get('investment_amount', 0)
        inv_block = (
            f"{inv_status}\n"
            f"   Планируемый объём: {format_amount(inv_amount)}"
        )
    elif "привлекли" in inv_status.lower():
        inv_block = (
            f"{inv_status}\n"
            f"   Сумма: {format_amount(data.get('investment_amount', 0))}\n"
            f"   Источник: {data.get('investment_source', '—')}\n"
            f"   Условия: {data.get('investment_terms', '—')}"
        )
    else:
        inv_block = inv_status
 
    pilot_text = data.get('pilot_status', '—')
    if data.get('pilot_company'):
        pilot_text += f"\n   Компания: {data['pilot_company']}"
    if data.get('pilot_essence'):
        pilot_text += f"\n   Суть: {data['pilot_essence']}"
    if data.get('pilot_results'):
        pilot_text += f"\n   Результаты: {data['pilot_results']}"
 
    text = (
        "📋 Проверь свои ответы:\n\n"
        f"📌 Стартап: {data.get('startup_name', '—')}\n\n"
        f"💼 Инвестиции: {inv_block}\n\n"
        f"💰 Выручка за месяц: {format_amount(data.get('revenue', 0))}\n\n"
        f"✈️ Пилоты: {pilot_text}\n\n"
        f"📢 Новости: {data.get('other_news', '—')}\n\n"
        "Всё верно?"
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
        await callback.message.answer("Что хочешь отредактировать?", reply_markup=get_edit_keyboard())
 
@dp.callback_query(lambda c: c.data.startswith('edit_'))
async def process_edit(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data == "edit_investments":
        await state.update_data(
            investment_status='', investment_amount=0,
            investment_source='', investment_terms='',
            invest_process_stage='', invest_process_amount=0,
            edit_mode='investments'
        )
        await state.set_state(Form.investment_status)
        await callback.message.answer(
            "💼 Инвестиции\n\n"
            "Был ли у вас договор о привлечении инвестиций за последний месяц?\n\n"
            "⚠️ Важно: гранты (Сколково, Фонд содействия и др.) сюда не относятся — "
            "их указывай в разделе «Другие новости».\n\n"
            "Выбери свой вариант 👇",
            reply_markup=get_invest_keyboard()
        )
    elif callback.data == "edit_revenue":
        await state.update_data(revenue=0, edit_mode='revenue')
        await state.set_state(Form.revenue)
        await callback.message.answer(
            "💰 Выручка\n\n"
            "Какая выручка у стартапа была за последний месяц?\n\n"
            "Можно писать как удобно: <b>1,5 млн</b>, <b>500 тыс</b>, <b>1 500 000</b>\n"
            "Если выручки не было — введи <b>0</b>",
            parse_mode="HTML"
        )
    elif callback.data == "edit_pilots":
        await state.update_data(
            pilot_status='', pilot_company='',
            pilot_essence='', pilot_results='',
            edit_mode='pilots'
        )
        await state.set_state(Form.pilot_status)
        await callback.message.answer(
            "✈️ Пилоты\n\nБыли ли новые пилоты за последний месяц?",
            reply_markup=get_pilot_keyboard()
        )
    elif callback.data == "edit_news":
        await state.update_data(other_news='', edit_mode='news')
        await state.set_state(Form.other_news)
        await callback.message.answer(
            "📢 Другие новости\n\nПоделись новостями или выбери вариант ниже.",
            reply_markup=get_news_keyboard()
        )
    elif callback.data == "edit_restart":
        await state.clear()
        await cmd_start(callback.message, state)
 
# ==================== ОТПРАВКА В SHEETS ====================
 
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
        "invest_process_stage": data.get('invest_process_stage', ''),
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
                "✅ Готово! Спасибо за информацию, мы получили все данные!",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            await message.answer(
                f"⚠️ Ошибка отправки. Код: {response.status_code}",
                reply_markup=ReplyKeyboardRemove()
            )
    except Exception as e:
        await message.answer(f"❌ Ошибка соединения: {e}", reply_markup=ReplyKeyboardRemove())
        print(f"Ошибка отправки: {e}")
 
    await state.clear()
 
# ==================== РАССЫЛКА ====================
 
MONTHLY_REMINDER_TEXT = (
    "📅 Мы собираем дайджест каждый месяц!\n\n"
    "Расскажи, что нового случилось с твоим стартапом за этот месяц? "
    "Какие достижения, пилоты, инвестиции?\n\n"
    "Заполни короткую форму — займёт не больше 2 минут. "
    "Жми на кнопку, поехали! 👇"
)
 
async def do_broadcast():
    """Выполняет рассылку всем пользователям из базы"""
    users = get_all_users()
    photo_path = "Картинки для бота/приветствие.png"
    success = []
    failed = []
 
    for user in users:
        user_id, first_name, username = user
        username = username or "нет username"
        caption = f"{first_name}, {MONTHLY_REMINDER_TEXT}" if first_name else MONTHLY_REMINDER_TEXT
        try:
            if os.path.exists(photo_path):
                photo = FSInputFile(photo_path)
                await bot.send_photo(user_id, photo=photo, caption=caption, reply_markup=start_keyboard)
            else:
                await bot.send_message(user_id, caption, reply_markup=start_keyboard)
            success.append(f"{first_name or 'Без имени'} (@{username})")
            await asyncio.sleep(0.05)
        except Exception as e:
            failed.append(f"{first_name or 'Без имени'} (@{username}) — {str(e)[:50]}")
            print(f"❌ Ошибка пользователю {user_id}: {e}")
 
    report = f"📅 **Рассылка завершена!**\n\n📊 **Успешно:** {len(success)}\n❌ **Ошибок:** {len(failed)}\n\n"
    if success:
        report += "**✅ Получили:**\n"
        for s in success[:20]:
            report += f"• {s}\n"
        if len(success) > 20:
            report += f"\n... и ещё {len(success) - 20} человек(а)\n"
    if failed:
        report += "\n**❌ Не получили:**\n"
        for f in failed[:20]:
            report += f"• {f}\n"
        if len(failed) > 20:
            report += f"\n... и ещё {len(failed) - 20} ошибок"
 
    for admin_id in ADMIN_IDS:
        await bot.send_message(admin_id, report[:4000], parse_mode="Markdown")
 
    print("Рассылка завершена!")
 
async def schedule_auto_monthly():
    """Планировщик: 3-е число в 10:00 — сначала спрашивает у админа подтверждение"""
    while True:
        now = datetime.now(timezone(timedelta(hours=3)))
        target = now.replace(day=3, hour=10, minute=0, second=0, microsecond=0)
        if now.day > 3 or (now.day == 3 and now.hour >= 10):
            if now.month == 12:
                target = target.replace(year=now.year + 1, month=1)
            else:
                target = target.replace(month=now.month + 1)
        wait_seconds = (target - now).total_seconds()
        print(f"⏰ Следующая рассылка: {target.strftime('%Y-%m-%d %H:%M')} (через {wait_seconds / 3600:.1f} ч)")
        await asyncio.sleep(wait_seconds)
        await ask_admin_broadcast_confirm()
 
async def ask_admin_broadcast_confirm():
    """Отправляет админам запрос на подтверждение рассылки"""
    users = get_all_users()
    if not users:
        for admin_id in ADMIN_IDS:
            await bot.send_message(admin_id, "📭 База пользователей пуста. Рассылка отменена.")
        return
 
    names = [f"{u[1] or 'Без имени'} (@{u[2] or 'нет username'})" for u in users]
    preview = "\n".join(f"• {n}" for n in names[:20])
    if len(names) > 20:
        preview += f"\n... и ещё {len(names) - 20} человек(а)"
 
    text = (
        f"📅 Запланирована ежемесячная рассылка!\n\n"
        f"Получат сообщение ({len(users)} чел.):\n{preview}\n\n"
        f"Запустить рассылку?"
    )
    for admin_id in ADMIN_IDS:
        await bot.send_message(admin_id, text, reply_markup=get_broadcast_confirm_keyboard())
 
@dp.callback_query(lambda c: c.data == "broadcast_yes")
async def broadcast_confirmed(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("🔄 Запускаю рассылку...")
    await do_broadcast()
 
@dp.callback_query(lambda c: c.data == "broadcast_no")
async def broadcast_cancelled(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("❌ Рассылка отменена.")
 
# ==================== ФОНОВЫЙ ПИНГ ====================
 
async def keep_alive():
    while True:
        await asyncio.sleep(600)
        try:
            requests.get("https://bot-s-tdrx.onrender.com/keepalive", timeout=5)
            print("✅ Пинг выполнен")
        except Exception as e:
            print(f"❌ Ошибка пинга: {e}")
 
# ==================== ВЕБ-СЕРВЕР ====================
 
app = Flask(__name__)
 
@app.route('/')
def health():
    return "Bot is running!", 200
 
@app.route('/ping')
def ping():
    return "OK", 200
 
@app.route('/keepalive')
def keepalive():
    return "OK", 200
 
def run_web_server():
    app.run(host='0.0.0.0', port=8000)
 
# ==================== ЗАПУСК ====================
 
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
 
    asyncio.create_task(keep_alive())
    print("✅ Пинг запущен")
 
    asyncio.create_task(schedule_auto_monthly())
    print("✅ Планировщик рассылки запущен (3-е число в 10:00)")
 
    asyncio.create_task(auto_backup())
    print("✅ Автобэкап запущен (каждые 3 дня)")
 
    print("Бот запущен!")
    await dp.start_polling(bot)
 
# ==================== АДМИНСКИЕ КОМАНДЫ ====================
 
@dp.message(Command("db"))
async def show_db(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Эта команда только для администраторов")
        return
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT user_id, first_name, last_completed FROM users ORDER BY last_completed DESC")
    users = c.fetchall()
    conn.close()
    if not users:
        await message.answer("📭 База пользователей пуста")
        return
    text = "👥 **Пользователи в базе:**\n\n"
    for u in users:
        user_id, first_name, last_completed = u
        name = first_name if first_name else "без имени"
        date = last_completed[:16] if last_completed else "никогда"
        text += f"• {name} (ID: `{user_id}`)\n   Последнее действие: {date}\n\n"
    if len(text) > 4000:
        text = text[:4000] + "\n\n... (обрезано)"
    await message.answer(text, parse_mode="Markdown")
 
@dp.message(Command("send_now"))
async def send_now(message: types.Message, state: FSMContext):
    """Сразу показывает список и спрашивает подтверждение — как плановая рассылка"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Нет прав")
        return
    await ask_admin_broadcast_confirm()
 
@dp.message(Command("backup"))
async def backup_db(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Нет прав")
        return
    if os.path.exists('users.db'):
        with open('users.db', 'rb') as f:
            await message.answer_document(
                types.BufferedInputFile(f.read(), filename='users.db'),
                caption="📦 Бэкап базы пользователей"
            )
    else:
        await message.answer("❌ Файл базы не найден")
 
@dp.message(Command("restore"))
async def restore_db(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Нет прав")
        return
    if not message.document:
        await message.answer("❌ Отправь файл users.db вместе с командой /restore")
        return
    if message.document.file_name != 'users.db':
        await message.answer("❌ Файл должен называться users.db")
        return
    await message.answer("🔄 Загружаю файл...")
    try:
        file = await bot.get_file(message.document.file_id)
        file_data = await bot.download_file(file.file_path)
        with open('users.db', 'wb') as f:
            f.write(file_data.read())
        await message.answer("✅ База восстановлена!")
    except Exception as e:
        await message.answer(f"❌ Ошибка восстановления: {e}")
 
@dp.message(Command("check_reminder"))
async def check_reminder(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Нет прав")
        return
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT user_id, first_name, last_reminder_sent FROM users")
    users = c.fetchall()
    conn.close()
    if not users:
        await message.answer("📭 База пуста")
        return
    text = "📋 **Пользователи в базе:**\n\n"
    for user_id, first_name, last_sent in users:
        name = first_name if first_name else "без имени"
        status = "никогда не получал" if last_sent is None else last_sent[:16]
        text += f"• {name}: последняя рассылка — {status}\n"
    await message.answer(text[:4000], parse_mode="Markdown")
 
if __name__ == "__main__":
    asyncio.run(main())