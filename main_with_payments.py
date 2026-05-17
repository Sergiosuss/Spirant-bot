import logging
import os
import json
import base64
from typing import Dict, Any
from dotenv import load_dotenv
from aiogram import Bot, types
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Импортируем модули
from email_reader import EmailPaymentReader
from payment_processor import SpeerantPaymentProcessor

# Загружаем переменные окружения
load_dotenv()

# Константы
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHAT_ID = int(os.getenv('ADMIN_CHAT_ID', '0'))
GMAIL_EMAIL = os.getenv('GMAIL_EMAIL')
GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD')
GOOGLE_CREDENTIALS_FILE = 'google_creds.json'

# Инициализация бота
bot = Bot(token=BOT_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Флаги инициализации
EMAIL_READER = None
PAYMENT_PROCESSOR = None
SCHEDULER_RUNNING = False

# ==================== ЗАГРУЗКА GOOGLE CREDENTIALS ====================

def load_google_credentials() -> Dict[str, Any]:
    """Загружает учетные данные Google из переменной окружения или файла"""
    
    # СПОСОБ 1: Из переменной окружения (Render.com)
    creds_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
    if creds_json:
        try:
            logger.info("📝 Читаю GOOGLE_CREDENTIALS_JSON из переменной окружения...")
            
            # Пробуем декодировать как base64
            try:
                decoded = base64.b64decode(creds_json)
                creds = json.loads(decoded.decode('utf-8'))
                logger.info("✅ Успешно декодирован base64 JSON")
            except:
                # Если не base64, пробуем парсить как обычный JSON
                creds = json.loads(creds_json)
                logger.info("✅ Успешно распарсен JSON")
            
            # Сохраняем в файл для дальнейшего использования
            with open(GOOGLE_CREDENTIALS_FILE, 'w') as f:
                json.dump(creds, f)
            logger.info("✅ Сохранён google_creds.json")
            
            return creds
        
        except Exception as e:
            logger.error(f"❌ Ошибка обработки GOOGLE_CREDENTIALS_JSON: {e}")
            return {}
    
    # СПОСОБ 2: Из файла (локальная разработка)
    try:
        with open(GOOGLE_CREDENTIALS_FILE, 'r') as f:
            creds = json.load(f)
        logger.info(f"✅ Загружены Google credentials из {GOOGLE_CREDENTIALS_FILE}")
        return creds
    except FileNotFoundError:
        logger.error(f"❌ Файл {GOOGLE_CREDENTIALS_FILE} не найден!")
        logger.error("❌ Переменная GOOGLE_CREDENTIALS_JSON тоже не установлена!")
        logger.error("💡 На Render добавьте переменную окружения GOOGLE_CREDENTIALS_JSON")
        return {}
    except json.JSONDecodeError:
        logger.error(f"❌ Ошибка парсинга {GOOGLE_CREDENTIALS_FILE}")
        return {}

# ==================== ПРОВЕРКА АДМИНА ====================

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь админом"""
    return user_id == ADMIN_CHAT_ID

# ==================== ИНИЦИАЛИЗАЦИЯ МОДУЛЕЙ ====================

def init_modules():
    """Инициализирует email reader и payment processor"""
    global EMAIL_READER, PAYMENT_PROCESSOR
    
    try:
        if GMAIL_EMAIL and GMAIL_APP_PASSWORD:
            EMAIL_READER = EmailPaymentReader(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
            logger.info("✅ Email Reader инициализирован")
        else:
            logger.warning("⚠️ Email Reader не инициализирован (отсутствуют учётные данные)")
    except Exception as e:
        logger.warning(f"⚠️ Email Reader ошибка: {e}")
    
    try:
        google_creds = load_google_credentials()
        
        if not google_creds:
            logger.error("❌ Google credentials не загружены!")
            return
        
        PAYMENT_PROCESSOR = SpeerantPaymentProcessor(
            google_creds_dict=google_creds,
            bot=bot,
            admin_chat_id=ADMIN_CHAT_ID
        )
        
        if PAYMENT_PROCESSOR.connect_to_sheet():
            logger.info("✅ Payment Processor инициализирован и подключен к Google Sheets")
        else:
            logger.error("❌ Payment Processor не смог подключиться к Google Sheets")
            PAYMENT_PROCESSOR = None
    
    except Exception as e:
        logger.error(f"❌ Payment Processor ошибка: {e}")
        PAYMENT_PROCESSOR = None

# ==================== КОМАНДЫ ====================

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """Приветствие"""
    await message.reply(
        "🤖 <b>Spirant Payment Bot</b>\n\n"
        "Привет! Я админский помощник платежной системы студии Spirant.\n\n"
        "Доступные команды:\n"
        "/help - Справка\n"
        "/status - Статус системы\n"
        "/check_sheet - Проверить Google Sheets\n"
        "/check_email - Проверить Gmail\n"
        "/sync - Проверить платежи вручную"
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
        "🔹 /check_email - Проверить подключение Gmail\n"
        "🔹 /sync - Проверить платежи вручную (красным в таблице)\n\n"
        "⚠️ Все команды доступны только админу!"
    )

@dp.message_handler(commands=['status'])
async def cmd_status(message: types.Message):
    """Статус системы"""
    if not is_admin(message.from_user.id):
        await message.reply("❌ <b>Доступ запрещен!</b>\n\nЭта команда доступна только админу.")
        return
    
    status_text = "📊 <b>Статус платежной системы:</b>\n\n"
    
    # Google Sheets
    if PAYMENT_PROCESSOR and PAYMENT_PROCESSOR.sheet:
        status_text += "✅ <b>Google Sheets:</b> Подключено\n"
        status_text += "  • Таблица: Заявки\n"
        status_text += "  • Лист: 25/26\n"
        status_text += "  • Месяцы: Q-Y (сентябрь-май)\n"
    else:
        status_text += "❌ <b>Google Sheets:</b> Отключено\n"
    
    # Gmail IMAP
    if EMAIL_READER:
        status_text += "\n✅ <b>Gmail (IMAP):</b> Подключено\n"
        status_text += f"  • Email: {GMAIL_EMAIL}\n"
        status_text += "  • Отправитель: ipay@ipay.by\n"
        status_text += "  • Проверка: каждый час\n"
    else:
        status_text += "\n❌ <b>Gmail (IMAP):</b> Отключено\n"
    
    # Планировщик
    status_text += "\n"
    if SCHEDULER_RUNNING:
        status_text += "✅ <b>Планировщик:</b> Работает\n"
        status_text += "  • Проверка платежей: каждый час\n"
        status_text += "  • Уведомления админу: включены\n"
        status_text += "  • Цвет платежей: 🔴 красный\n"
    else:
        status_text += "❌ <b>Планировщик:</b> Остановлен\n"
    
    await message.reply(status_text)

@dp.message_handler(commands=['check_sheet'])
async def cmd_check_sheet(message: types.Message):
    """Проверить Google Sheets"""
    if not is_admin(message.from_user.id):
        await message.reply("❌ <b>Доступ запрещен!</b>")
        return
    
    if not PAYMENT_PROCESSOR or not PAYMENT_PROCESSOR.sheet:
        await message.reply("❌ <b>Google Sheets не инициализирован</b>")
        return
    
    try:
        await message.reply(
            "✅ <b>Google Sheets подключен успешно!</b>\n\n"
            "📋 <b>Информация:</b>\n"
            "  • Статус: Активен\n"
            "  • Таблица: Заявки\n"
            "  • Лист: 25/26\n"
            "  • Готов к обновлениям платежей\n"
            "  • Цвет платежей: 🔴 красный"
        )
    except Exception as e:
        await message.reply(f"❌ <b>Ошибка:</b> {str(e)}")

@dp.message_handler(commands=['check_email'])
async def cmd_check_email(message: types.Message):
    """Проверить Gmail"""
    if not is_admin(message.from_user.id):
        await message.reply("❌ <b>Доступ запрещен!</b>")
        return
    
    if not EMAIL_READER:
        await message.reply("❌ <b>Gmail не инициализирован</b>")
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
        await message.reply(f"❌ <b>Ошибка:</b> {str(e)}")

@dp.message_handler(commands=['sync'])
async def cmd_sync(message: types.Message):
    """Проверить платежи вручную"""
    if not is_admin(message.from_user.id):
        await message.reply("❌ <b>Доступ запрещен!</b>")
        return
    
    if not EMAIL_READER or not PAYMENT_PROCESSOR:
        await message.reply("❌ <b>Система не готова к синхронизации</b>")
        return
    
    await message.reply("⏳ Проверяю платежи...")
    
    try:
        # Получаем новые платежи
        payments = EMAIL_READER.get_new_payments()
        
        if not payments:
            await message.reply("✅ Новых платежей не найдено")
            return
        
        # Обрабатываем платежи (будут красными)
        result = PAYMENT_PROCESSOR.process_payments(payments)
        
        # Отправляем результат
        response = f"✅ <b>Синхронизация завершена!</b>\n\n"
        response += f"📊 <b>Результаты:</b>\n"
        response += f"  • Всего: {result['successful'] + result['failed']}\n"
        response += f"  • Успешно: {result['successful']} ✅\n"
        response += f"  • Ошибок: {result['failed']} ❌\n\n"
        response += "🔴 Все платежи написаны <b>красным цветом</b>\n"
        
        await message.reply(response)
    
    except Exception as e:
        logger.error(f"❌ Ошибка синхронизации: {e}")
        await message.reply(f"❌ <b>Ошибка:</b> {str(e)}")

@dp.message_handler()
async def handle_unknown(message: types.Message):
    """Обработка неизвестных команд"""
    await message.reply(
        "❓ <b>Неизвестная команда</b>\n\n"
        "Используйте /help для справки"
    )

# ==================== ПЛАНИРОВЩИК ====================

async def check_payments_job():
    """Задача проверки платежей (каждый час)"""
    logger.info("🔄 Начало проверки платежей...")
    
    if not EMAIL_READER or not PAYMENT_PROCESSOR:
        logger.warning("⚠️ Модули не инициализированы")
        return
    
    try:
        # Получаем новые платежи
        payments = EMAIL_READER.get_new_payments()
        
        if not payments:
            logger.info("ℹ️ Новых платежей не найдено")
            return
        
        # Обрабатываем платежи
        result = PAYMENT_PROCESSOR.process_payments(payments)
        
        # Отправляем уведомление админу
        message_text = f"📬 <b>Найдены новые платежи!</b>\n\n"
        message_text += f"✅ Успешно: {result['successful']}\n"
        message_text += f"❌ Ошибок: {result['failed']}\n\n"
        message_text += "🔴 Платежи обновлены <b>красным цветом</b>\n"
        
        await bot.send_message(ADMIN_CHAT_ID, message_text)
        logger.info(f"✅ Платежи обработаны и админ уведомлён")
    
    except Exception as e:
        logger.error(f"❌ Ошибка проверки платежей: {e}")
        try:
            await bot.send_message(ADMIN_CHAT_ID, f"❌ <b>Ошибка проверки платежей:</b>\n{str(e)}")
        except:
            pass

async def on_startup(dp):
    """При запуске бота"""
    global SCHEDULER_RUNNING
    
    logger.info("=" * 60)
    logger.info("🚀 SPIRANT PAYMENT BOT - ЗАПУСК")
    logger.info("=" * 60)
    logger.info(f"✅ BOT_TOKEN: loaded")
    logger.info(f"✅ ADMIN_CHAT_ID: {ADMIN_CHAT_ID}")
    logger.info(f"📧 GMAIL_EMAIL: {GMAIL_EMAIL if GMAIL_EMAIL else '❌'}")
    logger.info("=" * 60)
    
    # Инициализируем модули
    init_modules()
    
    # Запуск планировщика
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_payments_job, 'interval', hours=1)
    scheduler.start()
    SCHEDULER_RUNNING = True
    
    logger.info("✅ Бот запущен!")
    logger.info("✅ Планировщик запущен (проверка каждый час)")
    logger.info("=" * 60)

async def on_shutdown(dp):
    """При остановке бота"""
    global SCHEDULER_RUNNING
    SCHEDULER_RUNNING = False
    logger.info("🛑 Бот остановлен")

# ==================== ЗАПУСК ====================

if __name__ == '__main__':
    executor.start_polling(
        dp,
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown
    )
