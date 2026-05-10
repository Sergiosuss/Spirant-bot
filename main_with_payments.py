"""
Spirant Bot - MAIN.PY с полной интеграцией платежной системы
Пример использования для бота на aiogram
"""

import os
import logging
from typing import Dict, Any

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from dotenv import load_dotenv

# Импортируем наши модули
from spirant_payment_processor_final import SpeerantPaymentProcessor
from email_payment_reader import GmailPaymentReader, PaymentScheduler

# Загружаем переменные окружения
load_dotenv()

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== КОНФИГУРАЦИЯ ==========

# Telegram
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CHAT_ID = int(os.getenv('ADMIN_CHAT_ID', '0'))

# Gmail
GMAIL_EMAIL = os.getenv('GMAIL_EMAIL', 'zhmykhtv@gmail.com')
GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD')  # ← App Password, не обычный пароль!

# Google Sheets
GOOGLE_CREDENTIALS_FILE = os.getenv('GOOGLE_CREDENTIALS_FILE', 'google_creds.json')

# ========== ИНИЦИАЛИЗАЦИЯ ==========

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Глобальные переменные для платежной системы
payment_processor: SpeerantPaymentProcessor = None
payment_scheduler: PaymentScheduler = None


# ========== ЗАГРУЗКА GOOGLE CREDENTIALS ==========

def load_google_credentials() -> Dict[str, Any]:
    """Загружает учетные данные Google из файла"""
    import json
    try:
        with open(GOOGLE_CREDENTIALS_FILE, 'r') as f:
            creds = json.load(f)
        logger.info(f"✅ Загружены Google credentials из {GOOGLE_CREDENTIALS_FILE}")
        return creds
    except FileNotFoundError:
        logger.error(f"❌ Файл {GOOGLE_CREDENTIALS_FILE} не найден!")
        logger.error("💡 Скачай credentials с console.cloud.google.com и сохрани как google_creds.json")
        return {}
    except json.JSONDecodeError:
        logger.error(f"❌ Ошибка парсинга {GOOGLE_CREDENTIALS_FILE}")
        return {}


# ========== ОБРАБОТЧИКИ КОМАНД ==========

@dp.message_handler(commands=['start', 'help'])
async def cmd_start(message: types.Message):
    """Справка по боту"""
    text = """
🎭 <b>Spirant Telegram Bot</b>

<b>Доступные команды:</b>
/status - Статус платежной системы
/sync_payments - Ручная синхронизация платежей
/check_sheet - Проверить подключение к Google Sheets
/check_email - Проверить подключение к Gmail

<b>📊 Автоматизация:</b>
✅ Платежи проверяются автоматически каждый час
✅ Google Sheets обновляется при поступлении платежей
✅ Админ получает уведомления о каждом платеже
    """
    await message.reply(text, parse_mode='HTML')


@dp.message_handler(commands=['status'])
async def cmd_status(message: types.Message):
    """Статус системы"""
    # Проверяем компоненты
    sheets_ok = payment_processor and payment_processor.sheet is not None
    email_ok = payment_scheduler is not None
    
    status_text = f"""
📊 <b>Статус платежной системы:</b>

🔗 Google Sheets: {'✅ Подключено' if sheets_ok else '❌ Отключено'}
   • Таблица: Заявки
   • Лист: 25/26
   • Месяцы: Q-Y (сентябрь-май)

📧 Gmail (IMAP): {'✅ Готов' if email_ok else '❌ Отключен'}
   • Email: {GMAIL_EMAIL}
   • Отправитель: ipay@ipay.by
   • Проверка: каждый час

🤖 Планировщик: {'✅ Работает' if payment_scheduler and payment_scheduler.scheduler else '❌ Остановлен'}
    """
    await message.reply(status_text, parse_mode='HTML')


@dp.message_handler(commands=['sync_payments'])
async def cmd_sync_payments(message: types.Message):
    """Ручная синхронизация платежей"""
    if not payment_scheduler:
        await message.reply("❌ Платежная система не инициализирована!")
        return
    
    await message.reply("🔄 Запущена ручная проверка платежей...")
    
    try:
        count = await payment_scheduler.email_reader.process_all_payments()
        await message.reply(
            f"✅ Проверка завершена!\n"
            f"📊 Обработано платежей: {count}",
            parse_mode='HTML'
        )
    except Exception as e:
        await message.reply(
            f"❌ Ошибка при проверке платежей:\n<code>{str(e)}</code>",
            parse_mode='HTML'
        )


