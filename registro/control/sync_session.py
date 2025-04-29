# ----------------------------------------------------------------------------
# File: registro/control/sync_session.py (Refined gspread Wrapper)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
import json
import logging
from typing import List, Set, Tuple, Optional, Dict, Any
import gspread
from gspread.exceptions import APIError, WorksheetNotFound, SpreadsheetNotFound
from gspread.utils import ValueInputOption
from registro.control.constants import SPREADSHEET_ID_JSON
from registro.control.google_creds import GrantAccess
logger = logging.getLogger(__name__)

def _convert_to_tuples(list_of_lists: List[List[Any]]) -> Set[Tuple[str, ...]]:
    return {tuple(map(str, row)) for row in list_of_lists}

def _convert_to_lists(set_of_tuples: Set[Tuple[str, ...]]) -> List[List[str]]:
    return [list(row) for row in set_of_tuples]

class SpreadSheet:
    spreadsheet: Optional[gspread.Spreadsheet] = None
    client: Optional[gspread.Client] = None
    configuration: Optional[Dict[str, str]] = None
    _is_initialized: bool = False
    _config_file_path: Optional[str] = None
    def __init__(self, config_file: str = str(SPREADSHEET_ID_JSON)):
        SpreadSheet._config_file_path = config_file
    @classmethod
    def _ensure_initialized(cls) -> bool:
        if cls._is_initialized:
            return True
        logger.debug("Initializing connection with Google Sheets...")
        if not cls._config_file_path:
            logger.error("Cannot initialize SpreadSheet: Configuration file path not set.")
            return False
        try:
            creds_manager = GrantAccess()
            credentials = creds_manager.refresh_or_obtain_credentials().get_credentials()
            if not credentials:
                logger.error("Failed to obtain Google credentials. Cannot connect to Sheets.")
                return False
            cls.client = gspread.authorize(credentials)
            logger.info("gspread client authorized successfully.")
            try:
                with open(cls._config_file_path, 'r', encoding='utf-8') as file:
                    cls.configuration = json.load(file)
            except FileNotFoundError:
                logger.error(f"Spreadsheet configuration file not found: '{cls._config_file_path}'")
                return False
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON from '{cls._config_file_path}': {e}")
                return False
            if not cls.configuration or 'key' not in cls.configuration:
                logger.error(f"Invalid configuration or missing 'key' in '{cls._config_file_path}'")
                return False
            spreadsheet_key = cls.configuration['key']
            logger.info(f"Attempting to open Google Sheet with key: {spreadsheet_key}")
            cls.spreadsheet = cls.client.open_by_key(spreadsheet_key)
            logger.info(f"Successfully opened Google Sheet: '{cls.spreadsheet.title}' (ID: {spreadsheet_key})")
            cls._is_initialized = True
            return True
        except (SpreadsheetNotFound, APIError) as e:
            key_info = cls.configuration.get('key', 'N/A') if cls.configuration else 'N/A'
            logger.exception(f"Error accessing Google Sheet (Key: {key_info}): {e}")
        except Exception as e:
            logger.exception(f"Unexpected error during SpreadSheet initialization: {e}")
        cls.spreadsheet = None
        cls.client = None
        cls.configuration = None
        cls._is_initialized = False
        return False
    def _get_worksheet(self, sheet_name: str) -> Optional[gspread.Worksheet]:
        if not self._ensure_initialized() or self.spreadsheet is None:
            logger.error(f"Cannot get worksheet '{sheet_name}': SpreadSheet connection not initialized.")
            return None
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            logger.debug(f"Successfully accessed worksheet: '{sheet_name}'")
            return worksheet
        except WorksheetNotFound:
            logger.error(f"Worksheet '{sheet_name}' not found in spreadsheet '{self.spreadsheet.title}'.")
        except APIError as e:
            logger.exception(f"API error accessing worksheet '{sheet_name}': {e}")
        except Exception as e:
            logger.exception(f"Unexpected error getting worksheet '{sheet_name}': {e}")
        return None
    def update_data(self, rows: List[List[Any]], sheet_name: str, replace: bool = False) -> bool:
        worksheet = self._get_worksheet(sheet_name)
        if not worksheet:
            logger.error(f"Cannot update data: Failed to get worksheet '{sheet_name}'.")
            return False
        try:
            value_option = ValueInputOption.user_entered
            if replace:
                logger.info(f"Clearing worksheet '{sheet_name}' before updating...")
                worksheet.clear()
                worksheet.update('A1', rows, value_input_option=value_option)
                logger.info(f"Worksheet '{sheet_name}' cleared and updated with {len(rows)} rows.")
            else:
                worksheet.append_rows(values=rows, value_input_option=value_option)
                logger.info(f"Appended {len(rows)} rows to worksheet '{sheet_name}'.")
            return True
        except APIError as e:
            logger.exception(f"API error updating data in worksheet '{sheet_name}': {e}")
        except Exception as e:
            logger.exception(f"Unexpected error updating data in '{sheet_name}': {e}")
        return False
    def fetch_sheet_values(self, sheet_name: str) -> Optional[List[List[str]]]:
        worksheet = self._get_worksheet(sheet_name)
        if not worksheet:
            logger.error(f"Cannot fetch values: Failed to get worksheet '{sheet_name}'.")
            return None
        try:
            logger.debug(f"Fetching all values from worksheet '{sheet_name}'...")
            values = worksheet.get_all_values()
            logger.info(f"Fetched {len(values)} rows from worksheet '{sheet_name}'.")
            return values
        except APIError as e:
            logger.exception(f"API error fetching values from '{sheet_name}': {e}")
        except Exception as e:
            logger.exception(f"Unexpected error fetching values from '{sheet_name}': {e}")
        return None
    def append_unique_rows(self, rows_to_append: List[List[Any]], sheet_name: str) -> bool:
        worksheet = self._get_worksheet(sheet_name)
        if not worksheet:
            logger.error(f"Cannot append unique rows: Failed to get worksheet '{sheet_name}'.")
            return False
        try:
            logger.debug(f"Fetching existing data from '{sheet_name}' to determine unique rows...")
            existing_data = worksheet.get_all_values()
            existing_rows_set = _convert_to_tuples(existing_data)
            logger.debug(f"Found {len(existing_rows_set)} existing rows in '{sheet_name}'.")
            new_rows_set = _convert_to_tuples(rows_to_append)
            unique_new_rows_set = new_rows_set - existing_rows_set
            unique_rows_to_add = _convert_to_lists(unique_new_rows_set)
            if unique_rows_to_add:
                logger.info(f"Appending {len(unique_rows_to_add)} unique rows to worksheet '{sheet_name}'.")
                worksheet.append_rows(values=unique_rows_to_add, value_input_option=ValueInputOption.user_entered)
            else:
                logger.info(f"No unique new rows found to append to worksheet '{sheet_name}'.")
            return True
        except APIError as e:
            logger.exception(f"API error appending unique rows to '{sheet_name}': {e}")
        except Exception as e:
            logger.exception(f"Unexpected error appending unique rows to '{sheet_name}': {e}")
        return False
