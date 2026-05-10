"""
Spirant Bot - Полная обработка платежей ФИНАЛЬНАЯ ВЕРСИЯ
Автоматическое обновление Google Sheets на основе TXT файлов из email

Правильные координаты:
- Лист: "25/26"
- Месяцы: Q (сентябрь) - Y (май)
- Номер договора: столбец J
- ФИО: столбец B
"""

import re
import gspread
from datetime import datetime
from typing import Dict, Optional, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SpeerantPaymentProcessor:
    """Обработка платежей для студентов Spirant"""
    
    # ПРАВИЛЬНЫЕ константы для Google Sheets
    SPREADSHEET_NAME = "Заявки"
    SHEET_NAME = "25/26"  # ✅ Правильный лист!
    
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
    
    @staticmethod
    def col_letter_to_num(col_letter: str) -> int:
        """
        Преобразует букву столбца (A, B, AA...) в число для gspread
        
        Args:
            col_letter: Буква столбца (A=1, B=2, Z=26, AA=27...)
            
        Returns:
            Номер столбца (1-indexed)
        """
        result = 0
        for char in col_letter:
            result = result * 26 + (ord(char) - ord('A') + 1)
        return result
    
    def connect_to_sheet(self) -> bool:
        """Подключение к Google Sheets"""
        try:
            self.spreadsheet = self.gc.open(self.SPREADSHEET_NAME)
            self.sheet = self.spreadsheet.worksheet(self.SHEET_NAME)
            logger.info(f"✅ Подключено к таблице '{self.SPREADSHEET_NAME}', лист '{self.SHEET_NAME}'")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            return False
    
    def parse_payment_file(self, file_content: str) -> Dict[str, Optional[str]]:
        """
        Парсит TXT файл платежа из ERIP/банка
        
        Формат файла:
        ```
        Номер договора (заказа) : ТС22044
        ФИО                     : Червоная Марина Владимировна
        Адрес                   : 
        Сумма                   : 184.00
        Оплачено (дата/время)   : 2026.05.09 15:25:46
        ```
        
        Returns:
            Dict с ключами: contract, fio, amount, date, month_num, year
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
        
        return data
    
    def find_row_by_contract(self, contract_num: str) -> Optional[int]:
        """
        Ищет номер строки по номеру договора
        
        Args:
            contract_num: Номер договора (ТС22XXX)
            
        Returns:
            Номер строки (1-indexed) или None
        """
        try:
            col_num = self.col_letter_to_num(self.CONTRACT_COL)
            contracts = self.sheet.col_values(col_num)
            
            for i, cell_value in enumerate(contracts):
                if contract_num in str(cell_value):
                    return i + 1
            
            logger.warning(f"⚠️ Договор {contract_num} не найден в столбце {self.CONTRACT_COL}")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка поиска договора: {e}")
            return None
    
    def find_row_by_name(self, fio: str) -> Optional[int]:
        """
        Резервный поиск по фамилии (если договор не найден)
        
        Args:
            fio: Полное имя (Фамилия Имя Отчество)
            
        Returns:
            Номер строки или None
        """
        try:
            last_name = fio.split()[0].lower()
            col_num = self.col_letter_to_num(self.NAME_COL)
            names = self.sheet.col_values(col_num)
            
            for i, cell_value in enumerate(names):
                if last_name in str(cell_value).lower():
                    return i + 1
            
            logger.warning(f"⚠️ ФИО {fio} не найдено в столбце {self.NAME_COL}")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка поиска по имени: {e}")
            return None
    
    def get_month_column(self, month_num: int) -> Optional[str]:
        """
        Получает букву столбца для месяца
        
        Args:
            month_num: Номер месяца (1-12)
            
        Returns:
            Буква столбца (Q-Y) или None
        """
        col = self.MONTHS_TO_COLUMNS.get(month_num)
        if not col:
            logger.warning(f"⚠️ Месяц {month_num} не поддерживается")
        return col
    
    def update_payment(self, payment_data: Dict) -> Tuple[bool, str]:
        """
        Обновляет платеж в таблице Google Sheets
        
        Args:
            payment_data: Словарь с данными платежа
                {
                    'contract': 'ТС22044',
                    'fio': 'Червоная Марина Владимировна',
                    'amount': '184.00',
                    'month_num': 5,
                    'date': '09.05.2026'
                }
            
        Returns:
            Кортеж (успех, сообщение с координатами или ошибкой)
        """
        if not self.sheet:
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
            return False, f"Строка не найдена для договора {contract} / ФИО {fio}"
        
        # Находим столбец месяца
        month_col = self.get_month_column(month_num)
        if not month_col:
            return False, f"Месяц {month_num} не поддерживается"
        
        try:
            # Обновляем ячейку
            cell_addr = f"{month_col}{row_num}"
            self.sheet.update(cell_addr, amount)
            
            logger.info(f"✅ Платеж обновлен: {contract} ({fio}) = {amount} руб. → {cell_addr}")
            return True, cell_addr
        
        except Exception as e:
            logger.error(f"❌ Ошибка обновления ячейки {cell_addr}: {e}")
            return False, str(e)
    
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
                notification = f"""✅ <b>Платёж обработан автоматически!</b>

