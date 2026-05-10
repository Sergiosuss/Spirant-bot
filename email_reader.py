import imaplib
import email
from email.header import decode_header
import logging
import os
import re
from datetime import datetime

logger = logging.getLogger(__name__)

class EmailPaymentReader:
    """Читает платежи из Gmail IMAP"""
    
    def __init__(self, email_addr: str, app_password: str):
        self.email_addr = email_addr
        self.app_password = app_password
        self.imap_server = "imap.gmail.com"
        self.imap_port = 993
        self.processed_emails = set()  # Кэш обработанных писем
    
    def connect(self):
        """Подключается к Gmail IMAP"""
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(self.email_addr, self.app_password)
            logger.info(f"✅ Подключено к Gmail: {self.email_addr}")
            return mail
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Gmail: {e}")
            raise
    
    def decode_email_subject(self, subject):
        """Декодирует тему письма"""
        try:
            if isinstance(subject, bytes):
                subject = subject.decode('utf-8', errors='ignore')
            decoded_parts = decode_header(subject)
            return ''.join([
                part.decode(charset if charset else 'utf-8', errors='ignore') if isinstance(part, bytes) else part
                for part, charset in decoded_parts
            ])
        except:
            return str(subject)
    
    def parse_payment_email(self, email_body: str) -> dict:
        """Парсит письмо с платежом и извлекает данные"""
        try:
            # Парсим формат платежного письма
            data = {}
            
            # Ищем номер договора (ТС22XXX)
            contract_match = re.search(r'Номер договора.*?:\s*(ТС22\d+)', email_body, re.IGNORECASE)
            if contract_match:
                data['contract_number'] = contract_match.group(1).strip()
            
            # Ищем ФИО
            fio_match = re.search(r'ФИО\s*:\s*([А-Яа-яЁё\s]+)', email_body, re.IGNORECASE)
            if fio_match:
                data['fio'] = fio_match.group(1).strip()
            
            # Ищем сумму
            amount_match = re.search(r'Сумма\s*:\s*([\d.]+)', email_body, re.IGNORECASE)
            if amount_match:
                data['amount'] = float(amount_match.group(1).strip())
            
            # Ищем дату платежа
            date_match = re.search(r'Оплачено.*?:\s*(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})', email_body, re.IGNORECASE)
            if date_match:
                data['payment_date'] = date_match.group(1).strip()
            
            # Проверяем что есть критические данные
            if 'contract_number' in data and 'amount' in data:
                logger.info(f"✅ Платёж распарсен: {data['contract_number']} - {data['amount']} руб.")
                return data
            else:
                logger.warning(f"⚠️ Неполные данные платежа: {data}")
                return None
        
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга платежа: {e}")
            return None
    
    def get_new_payments(self) -> list:
        """Получает новые платежи из Gmail"""
        payments = []
        
        try:
            mail = self.connect()
            mail.select('INBOX')
            
            # Ищем письма от ipay@ipay.by
            status, email_ids = mail.search(None, 'FROM', 'zhmykhtv@gmail.com')
            
            if status != 'OK':
                logger.warning("⚠️ Нет писем от ipay@ipay.by")
                mail.close()
                return payments
            
            email_list = email_ids[0].split()
            
            # Обрабатываем последние письма (новые сверху)
            for email_id in reversed(email_list[-10:]):  # Проверяем только последние 10 писем
                # Пропускаем уже обработанные
                if email_id.decode() in self.processed_emails:
                    continue
                
                try:
                    status, msg_data = mail.fetch(email_id, '(RFC822)')
                    
                    if status != 'OK':
                        continue
                    
                    msg = email.message_from_bytes(msg_data[0][1])
                    
                    # Получаем тело письма
                    email_body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                email_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                break
                    else:
                        email_body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                    
                    # Парсим платеж
                    payment = self.parse_payment_email(email_body)
                    
                    if payment:
                        payments.append(payment)
                        self.processed_emails.add(email_id.decode())
                        logger.info(f"✅ Новый платёж найден: {payment['contract_number']}")
                
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка обработки письма: {e}")
                    continue
            
            mail.close()
            
            if payments:
                logger.info(f"✅ Найдено {len(payments)} новых платежей")
            else:
                logger.info("ℹ️ Новых платежей не найдено")
            
            return payments
        
        except Exception as e:
            logger.error(f"❌ Ошибка получения платежей: {e}")
            return payments
