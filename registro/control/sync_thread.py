# ----------------------------------------------------------------------------
# File: registro/control/sync_thread.py (Threading Wrappers for Sync Ops)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

import logging
from threading import Thread
from typing import Optional, List, Any
from registro.control.constants import (
    RESERVES_CSV_PATH, RESERVES_SHEET_NAME,
    STUDENTS_CSV_PATH, STUDENTS_SHEET_NAME,
    EXPORT_HEADER
)
from registro.control.reserves import import_reserves_csv, import_students_csv
from registro.control.session_manage import SessionManager
from registro.control.utils import save_csv_from_list
logger = logging.getLogger(__name__)


class BaseSyncThread(Thread):

    def __init__(self, session_manager: SessionManager):

        super().__init__(daemon=True)
        self._session_manager = session_manager
        self.error: Optional[Exception] = None
        self.success: bool = False

    def run(self):
        thread_name = self.__class__.__name__
        try:
            logger.info(f"Starting thread: {thread_name}")
            self._run_logic()

            self.success = self.error is None
            if self.success:
                logger.info(f"Thread {thread_name} completed successfully.")
            else:

                logger.error(f"Thread {thread_name} finished with error: {self.error}")
        except Exception as e:

            logger.exception(f"Unhandled error in thread {thread_name}: {e}")
            self.error = e
            self.success = False

    def _run_logic(self):
        raise NotImplementedError("Subclasses must implement the _run_logic method.")


class SpreadsheetThread(BaseSyncThread):
    def _run_logic(self):
        logger.info("SpreadsheetThread: Starting upload of served meals.")

        spreadsheet = self._session_manager.get_spreadsheet()
        if not spreadsheet:
            logger.error("SpreadsheetThread: Cannot proceed, SpreadSheet instance is unavailable.")
            self.error = ValueError("SpreadSheet instance not available.")
            return

        served_meals = self._session_manager.get_served_students_details()
        if not served_meals:
            logger.info("SpreadsheetThread: No served students found in the current session. Nothing to upload.")

            return

        meal_type = self._session_manager.get_meal_type()
        sheet_name = (meal_type or "Unknown").capitalize()
        session_date = self._session_manager.get_date()
        if not meal_type or not session_date:
            logger.error("SpreadsheetThread: Cannot determine target sheet name or session date.")
            self.error = ValueError("Meal type or session date is missing.")
            return
        logger.debug(f"SpreadsheetThread: Target sheet name: '{sheet_name}', Session date: {session_date}")

        rows_to_add: List[List[Any]] = []

        for pront, nome, turma, hora, prato_status in served_meals:

            simplified_turma = turma.split(',')[0].strip() if ',' in turma else turma
            rows_to_add.append([
                str(pront),
                str(session_date),
                str(nome),
                str(simplified_turma),
                str(prato_status),
                str(hora)
            ])
        if rows_to_add:
            logger.info(
                f"SpreadsheetThread: Attempting to append {len(rows_to_add)} unique rows to sheet '{sheet_name}'.")

            success = spreadsheet.append_unique_rows(rows_to_add, sheet_name)
            if not success:

                logger.error(f"SpreadsheetThread: Failed to append unique rows to sheet '{sheet_name}'.")
                self.error = RuntimeError(f"Failed to append rows to Google Sheet '{sheet_name}'. Check logs.")

        else:

            logger.info("SpreadsheetThread: No rows formatted for adding to the sheet.")


class SyncReserves(BaseSyncThread):
    def _run_logic(self):
        logger.info("SyncReserves: Starting synchronization from Google Sheets to local DB.")
        spreadsheet = self._session_manager.get_spreadsheet()
        if not spreadsheet:
            logger.error("SyncReserves: Cannot proceed, SpreadSheet instance is unavailable.")
            self.error = ValueError("SpreadSheet instance not available.")
            return

        logger.info(f"SyncReserves: Fetching student data from sheet '{STUDENTS_SHEET_NAME}'...")
        students_data = spreadsheet.fetch_sheet_values(STUDENTS_SHEET_NAME)
        if students_data is None:
            logger.error(
                f"SyncReserves: Failed to fetch data from student sheet '{STUDENTS_SHEET_NAME}'. Aborting sync.")
            self.error = RuntimeError(f"Failed to fetch data from sheet '{STUDENTS_SHEET_NAME}'.")
            return
        if not students_data or len(students_data) <= 1:
            logger.warning(
                f"SyncReserves: Student sheet '{STUDENTS_SHEET_NAME}' is empty or contains only headers. Skipping student import.")

        else:
            logger.info(
                f"SyncReserves: Saving {len(students_data)} rows from student sheet to '{STUDENTS_CSV_PATH}'...")

            if save_csv_from_list(students_data, str(STUDENTS_CSV_PATH)):
                logger.info(f"SyncReserves: Student data saved to CSV. Importing to database...")

                if not import_students_csv(self._session_manager.student_crud,
                                           self._session_manager.turma_crud,
                                           str(STUDENTS_CSV_PATH)):
                    logger.error("SyncReserves: Failed to import student data from CSV to database. Aborting sync.")
                    self.error = RuntimeError("Failed to import students from CSV.")
                    return
                logger.info("SyncReserves: Student data imported successfully.")
            else:
                logger.error(f"SyncReserves: Failed to save student data to CSV '{STUDENTS_CSV_PATH}'. Aborting sync.")
                self.error = RuntimeError(f"Failed to save students to CSV '{STUDENTS_CSV_PATH}'.")
                return

        logger.info(f"SyncReserves: Fetching reservation data from sheet '{RESERVES_SHEET_NAME}'...")
        reserves_data = spreadsheet.fetch_sheet_values(RESERVES_SHEET_NAME)
        if reserves_data is None:
            logger.error(
                f"SyncReserves: Failed to fetch data from reserves sheet '{RESERVES_SHEET_NAME}'. Aborting sync.")
            self.error = RuntimeError(f"Failed to fetch data from sheet '{RESERVES_SHEET_NAME}'.")
            return
        if not reserves_data or len(reserves_data) <= 1:
            logger.warning(
                f"SyncReserves: Reserves sheet '{RESERVES_SHEET_NAME}' is empty or contains only headers. Skipping reserves import.")

        else:
            logger.info(
                f"SyncReserves: Saving {len(reserves_data)} rows from reserves sheet to '{RESERVES_CSV_PATH}'...")

            if save_csv_from_list(reserves_data, str(RESERVES_CSV_PATH)):
                logger.info(f"SyncReserves: Reservation data saved to CSV. Importing to database...")

                if not import_reserves_csv(self._session_manager.student_crud,
                                           self._session_manager.reserve_crud,
                                           str(RESERVES_CSV_PATH)):
                    logger.error("SyncReserves: Failed to import reservation data from CSV to database. Aborting sync.")
                    self.error = RuntimeError("Failed to import reserves from CSV.")
                    return
                logger.info("SyncReserves: Reservation data imported successfully.")
            else:
                logger.error(
                    f"SyncReserves: Failed to save reservation data to CSV '{RESERVES_CSV_PATH}'. Aborting sync.")
                self.error = RuntimeError(f"Failed to save reserves to CSV '{RESERVES_CSV_PATH}'.")
                return

        logger.info("SyncReserves: Synchronization process completed.")
