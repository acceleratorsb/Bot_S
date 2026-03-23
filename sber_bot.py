import asyncio
import requests
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime
from aiogram.types import FSInputFile

API_TOKEN = '8409242586:AAGeTLoHT2pbOK1n1IiaTNTb8Pvj1YT3_WU'

storage = MemoryStorage()
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=storage)

class Form(StatesGroup):
    startup_name = State()
    investment_status = State()
    investment_amount = State()
    investment_source = State()
    investment_terms = State()
    revenue = State()
    clients_count = State()
    pilot_status = State()
    pilot_details = State()
    other_news = State()
    summary = State()
    edit_menu = State()

# ---- КЛАВИАТУРЫ ----

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

# ---- ОБРАБОТЧИКИ ----

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
        "Хотим узнать, как обстоят дела с вашим проектом:\n"
        "есть ли достижения, как развивается стартап, что с пилотами и инвестициями.\n\n"
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
            "Какая выручка у проекта была за последний месяц?\n\n"
            "Введите сумму в миллионах рублей.\n"
            "Если выручки не было — введите 0\n"
            "Пример: 1,5 (это 1,5 млн)"
        )

@dp.message(Form.investment_amount)
async def get_investment_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(',', '.'))
        await state.update_data(investment_amount=amount)
        await state.set_state(Form.investment_source)
        await message.answer("От кого привлечены инвестиции?\n(Бизнес-ангел, фонд, компания-партнёр и т.д.)")
    except ValueError:
        await message.answer("Пожалуйста, введите число (например: 5 или 0,5)")

@dp.message(Form.investment_source)
async def get_investment_source(message: types.Message, state: FSMContext):
    await state.update_data(investment_source=message.text)
    await state.set_state(Form.investment_terms)
    await message.answer("На каких условиях привлечены инвестиции?\n(Доля в компании, конвертируемый займ, грант и т.д.)")

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
            "Какая выручка у проекта была за последний месяц?\n\n"
            "Введите сумму в миллионах рублей.\n"
            "Если выручки не было — введите 0\n"
            "Пример: 1,5 (это 1,5 млн)"
        )

@dp.message(Form.revenue)
async def get_revenue(message: types.Message, state: FSMContext):
    try:
        revenue = float(message.text.replace(',', '.'))
        await state.update_data(revenue=revenue)
        await state.set_state(Form.clients_count)
        await message.answer(
            "👥 Клиенты\n\n"
            "Сколько клиентов у вас было за последний месяц?\n\n"
            "Введите число.\n"
            "Если клиентов не было — введите 0\n"
            "Пример: 15"
        )
    except ValueError:
        await message.answer("Пожалуйста, введите число (например: 1,5 или 0,3)")

@dp.message(Form.clients_count)
async def get_clients_count(message: types.Message, state: FSMContext):
    try:
        clients = int(float(message.text.replace(',', '.')))
        await state.update_data(clients_count=clients)
        
        data = await state.get_data()
        if data.get('edit_mode') == 'revenue':
            await state.update_data(edit_mode=None)
            await show_summary(message, state)
        else:
            await state.set_state(Form.pilot_status)
            await message.answer(
                "✈️ Пилоты и партнёрства\n\n"
                "Были ли новые пилоты с крупными компаниями за последний месяц?",
                reply_markup=get_pilot_keyboard()
            )
    except ValueError:
        await message.answer("Пожалуйста, введите целое число (например: 15)")

