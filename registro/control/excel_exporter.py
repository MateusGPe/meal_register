# ----------------------------------------------------------------------------
# File: registro/control/excel_exporter.py (Refined Excel Exporter)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
import logging
import os
import re
from pathlib import Path
from typing import List, Optional, Tuple, NamedTuple
import xlsxwriter
from xlsxwriter.exceptions import XlsxWriterException
from registro.control.constants import EXPORT_HEADER
from registro.control.utils import get_documents_path
logger = logging.getLogger(__name__)


class ServedMealRecord(NamedTuple):
    pront: str
    nome: str
    turma: str
    hora_consumo: str
    prato: str


def _sanitize_filename_part(part: str) -> str:

    part = re.sub(r'[\\/*?:\[\]]', '', part)
    part = part.replace(':', '.')

    return part[:30]


def export_to_excel(
    served_meals_data: List[ServedMealRecord],
    meal_type: str,
    session_date: str,
    session_time: str,
) -> Optional[Path]:
    if not served_meals_data:
        logger.warning("No served meals data provided for Excel export. Skipping.")

        return None
    if not all([meal_type, session_date, session_time]):
        logger.error("Insufficient session metadata (meal_type, date, time) provided for Excel export.")
        return None
    output_path: Optional[Path] = None
    try:

        safe_meal_type = _sanitize_filename_part(meal_type)

        safe_date = session_date
        safe_time = _sanitize_filename_part(session_time)
        filename_base = f"{safe_meal_type} {safe_date} {safe_time}.xlsx"
        docs_path_str = get_documents_path()
        docs_path = Path(docs_path_str)

        output_path = docs_path / filename_base

        with xlsxwriter.Workbook(output_path, {'constant_memory': True}) as workbook:

            worksheet_name = _sanitize_filename_part(f"{safe_meal_type}_{safe_date}_{safe_time}")
            worksheet = workbook.add_worksheet(worksheet_name)

            header_format = workbook.add_format(
                {'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1})
            cell_format = workbook.add_format(
                {'border': 1, 'valign': 'vcenter'})

            worksheet.write_row(0, 0, EXPORT_HEADER, header_format)
            worksheet.freeze_panes(1, 0)

            row_idx = 1
            for record in served_meals_data:

                data_row = [
                    record.pront,
                    session_date,
                    record.nome,
                    record.turma,
                    record.prato,
                    record.hora_consumo
                ]

                worksheet.write_row(row_idx, 0, data_row, cell_format)
                row_idx += 1

            worksheet.set_column(0, 0, 12)
            worksheet.set_column(1, 1, 12)
            worksheet.set_column(2, 2, 40)
            worksheet.set_column(3, 3, 25)
            worksheet.set_column(4, 4, 30)
            worksheet.set_column(5, 5, 10)

        logger.info(f"Served meal data successfully exported to {output_path}")
        return output_path
    except (IOError, OSError, XlsxWriterException) as e:
        logger.exception(f"File I/O or XlsxWriter error during Excel export: {e}")

        if output_path and output_path.exists():
            try:
                os.remove(output_path)
                logger.info(f"Removed partial file: {output_path}")
            except OSError as remove_err:
                logger.warning(f"Could not remove partial file {output_path}: {remove_err}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error during Excel export: {e}")
        if output_path and output_path.exists():
            try:
                os.remove(output_path)
                logger.info(f"Removed partial file: {output_path}")
            except OSError as remove_err:
                logger.warning(f"Could not remove partial file {output_path}: {remove_err}")
        return None
