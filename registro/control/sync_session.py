# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Provides a class for interacting with Google Sheets, allowing for updating,
fetching, and appending data.
"""

import json
import logging
from typing import List, Set, Tuple, Optional

import gspread
from google.oauth2.credentials import Credentials
from gspread.exceptions import APIError, WorksheetNotFound, SpreadsheetNotFound

from registro.control.constants import SPREADSHEET_ID_JSON
from registro.control.google_creds import GrantAccess

logger = logging.getLogger(__name__)


def _convert_to_tuples(list_of_lists: list) -> Set[Tuple[str, ...]]:
    """Converts a list of lists to a set of tuples."""
    return set(tuple(row) for row in list_of_lists)


def _convert_to_lists(set_of_tuples: Set[Tuple[str, ...]]) -> List[List[str]]:
    """Converts a set of tuples to a list of lists."""
    return [list(row) for row in set_of_tuples]


class SpreadSheet:
    """
    A class to interact with Google Sheets using the gspread library.

    Provides methods for updating, fetching, and appending data to a
    Google Spreadsheet.
    """
    spreadsheet: gspread.Spreadsheet
    credentials: Credentials
    client: gspread.Client
    configuration: dict

    def __init__(self, config_file: str = SPREADSHEET_ID_JSON):
        """
        Initializes the SpreadSheet object.

        Loads Google Sheets credentials and configuration from the provided file.
        Opens the specified Google Spreadsheet.

        Args:
            config_file (str, optional): Path to the JSON configuration file
                containing the Google Spreadsheet key.
                Defaults to SPREADSHEET_ID_JSON.
        """
        try:
            self.credentials = GrantAccess().reflesh_token().get_credentials()
            self.client = gspread.authorize(self.credentials)

            with open(config_file, 'r', encoding='utf-8') as file:
                self.configuration = json.load(file)

            print(f"Opening Google Spreadsheet: {self.configuration['key']}")

            self.spreadsheet = self.client.open_by_key(
                self.configuration['key'])

        except json.JSONDecodeError as e:
            print(f"Error parsing JSON configuration: {e}")
            raise
        except SpreadsheetNotFound as e:
            print(f"Error opening spreadsheet: {e}")
            raise
        except IOError as e:
            print(f"Error reading configuration file: {e}")
            raise
        except Exception as e:  # pylint: disable=broad-except
            print(f"An unexpected error occurred while opening spreadsheet '{
                self.configuration['key']}'- {type(e).__name__}: {e}")
            raise

    def update_data(self, rows: List[List[str]], sheet_name: str, replace: bool = False) -> bool:
        """
        Updates data in a specific worksheet of the Google Spreadsheet.

        Args:
            rows (List[List[str]]): The list of rows to update or append.
            sheet_name (str): The name of the worksheet to update.
            replace (bool, optional): If True, clears the sheet before updating.
                Defaults to False (appends rows).

        Returns:
            bool: True if the update was successful, False otherwise.
        """
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            if replace:
                worksheet.clear()
                worksheet.update('A1', rows, value_input_option='USER_ENTERED')
                logger.info(
                    "Sheet '%s' data replaced successfully.", sheet_name)
            else:
                worksheet.append_rows(rows, value_input_option='USER_ENTERED')
                logger.info(
                    "Rows appended to sheet '%s' successfully.", sheet_name)
            return True
        except WorksheetNotFound:
            logger.error("Error: Sheet '%s' not found.", sheet_name)
            return False
        except APIError as e:
            logger.error("Error updating sheet '%s': %s", sheet_name, e)
            return False
        except Exception as e:  # pylint: disable=broad-except
            logger.error("An unexpected error occurred while updating sheet '%s' - %s: %s",
                         sheet_name, type(e).__name__, e)
            return False

    def fetch_sheet_values(self, sheet_name: str) -> Optional[List[List[str]]]:
        """
        Fetches all values from a specific worksheet of the Google Spreadsheet.

        Args:
            sheet_name (str): The name of the worksheet to fetch values from.

        Returns:
            Optional[List[List[str]]]: A list of lists representing the sheet's values,
                or None if the sheet is not found or an error occurs.
        """
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            return worksheet.get_all_values()
        except WorksheetNotFound:
            print(f"Error: Sheet '{sheet_name}' not found.")
            return None
        except APIError as e:
            print(f"Error getting values from sheet '{sheet_name}': {e}")
            return None
        except Exception as e:  # pylint: disable=broad-except
            print(f"An unexpected error occurred while getting values from sheet  '{
                sheet_name}'- {type(e).__name__}: {e}")
            return None

    def append_unique_rows(self, rows: List[List[str]], sheet_name: str) -> bool:
        """
        Appends unique rows to a specific worksheet of the Google Spreadsheet.

        Compares the provided rows with existing data and appends only the
        rows that are not already present.

        Args:
            rows (List[List[str]]): The list of rows to append.
            sheet_name (str): The name of the worksheet to append to.

        Returns:
            bool: True if the appending was successful, False otherwise.
        """
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            existing_data = worksheet.get_all_values()
            existing_rows = _convert_to_tuples(existing_data)
            new_rows = _convert_to_tuples(rows)

            unique_rows = _convert_to_lists(new_rows - existing_rows)

            if unique_rows:
                worksheet.append_rows(
                    unique_rows, value_input_option='USER_ENTERED')
                print(
                    f"{len(unique_rows)} unique rows appended to sheet '{sheet_name}'.")
            else:
                print(f"No unique rows to append to sheet '{sheet_name}'.")
            return True

        except WorksheetNotFound:
            print(f"Error: Sheet '{sheet_name}' not found.")
            return False
        except APIError as e:
            print(f"Error appending unique rows to sheet '{sheet_name}': {e}")
            return False
        except Exception as e:  # pylint: disable=broad-except
            print(f"An unexpected error occurred while appending unique rows to sheet '{
                sheet_name}'- {type(e).__name__}: {e}")
            return False