@dp.callback_query(lambda c: c.data.startswith('pilot_'))
async def process_pilot(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    if callback.data == "pilot_yes":
        await state.update_data(pilot_status="✅ Да, запустили пилот")
        await state.set_state(Form.pilot_details)
        await callback.message.answer(
            "Расскажите подробно о пилоте:\n\n"
            "1. С какой компанией?\n"
            "2. В чём суть пилота?\n"
            "3. Какие результаты ожидаете?\n\n"
            "Напишите подробно."
        )
    elif callback.data == "pilot_no":
        await state.update_data(pilot_status="❌ Нет, пилотов не было", pilot_details='')
        
        data = await state.get_data()
        if data.get('edit_mode') == 'pilots':
            await state.update_data(edit_mode=None)
            await show_summary(callback.message, state)
        else:
            await state.set_state(Form.other_news)
            await callback.message.answer(
                "📢 Другие новости\n\n"
                "Поделитесь тем, что важно для вас и проекта:\n\n"
                "- технологические обновления (новый продукт, релиз, патент);\n\n"
                "- участие в мероприятиях, награды, партнерства;\n\n"
                "- выход на новые рынки или любые другие достижения;\n\n"
                "- или другие важные новости для проекта.\n\n"
                "Если новостей нет — выберите вариант ниже.",
                reply_markup=get_news_keyboard()
            )

@dp.message(Form.pilot_details)
async def get_pilot_details(message: types.Message, state: FSMContext):
    await state.update_data(pilot_details=message.text)
    
    data = await state.get_data()
    if data.get('edit_mode') == 'pilots':
        await state.update_data(edit_mode=None)
        await show_summary(message, state)
    else:
        await state.set_state(Form.other_news)
        await message.answer(
            "📢 Другие новости\n\n"
            "Поделитесь тем, что важно для вас и проекта:\n\n"
            "- технологические обновления (новый продукт, релиз, патент);\n\n"
            "- участие в мероприятиях, награды, партнерства;\n\n"
            "- выход на новые рынки или любые другие достижения;\n\n"
            "- или другие важные новости для проекта.\n\n"
            "Если новостей нет — выберите вариант ниже.",
            reply_markup=get_news_keyboard()
        )

@dp.callback_query(lambda c: c.data.startswith('news_'))
async def process_news(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    
    if callback.data == "news_share":
        await callback.message.answer(
            "📢 Расскажите, какие новости у вас были за последний месяц:"
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
    if data.get('pilot_details'):
        pilot_text = f"{pilot_text}\n   Детали: {data['pilot_details']}"
    
    text = (
        "📋 Проверьте информацию:\n\n"
        f"📌 Название: {data.get('startup_name', '—')}\n\n"
        f"💼 Инвестиции:\n"
        f"   Статус: {data.get('investment_status', '—')}\n"
        f"   Сумма: {inv_amount} млн ₽\n"
        f"   Источник: {data.get('investment_source', '—')}\n"
        f"   Условия: {data.get('investment_terms', '—')}\n\n"
        f"💰 Финансы:\n"
        f"   Выручка: {revenue} млн ₽\n"
        f"   Клиентов: {data.get('clients_count', 0)}\n\n"
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
            "Что хотите отредактировать?",
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
            "Были ли у вас инвестиции за последний месяц?",
            reply_markup=get_invest_keyboard()
        )
    elif callback.data == "edit_revenue":
        await state.update_data(revenue=0, clients_count=0, edit_mode='revenue')
        await state.set_state(Form.revenue)
        await callback.message.answer(
            "💰 Выручка\n\n"
            "Какая выручка у проекта была за последний месяц?\n\n"
            "Введите сумму в миллионах рублей."
        )
    elif callback.data == "edit_pilots":
        await state.update_data(pilot_status='', pilot_details='', edit_mode='pilots')
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
            "Поделитесь новостями или выберите вариант ниже.",
            reply_markup=get_news_keyboard()
        )
    elif callback.data == "edit_restart":
        await state.clear()
        await cmd_start(callback.message, state)

async def send_to_sheets(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id

    webhook_url = "https://flow.sokt.io/func/scri4EMJW50Q"

    payload = {
        "user_id": user_id,
        "username": data.get('username', ''),
        "first_name": data.get('first_name', ''),
        "last_name": data.get('last_name', ''),
        "startup_name": data.get('startup_name', ''),
        "investment_status": data.get('investment_status', ''),
        "investment_amount": data.get('investment_amount', 0),
        "investment_source": data.get('investment_source', ''),
        "investment_terms": data.get('investment_terms', ''),
        "revenue": data.get('revenue', 0),
        "clients_count": data.get('clients_count', 0),
        "pilot_status": data.get('pilot_status', ''),
        "pilot_details": data.get('pilot_details', ''),
        "other_news": data.get('other_news', '')
    }

    try:
        response = requests.post(webhook_url, json=payload)
        if response.status_code == 200:
            await message.answer(
                "✅ Готово! Спасибо за информацию, мы получили ваши данные!\nДайджест будет опубликован в сообществе выпускников.",
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

# ---- ЗАПУСК БОТА (для Render Web Service) ----
async def main():
    print("Бот запущен и работает через start_polling!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())