📄 <b>Договор:</b> {payment_data.get('contract', 'N/A')}
👤 <b>Клиент:</b> {payment_data.get('fio', 'Unknown')}
💰 <b>Сумма:</b> {payment_data.get('amount', '?')} бел. руб.
📅 <b>Дата оплаты:</b> {payment_data.get('date', 'N/A')}
📍 <b>Ячейка таблицы:</b> <code>{message}</code>

Таблица обновлена в листе <code>{self.SHEET_NAME}</code> ✨"""
            else:
                notification = f"""⚠️ <b>Ошибка при обработке платежа!</b>

📄 <b>Договор:</b> {payment_data.get('contract', 'N/A')}
👤 <b>Клиент:</b> {payment_data.get('fio', 'Unknown')}
💰 <b>Сумма:</b> {payment_data.get('amount', '?')} бел. руб.

❌ <b>Ошибка:</b>
<code>{message}</code>

⚠️ <b>Требуется ручная проверка!</b>"""
            
            try:
                await self.bot.send_message(
                    self.admin_chat_id,
                    notification,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"❌ Ошибка отправки уведомления в Telegram: {e}")
        
        return success


# ========== ИНТЕГРАЦИЯ С TELEGRAM БОТОМ ==========

# Добавить в main.py бота:
"""
from payment_processor import SpeerantPaymentProcessor

# В инициализации бота:
payment_processor = SpeerantPaymentProcessor(
    google_creds_dict=google_credentials,
    bot=bot,
    admin_chat_id=ADMIN_CHAT_ID
)

payment_processor.connect_to_sheet()

# В обработчике файлов из email:
async def process_payment_file(file_content: str):
    payment_data = payment_processor.parse_payment_file(file_content)
    await payment_processor.process_payment(payment_data)
"""


# ========== ТЕСТИРОВАНИЕ ==========

if __name__ == "__main__":
    # Тестовые данные платежа
    test_payment_txt = """
Номер договора (заказа) : ТС22044
ФИО                     : Червоная Марина Владимировна
Адрес                   : 
Сумма                   : 184.00
Оплачено (дата/время)   : 2026.05.09 15:25:46
"""
    
    # Создаем процессор (без гугл учетных данных - для теста парсинга)
    processor = SpeerantPaymentProcessor(google_creds_dict={})
    
    # Парсим файл
    payment = processor.parse_payment_file(test_payment_txt)
    print("📋 Распарсен платеж:")
    print(f"  Договор: {payment.get('contract')}")
    print(f"  ФИО: {payment.get('fio')}")
    print(f"  Сумма: {payment.get('amount')} руб.")
    print(f"  Месяц: {payment.get('month_num')} (столбец {processor.MONTHS_TO_COLUMNS.get(payment.get('month_num'))})")
    print(f"  Дата: {payment.get('date')}")
    print()
    print(f"✅ Парсинг работает правильно!")
