import imaplib
import email
from email.header import decode_header
import logging
import re

logger = logging.getLogger(__name__)

class EmailPaymentReader:
    def __init__(self, email_addr: str, app_password: str):
        self.email_addr = email_addr
        self.app_password = app_password
        self.imap_server = "imap.gmail.com"
        self.imap_port = 993
        self.processed_emails = set()
    
    def connect(self):
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(self.email_addr, self.app_password)
            logger.info(f"✅ Gmail: {self.email_addr}")
            return mail
        except Exception as e:
            logger.error(f"❌ Gmail error: {e}")
            raise
    
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
        payments = []
        try:
            mail = self.connect()
            mail.select('INBOX')
            status, email_ids = mail.search(None, 'FROM', 'zhmykhtv@gmail.com')
            
            if status != 'OK':
                mail.close()
                return payments
            
            email_list = email_ids[0].split()
            
            for email_id in reversed(email_list[-10:]):
                if email_id.decode() in self.processed_emails:
                    continue
                
                try:
                    status, msg_data = mail.fetch(email_id, '(RFC822)')
                    if status != 'OK':
                        continue
                    
                    msg = email.message_from_bytes(msg_data[0][1])
                    email_body = ""
                    
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            
                            if content_type == "text/plain":
                                try:
                                    email_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                    break
                                except:
                                    pass
                    else:
                        try:
                            email_body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                        except:
                            email_body = msg.get_payload(decode=False)
                    
                    payment = self.parse_payment_email(email_body)
                    
                    if not payment and msg.is_multipart():
                        logger.info(f"📎 Ищу в вложениях...")
                        for part in msg.walk():
                            if part.get_content_disposition() == 'attachment':
                                filename = part.get_filename()
                                logger.info(f"  📄 Файл: {filename}")
                                
                                if filename and filename.endswith('.txt'):
                                    try:
                                        attachment_body = None
                                        for encoding in ['utf-8', 'cp1251', 'windows-1251', 'latin-1', 'iso-8859-1']:
                                            try:
                                                attachment_body = part.get_payload(decode=True).decode(encoding)
                                                logger.info(f"  ✅ Кодировка: {encoding}")
                                                break
                                            except:
                                                continue
                                        
                                        if not attachment_body:
                                            attachment_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                                        
                                        logger.debug(f"  Содержимое: {attachment_body[:200]}")
                                        payment = self.parse_payment_email(attachment_body)
                                        
                                        if payment:
                                            logger.info(f"✅ Найден платёж во вложении!")
                                            break
                                    except Exception as e:
                                        logger.warning(f"  ⚠️ Ошибка чтения вложения: {e}")
                    
                    if payment:
                        payments.append(payment)
                        self.processed_emails.add(email_id.decode())
                        logger.info(f"✅ New: {payment['contract_number']}")
                    else:
                        logger.warning(f"⚠️ Не найдено данных платежа в письме")
                
                except Exception as e:
                    logger.warning(f"⚠️ Error: {e}")
                    continue
            
            mail.close()
            return payments
        
        except Exception as e:
            logger.error(f"❌ Critical: {e}")
            return payments
