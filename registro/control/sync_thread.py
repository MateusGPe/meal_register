# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Provides threading classes for synchronizing data with a spreadsheet
and importing reserves and students from a spreadsheet.
"""

from threading import Thread

from registro.control.constants import (RESERVES_CSV_PATH, RESERVES_SHEET_NAME,
                                        STUDENTS_CSV_PATH, STUDENTS_SHEET_NAME)
from registro.control.reserves import import_reserves_csv, import_students_csv
from registro.control.session_manage import SessionManager
from registro.control.utils import save_csv


class SpreadsheetThread(Thread):
    """
    A thread class for appending served meals data to a Google Spreadsheet.

    This thread retrieves the served students from the session manager and
    appends their information to the specified sheet in the Google Spreadsheet.
    """

    def __init__(self, session_data: SessionManager):
        """
        Initializes the SpreadsheetThread.

        Args:
            session_data (SessionManager): An instance of SessionManager
                containing the current session's data.
        """
        super().__init__()
        self._session = session_data
        self.error = True

    def run(self):
        """
        Executes the thread's main logic: appending served meals to the sheet.

        Retrieves served meals data, formats it into rows, and appends
        the unique rows to the Google Spreadsheet. Sets the 'error' attribute
        to indicate success or failure.
        """
        served_meals = self._session.get_served_students()
        if not served_meals:
            print("Error: Invalid session data provided for upload.")
            self.error = True
            return

        sheet_name = self._session.get_meal_type().capitalize()
        if not sheet_name:
            print("Error: 'refeição' not found in metadata to determine sheet name.")
            return

        rows_to_add = []
        for student in served_meals:
            try:
                classes = student[2]
                if 'MEC' in student[2] or 'MAC' in student[2]:
                    classes = classes.split(',')
                    classes = next(
                        c for c in classes if 'MEC' in c or 'MAC' in c)

                row = [
                    str(student[0]),
                    str(self._session.get_date()),
                    str(student[1]),
                    str(classes),
                    str(student[4]),
                    str(student[3])
                ]
                rows_to_add.append(row)
            except IndexError as e:
                print(f"Error processing student item: {student}. Error: {e}")
                return
        if rows_to_add:
            self.error = not self._session.get_spreadsheet().append_unique_rows(
                rows_to_add, sheet_name)
        else:
            self.error = False
        return


class SyncReserves(Thread):
    """
    A thread class for synchronizing student and reserve data from a
    Google Spreadsheet to the local database.

    This thread fetches data from the "Discentes" and "DB" sheets, saves
    it to CSV files, and then imports this data into the respective
    database tables.
    """

    def __init__(self, session_data: SessionManager):
        """
        Initializes the SyncReserves thread.

        Args:
            session_data (SessionManager): An instance of SessionManager
                providing access to the database CRUD operations and the
                Google Spreadsheet.
        """
        super().__init__()
        self._session = session_data
        self.error = True

    def run(self):
        """
        Executes the thread's main logic: fetching and importing data.

        Fetches student data from the "Discentes" sheet, saves it to a CSV
        file, and imports it into the students table. Then, fetches reserve
        data from the "DB" sheet, saves it to a CSV file, and imports it into
        the reserves table. Sets the 'error' attribute to indicate success.
        """
        discentes_list = self._session.get_spreadsheet(
        ).fetch_sheet_values(STUDENTS_SHEET_NAME)
        if discentes_list:
            if save_csv(discentes_list, STUDENTS_CSV_PATH):
                import_students_csv(
                    self._session.student_crud,
                    self._session.turma_crud,
                    STUDENTS_CSV_PATH)
            self.error = False

        reserves_list = self._session.get_spreadsheet(
        ).fetch_sheet_values(RESERVES_SHEET_NAME)
        if reserves_list:
            if save_csv(reserves_list, RESERVES_CSV_PATH):
                import_reserves_csv(self._session.student_crud,
                                    self._session.reserve_crud,
                                    RESERVES_CSV_PATH)
            self.error = False or self.error
