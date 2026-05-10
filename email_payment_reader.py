"""
Spirant Bot - Email Payment Reader
Автоматическое чтение платежей из Gmail от ipay@ipay.by
Проверка: раз в час через APScheduler
"""

import imaplib
import email
from email.mime.text import MIMEText
import logging
from typing import List, Dict, Optional
from datetime import datetime
import re

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GmailPaymentReader:
    """Чтение платежей из Gmail IMAP"""
    
    # Константы Gmail
    GMAIL_IMAP = "imap.gmail.com"
    GMAIL_IMAP_PORT = 993
    
    # Email отправителя платежей
    PAYMENT_SENDER = "ipay@ipay.by"
    
    # Параметры подключения
    EMAIL = "zhmykhtv@gmail.com"
    # PASSWORD = "тут ставить пароль/app-пароль"
    
    def __init__(self, email_address: str, app_password: str, bot=None, admin_chat_id: int = None):
        """
        Инициализация читателя email
        
        Args:
            email_address: Email для подключения (zhmykhtv@gmail.com)
            app_password: App Password от Google (не обычный пароль!)
            bot: aiogram bot для уведомлений
            admin_chat_id: ID чата админа
        """
        self.email = email_address
        self.password = app_password
        self.bot = bot
        self.admin_chat_id = admin_chat_id
        self.mail = None
        self.payment_processor = None  # Будет установлена зависимость
    
    def connect(self) -> bool:
        """Подключение к Gmail IMAP"""
        try:
            self.mail = imaplib.IMAP4_SSL(self.GMAIL_IMAP, self.GMAIL_IMAP_PORT)
            self.mail.login(self.email, self.password)
            logger.info(f"✅ Подключено к Gmail IMAP как {self.email}")
            return True
        except imaplib.IMAP4.error as e:
            logger.error(f"❌ Ошибка подключения IMAP: {e}")
            logger.error("💡 Убедитесь что используете App Password, не обычный пароль Gmail!")
            return False
        except Exception as e:
            logger.error(f"❌ Неизвестная ошибка подключения: {e}")
            return False
    
    def disconnect(self):
        """Отключение от Gmail"""
        if self.mail:
            try:
                self.mail.close()
                self.mail.logout()
                logger.info("✅ Отключено от Gmail IMAP")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при отключении: {e}")
    
    def find_payment_attachments(self) -> List[Dict]:
        """
        Ищет непрочитанные письма от ipay@ipay.by с TXT вложениями
        
        Returns:
            Список словарей с информацией о файлах платежей
        """
        try:
            # Выбираем папку INBOX
            self.mail.select("INBOX")
            
            # Ищем непрочитанные письма от ipay@ipay.by
            status, message_ids = self.mail.search(
                None,
                f'UNSEEN FROM "{self.PAYMENT_SENDER}"'
            )
            
            if status != "OK":
                logger.warning(f"⚠️ Ошибка поиска писем: {status}")
                return []
            
            message_list = message_ids[0].split()
            if not message_list:
                logger.info(f"ℹ️ Новых платежей от {self.PAYMENT_SENDER} не найдено")
                return []
            
            logger.info(f"📧 Найдено {len(message_list)} писем от {self.PAYMENT_SENDER}")
            
            payments = []
            
            for msg_id in message_list:
                try:
                    status, msg_data = self.mail.fetch(msg_id, "(RFC822)")
                    
                    if status != "OK":
                        logger.warning(f"⚠️ Ошибка получения письма {msg_id}")
                        continue
                    
                    email_message = email.message_from_bytes(msg_data[0][1])
                    
                    # Ищем TXT вложения
                    for part in email_message.walk():
                        if part.get_content_disposition() == "attachment":
                            filename = part.get_filename()
                            
                            if filename and filename.endswith('.txt'):
                                try:
                                    # Декодируем содержимое файла
                                    file_content = part.get_payload(decode=True)
                                    
                                    # Пробуем разные кодировки
                                    for encoding in ['cp1251', 'utf-8', 'iso-8859-1']:
                                        try:
                                            text_content = file_content.decode(encoding)
                                            break
                                        except UnicodeDecodeError:
                                            continue
                                    else:
                                        logger.warning(f"⚠️ Не удалось декодировать {filename}")
                                        continue
                                    
                                    payments.append({
                                        'filename': filename,
                                        'content': text_content,
                                        'msg_id': msg_id,
                                        'subject': email_message.get('Subject', ''),
                                        'date': email_message.get('Date', ''),
                                    })
                                    
                                    logger.info(f"✅ Прочитан файл платежа: {filename}")
                                
                                except Exception as e:
                                    logger.error(f"❌ Ошибка чтения вложения {filename}: {e}")
                
                except Exception as e:
                    logger.error(f"❌ Ошибка обработки письма {msg_id}: {e}")
            
            return payments
        
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при поиске платежей: {e}")
            return []
    
    def mark_as_read(self, msg_id: bytes) -> bool:
        """Отмечает письмо как прочитанное"""
        try:
            self.mail.store(msg_id, '+FLAGS', '\\Seen')
            return True
        except Exception as e:
            logger.warning(f"⚠️ Не удалось отметить письмо {msg_id} как прочитанное: {e}")
            return False
    
    async def process_all_payments(self) -> int:
        """
        Обрабатывает все найденные платежи
        
        Returns:
            Количество успешно обработанных платежей
        """
        if not self.payment_processor:
            logger.error("❌ Payment processor не установлен!")
            return 0
        
        # Подключаемся к Gmail
        if not self.connect():
            return 0
        
        try:
            # Ищем платежи
            payments = self.find_payment_attachments()
            
            if not payments:
                logger.info("ℹ️ Нечего обрабатывать")
                return 0
            
            processed_count = 0
            
            # Обрабатываем каждый платеж
            for payment_info in payments:
                try:
                    # Парсим файл
                    payment_data = self.payment_processor.parse_payment_file(
                        payment_info['content']
                    )
                    
                    if not payment_data.get('contract'):
                        logger.warning(f"⚠️ Не удалось парсить платеж из {payment_info['filename']}")
                        continue
                    
                    # Обновляем платеж в Google Sheets
                    success = await self.payment_processor.process_payment(payment_data)
                    
                    if success:
                        # Отмечаем письмо как прочитанное
                        self.mark_as_read(payment_info['msg_id'])
                        processed_count += 1
                        
                        logger.info(f"✅ Платеж обработан: {payment_data.get('contract')}")
                    else:
                        logger.warning(f"⚠️ Ошибка при обновлении платежа {payment_data.get('contract')}")
                
                except Exception as e:
                    logger.error(f"❌ Ошибка обработки платежа: {e}")
            
            return processed_count
        
        finally:
            self.disconnect()


