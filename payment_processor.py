import re
import gspread
import logging
from typing import Dict, Optional, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SpeerantPaymentProcessor:

    SPREADSHEET_NAME = "Заявки"
    SHEET_NAME = "25/26"

    CONTRACT_COL = "K"
    NAME_COL = "B"

    # Месяц (число) → столбец
    MONTH_TO_COL = {
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

    def __init__(self, google_creds_dict: dict, bot=None, admin_chat_id: int = None):
        self.gc = gspread.service_account_from_dict(google_creds_dict)
        self.bot = bot
        self.admin_chat_id = admin_chat_id
        self.spreadsheet = None
        self.sheet = None
        self.sheet_id = None
        logger.info("SpeerantPaymentProcessor initialized")

    @staticmethod
    def col_letter_to_num(col_letter: str) -> int:
        result = 0
        for char in col_letter:
            result = result * 26 + (ord(char) - ord('A') + 1)
        return result

    def connect_to_sheet(self) -> bool:
        try:
            logger.info(f"Connecting to spreadsheet '{self.SPREADSHEET_NAME}'...")
            self.spreadsheet = self.gc.open(self.SPREADSHEET_NAME)
            self.sheet = self.spreadsheet.worksheet(self.SHEET_NAME)
            try:
                self.sheet_id = self.sheet.id
                logger.info(f"Sheet ID: {self.sheet_id}")
            except Exception:
                self.sheet_id = 1
                logger.warning("Could not get sheet ID, using fallback: 1")
            logger.info(f"Connected to sheet '{self.SHEET_NAME}'")
            return True
        except Exception as e:
            logger.error(f"Google Sheets connection error: {e}")
            return False

    def find_row_by_contract(self, contract_num: str) -> Optional[int]:
        try:
            col_num = self.col_letter_to_num(self.CONTRACT_COL)
            contracts = self.sheet.col_values(col_num)
            contract_clean = re.sub(r'\s+', '', contract_num).upper()

            for i, cell_value in enumerate(contracts):
                cell_clean = re.sub(r'\s+', '', str(cell_value)).upper()
                if contract_clean in cell_clean or cell_clean in contract_clean:
                    logger.info(f"Contract {contract_num} found at row {i + 1}")
                    return i + 1

            logger.warning(f"Contract {contract_num} not found in column {self.CONTRACT_COL}")
            return None
        except Exception as e:
            logger.error(f"Error searching contract: {e}")
            return None

    def find_row_by_name(self, fio: str) -> Optional[int]:
        try:
            last_name = fio.split()[0].lower()
            col_num = self.col_letter_to_num(self.NAME_COL)
            names = self.sheet.col_values(col_num)

            for i, cell_value in enumerate(names):
                if last_name in str(cell_value).lower():
                    logger.info(f"Name '{fio}' found at row {i + 1}")
                    return i + 1

            logger.warning(f"Name '{fio}' not found")
            return None
        except Exception as e:
            logger.error(f"Error searching by name: {e}")
            return None

    def update_payment(self, payment_data: Dict) -> Tuple[bool, str]:
        if not self.sheet:
            return False, "Sheet not connected"

        contract = payment_data.get('contract')
        fio = payment_data.get('fio')
        amount = payment_data.get('amount', '0')
        month_num = payment_data.get('month_num')

        # Найти строку
        row_num = None
        if contract:
            row_num = self.find_row_by_contract(contract)
        if not row_num and fio:
            logger.info("Contract not found, searching by name...")
            row_num = self.find_row_by_name(fio)
        if not row_num:
            return False, f"Row not found for {contract or fio}"

        # Определить столбец по месяцу
        col = self.MONTH_TO_COL.get(month_num)
        if not col:
            return False, f"Unknown month: {month_num}"

        cell_addr = f"{col}{row_num}"
        logger.info(f"Target cell: {cell_addr} (month {month_num})")

        # Проверить — уже есть значение?
        try:
            current = self.sheet.acell(cell_addr).value or ''
            current = current.strip()
            if current and current != '0':
                logger.warning(f"Cell {cell_addr} already has value: {current}, overwriting")
        except Exception as e:
            logger.warning(f"Could not read cell {cell_addr}: {e}")

        try:
            self.sheet.update(cell_addr, [[amount]])
            logger.info(f"Payment written: {contract} → {cell_addr} = {amount}")
            self.apply_red_color(row_num, col)
            return True, cell_addr
        except Exception as e:
            logger.error(f"Error updating cell {cell_addr}: {e}")
            return False, str(e)

    def apply_red_color(self, row: int, col: str):
        try:
            col_index = self.col_letter_to_num(col) - 1
            requests = [{
                "updateCells": {
                    "range": {
                        "sheetId": self.sheet_id,
                        "startRowIndex": row - 1,
                        "endRowIndex": row,
                        "startColumnIndex": col_index,
                        "endColumnIndex": col_index + 1
                    },
                    "rows": [{
                        "values": [{
                            "userEnteredFormat": {
                                "textFormat": {
                                    "foregroundColor": {"red": 1.0, "green": 0.0, "blue": 0.0}
                                }
                            }
                        }]
                    }],
                    "fields": "userEnteredFormat.textFormat.foregroundColor"
                }
            }]
            self.spreadsheet.batch_update({"requests": requests})
            logger.info(f"Red color applied to {col}{row}")
        except Exception as e:
            logger.warning(f"Could not apply red color: {e}")

    def process_payments(self, payments: list) -> dict:
        result = {'successful': 0, 'failed': 0}
        for payment in payments:
            success, message = self.update_payment(payment)
            if success:
                result['successful'] += 1
                logger.info(f"OK: {message}")
            else:
                result['failed'] += 1
                logger.warning(f"FAIL: {message}")
        logger.info(f"Processed: {result['successful']}/{len(payments)} successful")
        return result
