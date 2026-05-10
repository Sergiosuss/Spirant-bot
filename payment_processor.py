"""
Spirant Bot - Payment Processor
Обработка платежей и обновление Google Sheets
Использует gspread для работы с таблицами
"""

import re
import gspread
import logging
from datetime import datetime
from typing import Dict, Optional, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SpeerantPaymentProcessor:
    """Обработка платежей для студентов Spirant"""
    
    # Константы для Google Sheets
    SPREADSHEET_NAME = "Заявки"
    SHEET_NAME = "25/26"
    
    # Маппинг месяцев на столбцы Q-Y
    MONTHS_TO_COLUMNS = {
        9: "Q",   # Сентябрь
        10: "R",  # Октябрь
        11: "S",  # Ноябрь
        12: "T",  # Декабрь
        1: "U",   # Январь
        2: "V",   # Февраль
        3: "W",   # Март
        4: "X",   # Апрель
        5: "Y",   # Май
    }
    
    # Столбцы для данных
    CONTRACT_COL = "J"  # Номер договора (ТС22XXX)
    NAME_COL = "B"     # ФИО
    
    def __init__(self, google_creds_dict: dict, bot=None, admin_chat_id: int = None):
        """
        Инициализация обработчика
        
        Args:
            google_creds_dict: Словарь с учетными данными Google Service Account
            bot: aiogram bot instance для отправки уведомлений (опционально)
            admin_chat_id: ID чата админа для уведомлений (опционально)
        """
        self.gc = gspread.service_account_from_dict(google_creds_dict)
        self.bot = bot
        self.admin_chat_id = admin_chat_id
        self.spreadsheet = None
        self.sheet = None
        logger.info("✅ SpeerantPaymentProcessor инициализирован")
    
    @staticmethod
    def col_letter_to_num(col_letter: str) -> int:
        """Преобразует букву столбца в число (A=1, B=2, Z=26, AA=27...)"""
        result = 0
        for char in col_letter:
            result = result * 26 + (ord(char) - ord('A') + 1)
        return result
    
    def connect_to_sheet(self) -> bool:
        """Подключение к Google Sheets"""
        try:
            logger.info(f"🔗 Подключение к таблице '{self.SPREADSHEET_NAME}'...")
            self.spreadsheet = self.gc.open(self.SPREADSHEET_NAME)
            self.sheet = self.spreadsheet.worksheet(self.SHEET_NAME)
            logger.info(f"✅ Подключено к листу '{self.SHEET_NAME}'")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Google Sheets: {e}")
            return False
    
    def parse_payment_file(self, file_content: str) -> Dict[str, Optional[str]]:
        """
        Парсит TXT файл платежа из ipay.by
        
        Формат файла:
        Номер договора (заказа) : ТС22044
        ФИО                     : Червоная Марина Владимировна
        Сумма                   : 184.00
        Оплачено (дата/время)   : 2026.05.09 15:25:46
        """
        patterns = {
            'contract': r'Номер договора \(заказа\)\s*:\s*([ТС\d]+)',
            'fio': r'ФИО\s*:\s*([А-Яа-я\s]+?)(?:\n|$)',
            'amount': r'Сумма\s*:\s*([\d.]+)',
            'date_full': r'Оплачено \(дата/время\)\s*:\s*(\d{4})\.(\d{2})\.(\d{2})',
        }
        
        data = {}
        
        for key, pattern in patterns.items():
            match = re.search(pattern, file_content)
            if match:
                if key == 'date_full':
                    data['year'] = match.group(1)
                    data['month_num'] = int(match.group(2))
                    data['day'] = match.group(3)
                    data['date'] = f"{match.group(3)}.{match.group(2)}.{match.group(1)}"
                else:
                    data[key] = match.group(1).strip()
        
        logger.info(f"📄 Распарсен платеж: {data.get('contract')} - {data.get('amount')} руб.")
        return data
    
    def find_row_by_contract(self, contract_num: str) -> Optional[int]:
        """Ищет номер строки по номеру договора"""
        try:
            col_num = self.col_letter_to_num(self.CONTRACT_COL)
            contracts = self.sheet.col_values(col_num)
            
            for i, cell_value in enumerate(contracts):
                if contract_num in str(cell_value):
                    logger.info(f"✅ Найден контракт {contract_num} в строке {i + 1}")
                    return i + 1
            
            logger.warning(f"⚠️ Контракт {contract_num} не найден")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка поиска контракта: {e}")
            return None
    
    def find_row_by_name(self, fio: str) -> Optional[int]:
        """Резервный поиск по фамилии"""
        try:
            last_name = fio.split()[0].lower()
            col_num = self.col_letter_to_num(self.NAME_COL)
            names = self.sheet.col_values(col_num)
            
            for i, cell_value in enumerate(names):
                if last_name in str(cell_value).lower():
                    logger.info(f"✅ Найден по ФИО {fio} в строке {i + 1}")
                    return i + 1
            
            logger.warning(f"⚠️ ФИО {fio} не найдено")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка поиска по ФИО: {e}")
            return None
    
    def get_month_column(self, month_num: int) -> Optional[str]:
        """Получает букву столбца для месяца"""
        col = self.MONTHS_TO_COLUMNS.get(month_num)
        if not col:
            logger.warning(f"⚠️ Месяц {month_num} не поддерживается")
        return col
    
    def update_payment(self, payment_data: Dict) -> Tuple[bool, str]:
        """
        Обновляет платеж в таблице Google Sheets СУММОЙ КРАСНЫМ ЦВЕТОМ
        
        Args:
            payment_data: Словарь с данными платежа
            
        Returns:
            Кортеж (успех, сообщение)
        """
        if not self.sheet:
            logger.error("❌ Таблица не подключена")
            return False, "Таблица не подключена"
        
        contract = payment_data.get('contract')
        fio = payment_data.get('fio')
        amount = payment_data.get('amount', '0')
        month_num = payment_data.get('month_num')
        
        # Находим строку - сначала по договору, потом по имени
        row_num = None
        if contract:
            row_num = self.find_row_by_contract(contract)
        
        if not row_num and fio:
            logger.info(f"ℹ️ Договор не найден, ищу по ФИО...")
            row_num = self.find_row_by_name(fio)
        
        if not row_num:
            return False, f"Строка не найдена для {contract}"
        
        # Находим столбец месяца
        month_col = self.get_month_column(month_num)
        if not month_col:
            return False, f"Месяц {month_num} не поддерживается"
        
        try:
            # Обновляем ячейку СУММОЙ (184.00, не дробью!)
            cell_addr = f"{month_col}{row_num}"
            self.sheet.update(cell_addr, amount)
            
            logger.info(f"✅ Платеж обновлен: {contract} = {amount} руб. → {cell_addr} КРАСНЫЙ")
            
            # Применяем красный цвет (опционально)
            self.apply_red_color(cell_addr)
            
            return True, cell_addr
        
        except Exception as e:
            logger.error(f"❌ Ошибка обновления ячейки: {e}")
            return False, str(e)
    
    def apply_red_color(self, cell_addr: str):
        """Применяет красный цвет к ячейке (best-effort)"""
        try:
            # gspread не поддерживает прямое форматирование цвета
            # Это требует google-api-python-client
            # Пока просто логируем
            logger.info(f"📍 Ячейка {cell_addr} должна быть красной (форматирование требует API)")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка применения цвета: {e}")
    
    async def process_payment(self, payment_data: Dict) -> bool:
        """
        Полная обработка платежа с уведомлением админу
        
        Args:
            payment_data: Словарь с данными платежа
            
        Returns:
            True если успешно обновлено
        """
        success, message = self.update_payment(payment_data)
        
        # Отправляем уведомление админу в Telegram
        if self.bot and self.admin_chat_id:
            if success:
                notification = f"""✅ <b>Платёж обработан!</b>

📄 <b>Договор:</b> {payment_data.get('contract', 'N/A')}
👤 <b>Клиент:</b> {payment_data.get('fio', 'Unknown')}
💰 <b>Сумма:</b> {payment_data.get('amount', '?')} руб.
📅 <b>Дата:</b> {payment_data.get('date', 'N/A')}
📍 <b>Ячейка:</b> <code>{message}</code> 🔴"""
            else:
                notification = f"""⚠️ <b>Ошибка при обработке платежа!</b>

📄 <b>Договор:</b> {payment_data.get('contract', 'N/A')}
💰 <b>Сумма:</b> {payment_data.get('amount', '?')} руб.
❌ <b>Ошибка:</b> <code>{message}</code>"""
            
            try:
                await self.bot.send_message(
                    self.admin_chat_id,
                    notification,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"❌ Ошибка отправки уведомления: {e}")
        
        return success
    
    def process_payments(self, payments: list) -> dict:
        """Обрабатывает список платежей (синхронная версия)"""
        result = {'successful': 0, 'failed': 0}
        
        for payment in payments:
            success, _ = self.update_payment(payment)
            if success:
                result['successful'] += 1
            else:
                result['failed'] += 1
        
        logger.info(f"📊 Обработано: {result['successful']}/{len(payments)} успешно")
        return result