@dp.message_handler(commands=['check_sheet'])
async def cmd_check_sheet(message: types.Message):
    """Проверка подключения к Google Sheets"""
    if not payment_processor:
        await message.reply("❌ Процессор платежей не инициализирован!")
        return
    
    if not payment_processor.sheet:
        await message.reply("❌ Не подключено к Google Sheets")
        return
    
    try:
        # Проверяем подключение
        title = payment_processor.sheet.title
        rows = len(payment_processor.sheet.get_all_values())
        
        await message.reply(
            f"✅ <b>Подключено к Google Sheets</b>\n\n"
            f"📄 Таблица: {payment_processor.SPREADSHEET_NAME}\n"
            f"📋 Лист: {title}\n"
            f"📊 Строк данных: {rows}",
            parse_mode='HTML'
        )
    except Exception as e:
        await message.reply(
            f"❌ Ошибка подключения:\n<code>{str(e)}</code>",
            parse_mode='HTML'
        )


@dp.message_handler(commands=['check_email'])
async def cmd_check_email(message: types.Message):
    """Проверка подключения к Gmail"""
    if not payment_scheduler:
        await message.reply("❌ Планировщик платежей не инициализирован!")
        return
    
    email_reader = payment_scheduler.email_reader
    
    await message.reply("🔄 Проверка подключения к Gmail...")
    
    if email_reader.connect():
        try:
            payments = email_reader.find_payment_attachments()
            await message.reply(
                f"✅ <b>Подключено к Gmail IMAP</b>\n\n"
                f"📧 Email: {email_reader.email}\n"
                f"📥 Непрочитанных платежей: {len(payments)}",
                parse_mode='HTML'
            )
        except Exception as e:
            await message.reply(
                f"⚠️ Подключено, но ошибка при проверке платежей:\n<code>{str(e)}</code>",
                parse_mode='HTML'
            )
        finally:
            email_reader.disconnect()
    else:
        await message.reply(
            f"❌ Ошибка подключения к Gmail\n"
            f"💡 Убедитесь что используете App Password, не обычный пароль!",
            parse_mode='HTML'
        )


# ========== ФОНОВЫЕ ЗАДАЧИ ==========

async def on_startup(dispatcher):
    """Выполняется при запуске бота"""
    global payment_processor, payment_scheduler
    
    logger.info("=" * 60)
    logger.info("🚀 Запуск Spirant Bot")
    logger.info("=" * 60)
    
    # 1️⃣ Инициализация Google Sheets процессора
    logger.info("\n📊 Инициализация Google Sheets...")
    google_creds = load_google_credentials()
    
    if not google_creds:
        logger.error("❌ Не удалось загрузить Google credentials")
    else:
        payment_processor = SpeerantPaymentProcessor(
            google_creds_dict=google_creds,
            bot=bot,
            admin_chat_id=ADMIN_CHAT_ID
        )
        
        if payment_processor.connect_to_sheet():
            logger.info("✅ Google Sheets инициализирована")
        else:
            logger.error("❌ Ошибка подключения к Google Sheets")
    
    # 2️⃣ Инициализация Email читателя и планировщика
    logger.info("\n📧 Инициализация Email платежной системы...")
    
    if not GMAIL_APP_PASSWORD:
        logger.error("❌ Не установлена переменная GMAIL_APP_PASSWORD")
        logger.error("💡 Добавь в .env: GMAIL_APP_PASSWORD=твой_app_password")
    else:
        email_reader = GmailPaymentReader(
            email_address=GMAIL_EMAIL,
            app_password=GMAIL_APP_PASSWORD,
            bot=bot,
            admin_chat_id=ADMIN_CHAT_ID
        )
        
        if payment_processor:
            payment_scheduler = PaymentScheduler(email_reader, payment_processor)
            payment_scheduler.start()
            logger.info("✅ Планировщик платежей запущен")
            logger.info("⏰ Проверка раз в час")
        else:
            logger.error("❌ Payment processor не инициализирован, пропускаем планировщик")
    
    # 3️⃣ Отправляем уведомление админу
    try:
        await bot.send_message(
            ADMIN_CHAT_ID,
            "✅ <b>Spirant Bot запущен!</b>\n\n"
            "📊 Платежная система активирована\n"
            "⏰ Проверка платежей: каждый час\n\n"
            "Используй /help для списка команд",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.warning(f"⚠️ Не удалось отправить уведомление админу: {e}")
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ Бот полностью инициализирован")
    logger.info("=" * 60 + "\n")


async def on_shutdown(dispatcher):
    """Выполняется при остановке бота"""
    logger.info("\n" + "=" * 60)
    logger.info("🛑 Остановка Spirant Bot")
    logger.info("=" * 60)
    
    # Останавливаем планировщик
    if payment_scheduler:
        payment_scheduler.stop()
        logger.info("✅ Планировщик остановлен")
    
    # Отправляем уведомление админу
    try:
        await bot.send_message(
            ADMIN_CHAT_ID,
            "🛑 Spirant Bot остановлен",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.warning(f"⚠️ Не удалось отправить уведомление: {e}")
    
    logger.info("✅ Бот остановлен")
    logger.info("=" * 60 + "\n")


# ========== ЗАПУСК БОТА ==========

if __name__ == '__main__':
    executor.start_polling(
        dp,
        skip_updates=True
    )