class PaymentScheduler:
    """Планировщик автоматической проверки платежей"""
    
    def __init__(self, email_reader: GmailPaymentReader, payment_processor):
        """
        Инициализация планировщика
        
        Args:
            email_reader: Экземпляр GmailPaymentReader
            payment_processor: Экземпляр SpeerantPaymentProcessor
        """
        self.email_reader = email_reader
        self.email_reader.payment_processor = payment_processor
        self.scheduler = None
    
    async def check_payments(self):
        """Запускается раз в час для проверки платежей"""
        logger.info("=" * 60)
        logger.info(f"🔄 Проверка платежей в {datetime.now().strftime('%H:%M:%S')}")
        logger.info("=" * 60)
        
        try:
            count = await self.email_reader.process_all_payments()
            logger.info(f"✅ Обработано платежей: {count}")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при проверке платежей: {e}")
        
        logger.info("=" * 60)
    
    def start(self):
        """Запуск планировщика"""
        try:
            self.scheduler = AsyncIOScheduler()
            
            # Проверка раз в час (на 0-й минуте каждого часа)
            self.scheduler.add_job(
                self.check_payments,
                trigger=IntervalTrigger(hours=1),
                id="payment_checker",
                name="Проверка платежей каждый час",
                replace_existing=True
            )
            
            self.scheduler.start()
            logger.info("✅ Планировщик платежей запущен")
            logger.info("⏰ Проверка раз в час")
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска планировщика: {e}")
    
    def stop(self):
        """Остановка планировщика"""
        if self.scheduler:
            try:
                self.scheduler.shutdown()
                logger.info("✅ Планировщик остановлен")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при остановке планировщика: {e}")


# ========== ИНТЕГРАЦИЯ В MAIN.PY ==========

"""
# В main.py:

from email_payment_reader import GmailPaymentReader, PaymentScheduler
from payment_processor import SpeerantPaymentProcessor
import os

# Инициализация при запуске бота:

async def on_startup():
    # Google Sheets процессор
    payment_processor = SpeerantPaymentProcessor(
        google_creds_dict=GOOGLE_SERVICE_ACCOUNT_CREDS,
        bot=bot,
        admin_chat_id=ADMIN_CHAT_ID
    )
    payment_processor.connect_to_sheet()
    
    # Gmail читатель
    email_reader = GmailPaymentReader(
        email_address="zhmykhtv@gmail.com",
        app_password=os.getenv('GMAIL_APP_PASSWORD'),
        bot=bot,
        admin_chat_id=ADMIN_CHAT_ID
    )
    
    # Планировщик
    scheduler = PaymentScheduler(email_reader, payment_processor)
    scheduler.start()
    
    # Сохраняем в app.middleware или глобальный контекст
    return scheduler


# При остановке бота:

async def on_shutdown(scheduler):
    scheduler.stop()
"""


# ========== ТЕСТИРОВАНИЕ ==========

if __name__ == "__main__":
    import asyncio
    
    # ⚠️ ВАЖНО: Замени на свой App Password!
    EMAIL = "zhmykhtv@gmail.com"
    APP_PASSWORD = "твой_app_password_здесь"
    
    reader = GmailPaymentReader(EMAIL, APP_PASSWORD)
    
    # Тест подключения
    if reader.connect():
        print("✅ Подключение успешно!")
        
        # Тест поиска платежей (без обработки)
        # payments = reader.find_payment_attachments()
        # print(f"Найдено {len(payments)} платежей")
        
        reader.disconnect()
    else:
        print("❌ Ошибка подключения")
        print("💡 Используй App Password, не обычный пароль Gmail!")
