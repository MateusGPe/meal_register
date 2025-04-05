# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Exports session consumption data to an Excel spreadsheet.
"""

import os
from typing import List, Optional, Tuple

import xlsxwriter

from registro.control.utils import get_documments_path


def export_to_excel(
    served_meals_data: List[Tuple[str, str, str, str, str]],
    meal_type: str,
    session_date: str,
    session_time: str,
) -> Optional[str]:
    """
    Exports the provided served students data to an Excel spreadsheet.

    Args:
        served_meals_data (List[Tuple]): List of tuples containing served student info:
                                         (PRONT, Nome, Turma, HoraConsumo, Refeição/Prato).
        meal_type (str): The type of meal (e.g., 'Almoço', 'Lanche').
        session_date (str): The date of the session (e.g., 'YYYY/MM/DD').
        session_time (str): The time of the session (e.g., 'HH:MM').

    Returns:
        bool: True if the export was successful, False otherwise.
    """
    if not all([served_meals_data, meal_type, session_date, session_time]):
        print("Error: Missing data for Excel export.")
        return None

    try:
        # Sanitize filename components
        safe_meal_type = meal_type.replace(" ", "_").lower()
        safe_date = session_date.replace('/', '-')
        safe_time = session_time.replace(':', '.')
        base_filename = f"{safe_meal_type}_{safe_date}_{safe_time}.xlsx"

        # Ensure the documents directory exists
        docs_path = get_documments_path()
        os.makedirs(docs_path, exist_ok=True)  # Create if it doesn't exist

        last_exported_path = os.path.join(docs_path, base_filename)

        workbook = xlsxwriter.Workbook(last_exported_path)
        # Use a slightly shorter name for the worksheet if filename is too long
        worksheet_name = f"{meal_type} {safe_date} {safe_time}"[
            :31]  # Excel limit
        worksheet = workbook.add_worksheet(worksheet_name)

        # Define header
        header = ["Matrícula", "Data", "Nome", "Turma", "Refeição", "Hora"]
        # Optional: Add formatting for header
        header_format = workbook.add_format({'bold': True})

        # Write header
        for hcol, item in enumerate(header):
            # Use row 0 for header
            worksheet.write(0, hcol, item, header_format)

        # Write data rows
        # Start data from row 1
        for row_idx, item in enumerate(served_meals_data, start=1):
            # Ensure item has the expected number of elements
            if len(item) == 5:  # (PRONT, Nome, Turma, HoraConsumo, Refeição/Prato)
                pront, nome, turma, hora, refeicao = item
                worksheet.write(row_idx, 0, pront)      # Matrícula
                # Data (Session Date)
                worksheet.write(row_idx, 1, session_date)
                worksheet.write(row_idx, 2, nome)        # Nome
                worksheet.write(row_idx, 3, turma)       # Turma
                worksheet.write(row_idx, 4, refeicao)    # Refeição
                # Hora (Consumption Time)
                worksheet.write(row_idx, 5, hora)
            else:
                print(
                    f"Warning: Skipping row {row_idx} due to unexpected data format: {item}")

        # Optional: Adjust column widths
        worksheet.set_column('A:A', 12)  # Matrícula
        worksheet.set_column('B:B', 12)  # Data
        worksheet.set_column('C:C', 30)  # Nome
        worksheet.set_column('D:D', 20)  # Turma
        worksheet.set_column('E:E', 15)  # Refeição
        worksheet.set_column('F:F', 10)  # Hora

        workbook.close()
        print(f"Successfully exported data to {last_exported_path}")
        return last_exported_path

    except (IOError, ValueError, xlsxwriter.exceptions.XlsxWriterException) as e:
        print(f"Error exporting to Excel: {e}")
        last_exported_path = None
        return None
    except Exception as e:  # pylint: disable=broad-except
        print(f"An unexpected error occurred during Excel export: {e}")
        last_exported_path = None
        return None
