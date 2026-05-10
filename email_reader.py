import imaplib
import email
from email.header import decode_header
import logging
import re

logger = logging.getLogger(__name__)


class EmailPaymentReader:
    """Чтение платежей из Gmail IMAP"""
    
    def __init__(self, email_addr: str, app_password: str):
        self.email = email_addr
        self.app_password = app_password
        self.imap = None
        self.processed_emails = set()
    
    def connect(self) -> bool:
        """Подключение к Gmail IMAP"""
        try:
            logger.info(f"🔗 Подключение к Gmail: {self.email}")
            self.imap = imaplib.IMAP4_SSL("imap.gmail.com")
            self.imap.login(self.email, self.app_password)
            logger.info("✅ Gmail: " + self.email)
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка подключения Gmail: {e}")
            return False
    
    def disconnect(self):
        """Отключение от Gmail"""
        try:
            if self.imap:
                self.imap.close()
                self.imap.logout()
        except:
            pass
    
    def find_payment_attachments(self) -> list:
        """Ищет письма с платежами от ipay@ipay.by"""
        try:
            self.imap.select("INBOX")
            status, messages = self.imap.search(None, 'FROM', 'zhmykhtv@gmail.com')
            
            if status != 'OK':
                return []
            
            email_ids = messages[0].split()
            logger.info(f"📬 Найдено писем от ipay@ipay.by: {len(email_ids)}")
            
            attachments = []
            
            for email_id in email_ids:
                status, msg_data = self.imap.fetch(email_id, '(RFC822)')
                
                if status != 'OK':
                    continue
                
                msg = email.message_from_bytes(msg_data[0][1])
                
                # Проверяем вложения
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_disposition() == 'attachment':
                            filename = part.get_filename()
                            
                            if filename and filename.endswith('.txt'):
                                logger.info(f"📎 Ищу в вложениях...")
                                logger.info(f" 📄 Файл: {filename}")
                                
                                try:
                                    # Пробуем разные кодировки
                                    content = part.get_payload(decode=True)
                                    
                                    for encoding in ['utf-8', 'cp1251', 'windows-1251', 'latin-1', 'iso-8859-5']:
                                        try:
                                            text = content.decode(encoding)
                                            logger.info(f" ✅ Кодировка: {encoding}")
                                            attachments.append(text)
                                            break
                                        except:
                                            continue
                                except Exception as e:
                                    logger.warning(f"⚠️ Ошибка чтения вложения: {e}")
            
            return attachments
        
        except Exception as e:
            logger.error(f"❌ Ошибка поиска вложений: {e}")
            return []
    
    def parse_payment_email(self, email_body: str) -> dict:
        """
        Парсит содержимое платежного письма
        Поддерживает варианты номера договора:
        - ТС22084 (кириллица)
        - TC22084 (латиница)
        - 22084 (только цифры)
        """
        
        payment = {}
        
        # ==================== НОМЕР ДОГОВОРА ====================
        # Ищем любой вариант: ТС, TC или просто цифры
        contract_patterns = [
            r'Номер договора \(заказа\)\s*:\s*([ТTC]+\d+)',  # ТС22084 или TC22084
            r'Номер договора \(заказа\)\s*:\s*(\d+)',         # Только 22084
        ]
        
        contract = None
        for pattern in contract_patterns:
            match = re.search(pattern, email_body)
            if match:
                contract = match.group(1).strip()
                break
        
        if contract:
            # Приводим к стандартному формату ТСxxxx
            contract = contract.upper()
            # Заменяем латинскую C на кириллицу Т
            contract = contract.replace('TC', 'ТС')
            # Если только цифры - добавляем ТС в начало
            if contract.isdigit():
                contract = 'ТС' + contract
            payment['contract'] = contract
        
        # ==================== ФИО ====================
        fio_pattern = r'ФИО\s*:\s*([А-Яа-я\s]+?)(?:\n|$)'
        fio_match = re.search(fio_pattern, email_body)
        if fio_match:
            payment['fio'] = fio_match.group(1).strip()
        
        # ==================== СУММА ====================
        amount_pattern = r'Сумма\s*:\s*([\d.]+)'
        amount_match = re.search(amount_pattern, email_body)
        if amount_match:
            payment['amount'] = amount_match.group(1).strip()
        
        # ==================== ДАТА ====================
        date_pattern = r'Оплачено \(дата/время\)\s*:\s*(\d{4})\.(\d{2})\.(\d{2})\s+(\d{2}):(\d{2}):(\d{2})'
        date_match = re.search(date_pattern, email_body)
        if date_match:
            payment['date'] = f"{date_match.group(3)}.{date_match.group(2)}.{date_match.group(1)}"
            payment['month'] = int(date_match.group(2))
            payment['year'] = date_match.group(1)
        
        logger.info(f"✅ Платеж распарсен: {payment.get('contract')} - {payment.get('amount')} руб.")
        return payment
    
    def get_new_payments(self) -> list:
        """Получить новые платежи"""
        if not self.connect():
            return []
        
        try:
            attachments = self.find_payment_attachments()
            payments = []
            
            for attachment in attachments:
                payment = self.parse_payment_email(attachment)
                
                if payment.get('contract') and payment.get('amount'):
                    logger.info(f"✅ New: {payment.get('contract')}")
                    payments.append(payment)
                else:
                    logger.warning(f"⚠️ Не найдено данных платежа в письме")
            
            return payments
        
        finally:
            self.disconnect()
