import logging
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import os
import json
import base64

logger = logging.getLogger(__name__)

class PaymentProcessor:  # ← ПРАВИЛЬНОЕ ИМЯ (без Speerant)
    def __init__(self):
        self.sheet_id = "1ZTDM8Ea-niTFVPly2ElrUQ00ztlGRFBWhE-seIrMnwY"
        self.sheet_name = "25/26"
        self.contract_col = "J"
        self.name_col = "B"
        
        self.months_to_columns = {
            9: "Q", 10: "R", 11: "S", 12: "T",
            1: "U", 2: "V", 3: "W", 4: "X", 5: "Y"
        }
        
        self.red_color = {"red": 1, "green": 0, "blue": 0}
        
        try:
            creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
            if creds_json:
                creds_data = json.loads(base64.b64decode(creds_json))
                self.creds = Credentials.from_service_account_info(creds_data)
            else:
                self.creds = None
            
            self.service = build('sheets', 'v4', credentials=self.creds)
            logger.info("✅ Google Sheets инициализирован")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Google Sheets: {e}")
            self.service = None
    
    def find_contract_row(self, contract_number: str) -> int:
        """Ищет номер строки по номеру контракта"""
        try:
            range_name = f"{self.sheet_name}!{self.contract_col}:{self.contract_col}"
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            for idx, row in enumerate(values, start=1):
                if row and row[0].strip() == contract_number.strip():
                    logger.info(f"✅ Найден контракт {contract_number} в строке {idx}")
                    return idx
            
            logger.warning(f"⚠️ Контракт {contract_number} не найден")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка поиска контракта: {e}")
            return None
    
    def update_payment(self, contract_number: str, amount: float, payment_date: str) -> bool:
        """Обновляет платёж в Google Sheets СУММОЙ красным цветом"""
        try:
            row = self.find_contract_row(contract_number)
            if not row:
                return False
            
            date_parts = payment_date.split('.')
            month = int(date_parts[1])
            
            col = self.months_to_columns.get(month)
            if not col:
                logger.warning(f"⚠️ Месяц {month} не поддерживается")
                return False
            
            cell = f"{self.sheet_name}!{col}{row}"
            
            # ПИШЕМ СУММУ КРАСНЫМ!
            self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range=cell,
                valueInputOption='USER_ENTERED',
                body={'values': [[amount]]}
            ).execute()
            
            logger.info(f"✅ Платеж обновлён: {contract_number} {col}{row} = {amount}")
            
            self.apply_red_color(row, col)
            
            return True
        
        except Exception as e:
            logger.error(f"❌ Ошибка обновления платежа: {e}")
            return False
    
    def apply_red_color(self, row: int, col: str):
        """Применяет красный цвет к ячейке"""
        try:
            col_index = ord(col) - ord('A')
            
            requests = [
                {
                    "updateCellStyle": {
                        "range": {
                            "sheetId": 1,
                            "rowIndex": row - 1,
                            "columnIndex": col_index,
                            "endRowIndex": row,
                            "endColumnIndex": col_index + 1
                        },
                        "fields": "userEnteredFormat.textFormat.foregroundColor",
                        "style": {
                            "textFormat": {
                                "foregroundColor": self.red_color
                            }
                        }
                    }
                }
            ]
            
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.sheet_id,
                body={'requests': requests}
            ).execute()
            
            logger.info(f"✅ Красный цвет применён: {col}{row}")
        
        except Exception as e:
            logger.warning(f"⚠️ Ошибка применения цвета (не критично): {e}")
    
    def process_payments(self, payments: list) -> dict:
        """Обрабатывает список платежей"""
        result = {'successful': 0, 'failed': 0}
        
        for payment in payments:
            if self.update_payment(
                payment['contract_number'],
                payment['amount'],
                payment['payment_date']
            ):
                result['successful'] += 1
            else:
                result['failed'] += 1
        
        logger.info(f"📊 Обработано платежей: {result['successful']}/{len(payments)}")
        return result
