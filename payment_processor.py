import gspread
import logging
import base64
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class PaymentProcessor:
    """Обновляет Google Sheets платежами (красным цветом для бота)"""
    
    # Константы для таблицы
    SHEET_NAME = "25/26"
    CONTRACT_COL = "J"  # Номер договора
    NAME_COL = "B"     # ФИО
    
    # Месяцы в колонках (сентябрь-май)
    MONTHS_TO_COLUMNS = {
        9: "Q",   # Сентябрь
        10: "R",  # Октябрь
        11: "S",  # Ноябрь
        12: "T",  # Декабрь
        1: "U",   # Январь
        2: "V",   # Февраль
        3: "W",   # Март
        4: "X",   # Апрель
        5: "Y"    # Май
    }
    
    # Красный цвет для текста (для платежей от бота)
    RED_COLOR = {
        "red": 1,
        "green": 0,
        "blue": 0
    }
    
    def __init__(self, google_creds_json: str):
        """Инициализирует processor с credentials"""
        try:
            # Декодируем base64 credentials
            decoded = base64.b64decode(google_creds_json).decode('utf-8')
            credentials = json.loads(decoded)
            
            # Подключаемся к Google Sheets
            self.gc = gspread.service_account_from_dict(credentials)
            self.sheet = self.gc.open('Заявки').worksheet(self.SHEET_NAME)
            
            logger.info("✅ Google Sheets инициализирован")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Google Sheets: {e}")
            raise
    
    def find_contract_row(self, contract_number: str) -> int:
        """Находит строку контракта в таблице"""
        try:
            # Ищем номер контракта в колонке J
            cell = self.sheet.find(contract_number)
            if cell:
                logger.info(f"✅ Найден контракт {contract_number} в строке {cell.row}")
                return cell.row
            else:
                logger.warning(f"⚠️ Контракт {contract_number} не найден в таблице")
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка поиска контракта: {e}")
            return None
    
    def get_payment_month(self, payment_date: str) -> int:
        """Извлекает месяц из даты платежа (формат: 2026.05.09)"""
        try:
            # Парсим дату
            date_obj = datetime.strptime(payment_date[:10], '%Y.%m.%d')
            month = date_obj.month
            
            # Возвращаем месяц (1-12)
            return month
        except Exception as e:
            logger.warning(f"⚠️ Ошибка парсинга даты: {e}")
            return None
    
    def update_payment(self, payment: dict) -> bool:
        """Обновляет таблицу с новым платежом (красным цветом)"""
        try:
            contract_number = payment.get('contract_number')
            amount = payment.get('amount')
            payment_date = payment.get('payment_date', '')
            
            # Находим строку контракта
            row = self.find_contract_row(contract_number)
            if not row:
                return False
            
            # Определяем месяц платежа
            month = self.get_payment_month(payment_date)
            if not month or month not in self.MONTHS_TO_COLUMNS:
                logger.warning(f"⚠️ Неправильный месяц платежа: {month}")
                return False
            
            # Получаем колонку месяца
            month_col = self.MONTHS_TO_COLUMNS[month]
            cell_address = f"{month_col}{row}"
            
            # Определяем что писать (зависит от суммы)
            # 184 = полный платеж
            # 92 = половина
            # 46 = четверть
            # 0 = не оплачено
            if amount >= 184:
                mark = "✓"  # Полный платеж
            elif amount >= 92:
                mark = "½"  # Половина
            elif amount >= 46:
                mark = "¼"  # Четверть
            else:
                mark = "0"  # Не оплачено
            
            # Обновляем ячейку
            self.sheet.update_cell(row, ord(month_col) - ord('A') + 1, mark)
            
            # Применяем красный цвет текста
            self._set_cell_color_red(cell_address)
            
            logger.info(f"✅ Платеж обновлён: {contract_number} {month_col}{row} = {mark} (красный)")
            return True
        
        except Exception as e:
            logger.error(f"❌ Ошибка обновления платежа: {e}")
            return False
    
    def _set_cell_color_red(self, cell_address: str):
        """Устанавливает красный цвет текста для ячейки"""
        try:
            # Используем Google Sheets API для форматирования
            from googleapiclient.discovery import build
            
            # Получаем spreadsheet_id из sheet
            spreadsheet_id = self.sheet.spreadsheet.id
            
            # Парсим адрес ячейки (например, "J5")
            col_letter = cell_address[0]
            row_number = int(cell_address[1:])
            
            # Преобразуем букву в индекс колонки (A=0, B=1, и т.д.)
            col_index = ord(col_letter) - ord('A')
            
            # Создаём request для форматирования
            request_body = {
                'requests': [
                    {
                        'repeatCell': {
                            'range': {
                                'sheetId': self.sheet.id,
                                'rowIndex': row_number - 1,
                                'columnIndex': col_index,
                                'endRowIndex': row_number,
                                'endColumnIndex': col_index + 1
                            },
                            'cell': {
                                'userEnteredFormat': {
                                    'textFormat': {
                                        'foregroundColor': {
                                            'red': 1.0,  # Красный
                                            'green': 0.0,
                                            'blue': 0.0
                                        }
                                    }
                                }
                            },
                            'fields': 'userEnteredFormat.textFormat.foregroundColor'
                        }
                    }
                ]
            }
            
            # Применяем форматирование
            service = build('sheets', 'v4', static_discovery=False)
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body=request_body
            ).execute()
            
            logger.info(f"✅ Красный цвет применён к {cell_address}")
        
        except Exception as e:
            logger.warning(f"⚠️ Ошибка применения красного цвета (не критично): {e}")
            # Не прерываем процесс если цвет не применился
    
    def process_payments(self, payments: list) -> dict:
        """Обрабатывает список платежей"""
        result = {
            'total': len(payments),
            'success': 0,
            'failed': 0,
            'details': []
        }
        
        for payment in payments:
            try:
                if self.update_payment(payment):
                    result['success'] += 1
                    result['details'].append(f"✅ {payment['contract_number']}")
                else:
                    result['failed'] += 1
                    result['details'].append(f"❌ {payment['contract_number']}")
            except Exception as e:
                result['failed'] += 1
                result['details'].append(f"❌ {payment.get('contract_number', 'unknown')}: {str(e)}")
        
        logger.info(f"📊 Обработано платежей: {result['success']}/{result['total']}")
        return result
