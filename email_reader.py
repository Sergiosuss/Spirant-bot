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
        try:
            data = {}
            contract_match = re.search(r'Номер договора.*?:\s*(ТС22\d+)', email_body, re.IGNORECASE)
            if contract_match:
                data['contract_number'] = contract_match.group(1).strip()
            
            amount_match = re.search(r'Сумма\s*:\s*([\d.]+)', email_body, re.IGNORECASE)
            if amount_match:
                data['amount'] = float(amount_match.group(1).strip())
            
            date_match = re.search(r'Оплачено.*?:\s*(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})', email_body, re.IGNORECASE)
            if date_match:
                data['payment_date'] = date_match.group(1).strip()
            
            if 'contract_number' in data and 'amount' in data:
                logger.info(f"✅ Payment: {data['contract_number']}")
                return data
            return None
        except Exception as e:
            logger.error(f"❌ Parse error: {e}")
            return None
    
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
                    
                    # Сначала ищем в теле письма
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
                    
                    # Пытаемся распарсить
                    payment = self.parse_payment_email(email_body)
                    
                    # ЕСЛИ НЕ НАШЛИ В ТЕЛЕ - ИЩЕМ В ВЛОЖЕНИЯХ
                    if not payment and msg.is_multipart():
                        logger.info(f"📎 Ищу в вложениях...")
                        for part in msg.walk():
                            if part.get_content_disposition() == 'attachment':
                                filename = part.get_filename()
                                logger.info(f"  📄 Файл: {filename}")
                                
                                # Если это .txt файл - читаем его
                                if filename and filename.endswith('.txt'):
                                    try:
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
