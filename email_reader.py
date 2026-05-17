import imaplib
import email
from email.header import decode_header
import logging
import re

logger = logging.getLogger(__name__)

PAYMENT_SENDERS = ['ipay@ipay.by', 'zhmykhtv@gmail.com']


class EmailPaymentReader:
    """Чтение платежей из Gmail IMAP"""

    def __init__(self, email_addr: str, app_password: str):
        self.email = email_addr
        self.app_password = app_password
        self.imap = None
        self.processed_emails = set()

    def connect(self) -> bool:
        try:
            logger.info(f"Connecting to Gmail: {self.email}")
            self.imap = imaplib.IMAP4_SSL("imap.gmail.com")
            self.imap.login(self.email, self.app_password)
            logger.info(f"Gmail connected: {self.email}")
            return True
        except Exception as e:
            logger.error(f"Gmail connection error: {e}")
            return False

    def disconnect(self):
        try:
            if self.imap:
                self.imap.close()
                self.imap.logout()
        except:
            pass

    def _extract_txt(self, msg) -> str | None:
        """Ищет .txt вложение в письме, включая пересланные (message/rfc822)"""
        for part in msg.walk():
            if part.get_content_type() == 'message/rfc822':
                nested = part.get_payload(0)
                if nested:
                    result = self._extract_txt(nested)
                    if result:
                        return result
                continue

            if part.get_content_disposition() != 'attachment':
                continue

            filename = part.get_filename() or ''
            if not filename.endswith('.txt'):
                continue

            content = part.get_payload(decode=True)
            if not content:
                continue

            for encoding in ['utf-8', 'cp1251', 'windows-1251', 'latin-1', 'iso-8859-5']:
                try:
                    text = content.decode(encoding)
                    logger.info(f"Attachment decoded ({encoding}): {filename}")
                    return text
                except Exception:
                    continue

        return None

    def find_payment_attachments(self) -> list:
        """Ищет новые (UNSEEN) письма от известных отправителей"""
        try:
            self.imap.select("INBOX")

            all_ids = set()
            for sender in PAYMENT_SENDERS:
                status, messages = self.imap.search(None, 'UNSEEN', 'FROM', sender)
                if status == 'OK' and messages[0]:
                    ids = messages[0].split()
                    all_ids.update(ids)
                    logger.info(f"Found {len(ids)} unseen email(s) from {sender}")

            logger.info(f"Total unseen payment emails: {len(all_ids)}")

            attachments = []
            for email_id in all_ids:
                status, msg_data = self.imap.fetch(email_id, '(RFC822)')
                if status != 'OK':
                    continue

                msg = email.message_from_bytes(msg_data[0][1])
                txt = self._extract_txt(msg)

                if txt:
                    attachments.append(txt)
                    self.imap.store(email_id, '+FLAGS', '\Seen')
                    logger.info(f"Email {email_id} marked as read")
                else:
                    logger.warning(f"No .txt attachment found in email {email_id}")

            return attachments

        except Exception as e:
            logger.error(f"Error searching emails: {e}")
            return []

    def parse_payment_email(self, email_body: str) -> dict:
        payment = {}

        contract_match = re.search(
            r'Номер договора \(заказа\)\s*:\s*([А-Яa-zA-Z]*?)(\d+)', email_body
        )
        if contract_match:
            prefix = contract_match.group(1).strip().upper().replace('TC', 'ТС') or 'ТС'
            payment['contract'] = prefix + contract_match.group(2).strip()
            logger.info(f"Contract: {payment['contract']}")
        else:
            logger.error("Contract number not found in email")

        fio_match = re.search(r'ФИО\s*:\s*([А-Яа-я\s]+?)(?:\n|$)', email_body)
        if fio_match:
            payment['fio'] = fio_match.group(1).strip()
            logger.info(f"Name: {payment['fio']}")

        amount_match = re.search(r'Сумма\s*:\s*([\d.]+)', email_body)
        if amount_match:
            payment['amount'] = amount_match.group(1).strip()
            logger.info(f"Amount: {payment['amount']}")

        date_match = re.search(
            r'Оплачено \(дата/время\)\s*:\s*(\d{4})\.(\d{2})\.(\d{2})\s+(\d{2}):(\d{2}):(\d{2})',
            email_body
        )
        if date_match:
            payment['date'] = f"{date_match.group(3)}.{date_match.group(2)}.{date_match.group(1)}"
            payment['month_num'] = int(date_match.group(2))
            payment['year'] = date_match.group(1)
            logger.info(f"Date: {payment['date']}, month: {payment['month_num']}")
        else:
            logger.error("Date not found in email")

        return payment

    def get_new_payments(self) -> list:
        if not self.connect():
            return []
        try:
            attachments = self.find_payment_attachments()
            payments = []
            for attachment in attachments:
                payment = self.parse_payment_email(attachment)
                if payment.get('contract') and payment.get('amount') and payment.get('month_num'):
                    logger.info(f"Payment ready: {payment.get('contract')}")
                    payments.append(payment)
                else:
                    logger.warning("Incomplete payment data, skipping")
            return payments
        finally:
            self.disconnect()
