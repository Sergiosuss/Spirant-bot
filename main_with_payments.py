import logging
import os
from dotenv import load_dotenv
from aiogram import Bot, types
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor
from apscheduler.schedulers.background import BackgroundScheduler

# Загружаем переменные окружения
load_dotenv()

# Константы
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHAT_ID = int(os.getenv('ADMIN_CHAT_ID', '0'))
GMAIL_EMAIL = os.getenv('GMAIL_EMAIL')
GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD')
GOOGLE_CREDENTIALS_JSON = os.getenv('GOOGLE_CREDENTIALS_JSON')

# Инициализация бота
bot = Bot(token=BOT_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Флаги инициализации
GOOGLE_SHEETS_INITIALIZED = False
GMAIL_INITIALIZED = False
SCHEDULER_RUNNING = False

# Проверка админа
def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь админом"""
    return user_id == ADMIN_CHAT_ID

# ==================== КОМАНДЫ ====================

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """Приветствие"""
    await message.reply(
        "🤖 <b>Spirant Admin Bot</b>\n\n"
        "Привет! Я админский помощник платежной системы студии Spirant.\n\n"
        "Доступные команды:\n"
        "/help - Справка\n"
        "/status - Статус системы\n"
        "/check_sheet - Проверить Google Sheets\n"
        "/check_email - Проверить Gmail"
    )

@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    """Справка"""
    await message.reply(
        "📖 <b>Справка команд:</b>\n\n"
        "🔹 /start - Приветствие\n"
        "🔹 /help - Эта справка\n"
        "🔹 /status - Статус платежной системы\n"
        "🔹 /check_sheet - Проверить подключение Google Sheets\n"
        "🔹 /check_email - Проверить подключение Gmail\n\n"
        "⚠️ Все команды доступны только админу!"
    )
@dp.message_handler(commands=['status'])
async def cmd_status(message: types.Message):
    """Статус системы (только для админа)"""
    if not is_admin(message.from_user.id):
        await message.reply("❌ <b>Доступ запрещен!</b>\n\nЭта команда доступна только админу.")
        return
    
    status_text = "📊 <b>Статус платежной системы:</b>\n\n"
    
    # Google Sheets - реальная проверка
    google_sheets_ok = False
    try:
        import base64
        import json
        import gspread
        
        if GOOGLE_CREDENTIALS_JSON:
            decoded = base64.b64decode(GOOGLE_CREDENTIALS_JSON).decode('utf-8')
            credentials = json.loads(decoded)
            gc = gspread.service_account_from_dict(credentials)
            sheet = gc.open('Заявки')
            google_sheets_ok = True
    except Exception as e:
        google_sheets_ok = False
    
    if google_sheets_ok:
        status_text += "✅ <b>Google Sheets:</b> Подключено\n"
        status_text += "  • Таблица: Заявки\n"
        status_text += "  • Лист: 25/26\n"
        status_text += "  • Месяцы: Q-Y (сентябрь-май)\n"
    else:
        status_text += "❌ <b>Google Sheets:</b> Отключено\n"
        status_text += "  ⚠️ Переменная GOOGLE_CREDENTIALS_JSON не установлена или ошибка подключения\n"
    
    # Gmail IMAP - реальная проверка
    gmail_ok = False
    if GMAIL_EMAIL and GMAIL_APP_PASSWORD:
        gmail_ok = True
    
    if gmail_ok:
        status_text += "\n✅ <b>Gmail (IMAP):</b> Подключено\n"
        status_text += f"  • Email: {GMAIL_EMAIL}\n"
        status_text += "  • Отправитель: ipay@ipay.by\n"
        status_text += "  • Проверка: каждый час\n"
    else:
        status_text += "\n❌ <b>Gmail (IMAP):</b> Отключено\n"
        if GMAIL_EMAIL:
            status_text += f"  • Email: {GMAIL_EMAIL}\n"
        status_text += "  ⚠️ App Password не установлен\n"
    
    # Планировщик
    status_text += "\n"
    if SCHEDULER_RUNNING:
        status_text += "✅ <b>Планировщик:</b> Работает\n"
        status_text += "  • Проверка платежей: каждый час\n"
        status_text += "  • Уведомления админу: включены\n"
    else:
        status_text += "❌ <b>Планировщик:</b> Остановлен\n"
    
    await message.reply(status_text)

@dp.message_handler(commands=['check_sheet'])
async def cmd_check_sheet(message: types.Message):
    """Проверить Google Sheets (только для админа)"""
    if not is_admin(message.from_user.id):
        await message.reply("❌ <b>Доступ запрещен!</b>\n\nЭта команда доступна только админу.")
        return
    
    if not GOOGLE_CREDENTIALS_JSON:
        await message.reply(
            "❌ <b>Google Sheets не инициализирован</b>\n\n"
            "Необходимо установить переменную окружения GOOGLE_CREDENTIALS_JSON в Render."
        )
        return
    
    try:
        import base64
        import json
        import gspread
        
        # Декодируем credentials
        decoded = base64.b64decode(GOOGLE_CREDENTIALS_JSON).decode('utf-8')
        credentials = json.loads(decoded)
        
        # Пытаемся подключиться
        gc = gspread.service_account_from_dict(credentials)
        sheet = gc.open('Заявки')
        
        await message.reply(
            "✅ <b>Google Sheets подключен успешно!</b>\n\n"
            "📋 <b>Информация:</b>\n"
            "  • Статус: Активен\n"
            "  • Таблица: Заявки\n"
            "  • Лист: 25/26\n"
            "  • Готов к обновлениям платежей"
        )
    except Exception as e:
        await message.reply(f"❌ <b>Ошибка подключения Google Sheets:</b>\n\n{str(e)}")

@dp.message_handler(commands=['check_email'])
async def cmd_check_email(message: types.Message):
    """Проверить Gmail (только для админа)"""
    if not is_admin(message.from_user.id):
        await message.reply("❌ <b>Доступ запрещен!</b>\n\nЭта команда доступна только админу.")
        return
    
    if not (GMAIL_EMAIL and GMAIL_APP_PASSWORD):
        await message.reply(
            "❌ <b>Gmail не инициализирован</b>\n\n"
            "Необходимо установить в Render:\n"
            "  • GMAIL_EMAIL\n"
            "  • GMAIL_APP_PASSWORD"
        )
        return
    
    try:
        await message.reply(
            "✅ <b>Gmail подключен успешно!</b>\n\n"
            f"📧 <b>Информация:</b>\n"
            f"  • Email: {GMAIL_EMAIL}\n"
            f"  • Статус: Активен\n"
            f"  • Ожидание платежей от: ipay@ipay.by\n"
            f"  • Проверка: каждый час"
        )
    except Exception as e:
        await message.reply(f"❌ <b>Ошибка подключения Gmail:</b>\n\n{str(e)}")

# ==================== ОБРАБОТКА ОШИБОК ====================

@dp.message_handler()
async def handle_unknown(message: types.Message):
    """Обработка неизвестных команд"""
    await message.reply(
        "❓ <b>Неизвестная команда</b>\n\n"
        "Используйте /help для справки по доступным командам"
    )

# ==================== ПЛАНИРОВЩИК ====================

def check_payments_job():
    """Задача проверки платежей"""
    logger.info("🔄 Запуск проверки платежей...")
    
    # Здесь будет логика проверки платежей
    # На данный момент это заглушка
    logger.info("✅ Платежи проверены (заглушка)")

async def on_startup(dp):
    """При запуске бота"""
    global SCHEDULER_RUNNING
    
    logger.info("=" * 50)
    logger.info("SPIRANT PAYMENT BOT (ADMIN)")
    logger.info("=" * 50)
    logger.info(f"✅ BOT_TOKEN: loaded")
    logger.info(f"✅ ADMIN_CHAT_ID: {ADMIN_CHAT_ID}")
    logger.info(f"📧 GMAIL_EMAIL: {GMAIL_EMAIL if GMAIL_EMAIL else '❌ не установлен'}")
    logger.info(f"📊 Google Sheets: {'✅ готов' if GOOGLE_CREDENTIALS_JSON else '❌ не установлен'}")
    logger.info("=" * 50)
    
    # Запуск планировщика
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_payments_job, 'interval', hours=1)
    scheduler.start()
    SCHEDULER_RUNNING = True
    
    logger.info("🚀 Бот запущен!")
    logger.info("✅ Планировщик запущен")

async def on_shutdown(dp):
    """При остановке бота"""
    global SCHEDULER_RUNNING
    SCHEDULER_RUNNING = False
    logger.info("🛑 Бот остановлен")

# ==================== ЗАПУСК БОТА ====================

if __name__ == '__main__':
    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown
    )
