import re
import gspread
import logging
from datetime import datetime
from typing import Dict, Optional, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MONTH_NAMES = {
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май"
}


class SpeerantPaymentProcessor:

    SPREADSHEET_NAME = "Заявки"
    SHEET_NAME = "25/26"
    ERRORS_SHEET_NAME = "Ошибки"

    CONTRACT_COL = "K"
    NAME_COL = "B"

    MONTHS_COLUMNS = ["Q", "R", "S", "T", "U", "V", "W", "X", "Y"]

    def __init__(self, google_creds_dict: dict, bot=None, admin_chat_id: int = None):
        self.gc = gspread.service_account_from_dict(google_creds_dict)
        self.bot = bot
        self.admin_chat_id = admin_chat_id
        self.spreadsheet = None
        self.sheet = None
        self.sheet_id = None
        self.errors_sheet = None
        logger.info("SpeerantPaymentProcessor initialized")

    @staticmethod
    def col_letter_to_num(col_letter: str) -> int:
        result = 0
        for char in col_letter:
            result = result * 26 + (ord(char) - ord('A') + 1)
        return result

    @staticmethod
    def format_amount(amount_str: str) -> str:
        try:
            value = float(amount_str.replace(",", "."))
            if value == int(value):
                return str(int(value))
            return f"{value:.2f}".replace(".", ",")
        except Exception:
            return amount_str

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
            self._init_errors_sheet()
            return True
        except Exception as e:
            logger.error(f"Google Sheets connection error: {e}")
            return False

    def _init_errors_sheet(self):
        try:
            self.errors_sheet = self.spreadsheet.worksheet(self.ERRORS_SHEET_NAME)
            logger.info("Error sheet found")
        except gspread.WorksheetNotFound:
            self.errors_sheet = self.spreadsheet.add_worksheet(
                title=self.ERRORS_SHEET_NAME, rows=1000, cols=6
            )
            self.errors_sheet.append_row(
                ["Дата", "Договор", "ФИО", "Сумма", "Месяц", "Причина"],
                value_input_option="RAW"
            )
            logger.info("Error sheet created")

    def log_error_to_sheet(self, payment_data: Dict, reason: str):
        if not self.errors_sheet:
            return
        try:
            month_num = payment_data.get("month_num")
            row = [
                datetime.now().strftime("%d.%m.%Y %H:%M"),
                payment_data.get("contract", "-"),
                payment_data.get("fio", "-"),
                self.format_amount(payment_data.get("amount", "0")),
                MONTH_NAMES.get(month_num, str(month_num)) if month_num else "-",
                reason,
            ]
            self.errors_sheet.append_row(row, value_input_option="RAW")
            logger.info(f"Error logged: {reason}")
        except Exception as e:
            logger.warning(f"Could not write to error sheet: {e}")

    def find_row_by_contract(self, contract_num: str) -> Optional[int]:
        try:
            col_num = self.col_letter_to_num(self.CONTRACT_COL)
            contracts = self.sheet.col_values(col_num)
            contract_clean = re.sub(r'\s+', '', contract_num).upper()

            for i, cell_value in enumerate(contracts):
                if not cell_value or not cell_value.strip():
                    continue
                cell_clean = re.sub(r'\s+', '', str(cell_value)).upper()
                if contract_clean == cell_clean or contract_clean in cell_clean:
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
                if not cell_value or not cell_value.strip():
                    continue
                if last_name in str(cell_value).lower():
                    logger.info(f"Name '{fio}' found at row {i + 1}")
                    return i + 1

            logger.warning(f"Name '{fio}' not found")
            return None
        except Exception as e:
            logger.error(f"Error searching by name: {e}")
            return None

    def find_first_empty_month_cell(self, row_num: int) -> Optional[str]:
        try:
            row_values = self.sheet.row_values(row_num)

            for col_letter in self.MONTHS_COLUMNS:
                col_num = self.col_letter_to_num(col_letter)
                cell_index = col_num - 1

                if cell_index >= len(row_values):
                    logger.info(f"First empty cell: {col_letter}{row_num}")
                    return col_letter

                cell_value = row_values[cell_index].strip()
                if not cell_value:
                    logger.info(f"First empty cell: {col_letter}{row_num}")
                    return col_letter

                logger.info(f"  {col_letter}{row_num}: '{cell_value}' - skip")

            logger.warning(f"No empty cells in row {row_num} (Q-Y)")
            return None
        except Exception as e:
            logger.error(f"Error finding empty cell: {e}")
            return None

    def update_payment(self, payment_data: Dict) -> Tuple[bool, str]:
        if not self.sheet:
            return False, "Sheet not connected"

        contract = payment_data.get('contract')
        fio = payment_data.get('fio')
        amount = self.format_amount(payment_data.get('amount', '0'))

        row_num = None
        if contract:
            row_num = self.find_row_by_contract(contract)
        if not row_num and fio:
            logger.info("Contract not found, searching by name...")
            row_num = self.find_row_by_name(fio)
        if not row_num:
            reason = f"Не найден в таблице: {contract or fio}"
            self.log_error_to_sheet(payment_data, reason)
            return False, reason

        col = self.find_first_empty_month_cell(row_num)
        if not col:
            reason = f"Все ячейки заняты в строке {row_num}"
            self.log_error_to_sheet(payment_data, reason)
            return False, reason

        cell_addr = f"{col}{row_num}"
        try:
            self.sheet.update(cell_addr, [[amount]])
            logger.info(f"Payment written: {contract} -> {cell_addr} = {amount}")
            self.apply_red_color(row_num, col)
            return True, cell_addr
        except Exception as e:
            reason = str(e)
            self.log_error_to_sheet(payment_data, reason)
            logger.error(f"Error updating cell {cell_addr}: {e}")
            return False, reason

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
        result = {'successful': 0, 'failed': 0, 'errors': []}
        for payment in payments:
            success, message = self.update_payment(payment)
            if success:
                result['successful'] += 1
                logger.info(f"OK: {message}")
            else:
                result['failed'] += 1
                result['errors'].append({
                    'contract': payment.get('contract', '-'),
                    'fio': payment.get('fio', '-'),
                    'amount': self.format_amount(payment.get('amount', '0')),
                    'reason': message,
                })
                logger.warning(f"FAIL: {message}")
        logger.info(f"Processed: {result['successful']}/{len(payments)} successful")
        return result
