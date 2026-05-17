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
    MONTHS_COLUMNS = ["Q", "R", "S", "T", "U", "V", "W", "X", "Y"]  # Сентябрь-май
    
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
        self.sheet_id = None
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
            
            # Получаем sheetId листа
            try:
                self.sheet_id = self.sheet.id
                logger.info(f"✅ Получен sheetId: {self.sheet_id}")
            except:
                self.sheet_id = 1
                logger.warning(f"⚠️ Не удалось получить sheetId, используется fallback: 1")
            
            logger.info(f"✅ Подключено к листу '{self.SHEET_NAME}'")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Google Sheets: {e}")
            return False
    
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
    
    def find_first_empty_month_cell(self, row_num: int) -> Optional[str]:
        """
        Находит ПЕРВУЮ ПУСТУЮ ячейку в столбцах месяцев (Q-Y)
        Начиная с сентября (Q) и идя к маю (Y)
        
        Returns:
            Буква столбца (Q, R, S, T, U, V, W, X, Y) или None
        """
        try:
            logger.info(f"🔍 Ищу первую пустую ячейку в строке {row_num}...")
            
            # Получаем значения всех месячных ячеек
            row_values = self.sheet.row_values(row_num)
            
            # Ищем первую пустую ячейку в столбцах Q-Y
            for col_letter in self.MONTHS_COLUMNS:
                col_num = self.col_letter_to_num(col_letter)
                
                # col_num начинается с 1, а row_values с индекса 0
                cell_index = col_num - 1
                
                if cell_index < len(row_values):
                    cell_value = row_values[cell_index].strip()
                    
                    if not cell_value:  # Пусто
                        logger.info(f"✅ Найдена пустая ячейка: {col_letter}{row_num}")
                        return col_letter
                    else:
                        logger.info(f"  • {col_letter}{row_num}: {cell_value} (заполнено)")
                else:
                    # Если строка короче, значит ячейка пуста
                    logger.info(f"✅ Найдена пустая ячейка: {col_letter}{row_num} (за пределами)")
                    return col_letter
            
            logger.warning(f"⚠️ Все ячейки в строке {row_num} заполнены!")
            return None
        
        except Exception as e:
            logger.error(f"❌ Ошибка поиска пустой ячейки: {e}")
            return None
    
    def update_payment(self, payment_data: Dict) -> Tuple[bool, str]:
        """
        Обновляет платеж в таблице Google Sheets СУММОЙ в ПЕРВУЮ СВОБОДНУЮ ячейку КРАСНЫМ ЦВЕТОМ
        
        Args:
            payment_data: Словарь с данными платежа
            
        Returns:
            Кортеж (успех, сообщение/адрес_ячейки)
        """
        if not self.sheet:
            logger.error("❌ Таблица не подключена")
            return False, "Таблица не подключена"
        
        contract = payment_data.get('contract')
        fio = payment_data.get('fio')
        amount = payment_data.get('amount', '0')
        
        # Находим строку - сначала по договору, потом по имени
        row_num = None
        if contract:
            row_num = self.find_row_by_contract(contract)
        
        if not row_num and fio:
            logger.info(f"ℹ️ Договор не найден, ищу по ФИО...")
            row_num = self.find_row_by_name(fio)
        
        if not row_num:
            return False, f"Строка не найдена для {contract or fio}"
        
        # НОВАЯ ЛОГИКА: Ищем ПЕРВУЮ ПУСТУЮ ячейку в месячных столбцах
        col = self.find_first_empty_month_cell(row_num)
        
        if not col:
            return False, f"Нет свободных ячеек в строке {row_num}"
        
        try:
            # Обновляем ячейку СУММОЙ
            cell_addr = f"{col}{row_num}"
            self.sheet.update(cell_addr, amount)
            
            logger.info(f"✅ Платеж обновлен: {contract} = {amount} руб. → {cell_addr}")
            
            # Применяем красный цвет
            self.apply_red_color(row_num, col)
            
            return True, cell_addr
        
        except Exception as e:
            logger.error(f"❌ Ошибка обновления ячейки: {e}")
            return False, str(e)
    
    def apply_red_color(self, row: int, col: str):
        """Применяет красный цвет к ячейке"""
        try:
            col_index = ord(col) - ord('A')
            
            requests = [{
                "updateCellStyle": {
                    "range": {
                        "sheetId": self.sheet_id,
                        "rowIndex": row - 1,
                        "columnIndex": col_index,
                        "endRowIndex": row,
                        "endColumnIndex": col_index + 1
                    },
                    "fields": "userEnteredFormat.textFormat.foregroundColor",
                    "style": {
                        "textFormat": {
                            "foregroundColor": {"red": 1, "green": 0, "blue": 0}
                        }
                    }
                }
            }]
            
            self.spreadsheet.batch_update({"requests": requests})
            logger.info(f"🔴 Красный цвет применён: {col}{row}")
        
        except Exception as e:
            logger.warning(f"⚠️ Ошибка применения цвета: {e}")
    
    def process_payments(self, payments: list) -> dict:
        """Обрабатывает список платежей"""
        result = {'successful': 0, 'failed': 0}
        
        for payment in payments:
            success, message = self.update_payment(payment)
            if success:
                result['successful'] += 1
                logger.info(f"✅ Успешно: {message}")
            else:
                result['failed'] += 1
                logger.warning(f"❌ Ошибка: {message}")
        
        logger.info(f"📊 Обработано: {result['successful']}/{len(payments)} успешно")
        return result
