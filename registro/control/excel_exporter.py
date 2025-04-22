# ----------------------------------------------------------------------------
# File: registro/control/excel_exporter.py (Refined Excel Exporter)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Exporta dados de consumo da sessão para uma planilha Excel (.xlsx).
"""

import logging
import os
import re
from typing import List, Optional, Tuple

import xlsxwriter  # Biblioteca para criar arquivos Excel

# Importações locais
from registro.control.constants import EXPORT_HEADER
from registro.control.utils import get_documents_path

logger = logging.getLogger(__name__)


def _sanitize_filename_part(part: str) -> str:
    """ Remove caracteres inválidos para nomes de arquivo/planilha. """
    # Remove caracteres inválidos comuns em nomes de arquivo
    part = re.sub(r'[\\/*?:"<>|]', '', part)
    # Limita o comprimento (útil para nomes de planilha)
    return part[:30]  # Nomes de planilha Excel têm limite de 31 chars


def export_to_excel(
    served_meals_data: List[Tuple[str, str, str, str, str]],
    meal_type: str,
    session_date: str,
    session_time: str,
) -> Optional[str]:
    """
    Exporta os dados dos alunos servidos fornecidos para uma planilha Excel.

    Args:
        served_meals_data (List[Tuple]): Lista de tuplas contendo info dos alunos servidos:
                                         (PRONT, Nome, Turma, HoraConsumo, Refeição/Prato).
        meal_type (str): O tipo de refeição (ex: 'Almoço', 'Lanche').
        session_date (str): A data da sessão (ex: 'YYYY-MM-DD').
        session_time (str): A hora da sessão (ex: 'HH:MM').

    Returns:
        Optional[str]: O caminho absoluto para o arquivo Excel criado se sucesso, None caso contrário.
    """
    if not all([served_meals_data, meal_type, session_date, session_time]):
        logger.error("Dados insuficientes fornecidos para exportação Excel.")
        return None

    output_path: Optional[str] = None
    try:
        # --- Prepara nome do arquivo e caminho ---
        safe_meal_type = _sanitize_filename_part(meal_type)
        # Substitui separadores de data
        safe_date = session_date.replace('/', '-').replace('\\', '-')
        # Substitui ':' por '.' para nome de arquivo
        safe_time = session_time.replace(':', '.')
        filename_base = f"{safe_meal_type} {safe_date} {safe_time}.xlsx"

        docs_path = get_documents_path()  # Obtém caminho da pasta Documentos
        # O get_documents_path já garante que o diretório exista
        output_path = os.path.join(docs_path, filename_base)

        # --- Cria o Workbook e Worksheet ---
        # Usa 'constant_memory' para otimizar uso de memória com muitos dados
        workbook = xlsxwriter.Workbook(output_path, {'constant_memory': True})
        # Usa nome sanitizado e limitado para a planilha
        worksheet_name = _sanitize_filename_part(
            f"{safe_meal_type} {safe_date} {safe_time}")
        worksheet = workbook.add_worksheet(worksheet_name)

        # --- Formatação (Opcional) ---
        header_format = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1})
        cell_format = workbook.add_format(
            {'border': 1})  # Formato básico com borda

        # --- Escreve Cabeçalho ---
        worksheet.write_row(0, 0, EXPORT_HEADER, header_format)
        worksheet.freeze_panes(1, 0)  # Congela a linha do cabeçalho

        # --- Escreve Dados ---
        # (Matrícula, Data, Nome, Turma, Refeição, Hora)
        row_idx = 1  # Começa da segunda linha (após cabeçalho)
        for item in served_meals_data:
            # Extrai dados da tupla (assumindo formato correto)
            pront, nome, turma, hora_consumo, prato = item
            # Monta a linha na ordem do EXPORT_HEADER
            data_row = [pront, session_date, nome, turma, prato, hora_consumo]
            # Escreve a linha inteira com formato de célula padrão
            worksheet.write_row(row_idx, 0, data_row, cell_format)
            row_idx += 1

        # --- Ajusta Largura das Colunas (Opcional, mas recomendado) ---
        # Formato: worksheet.set_column(first_col, last_col, width)
        worksheet.set_column(0, 0, 12)  # Matrícula
        worksheet.set_column(1, 1, 12)  # Data
        worksheet.set_column(2, 2, 40)  # Nome
        worksheet.set_column(3, 3, 25)  # Turma
        worksheet.set_column(4, 4, 30)  # Refeição/Prato
        worksheet.set_column(5, 5, 10)  # Hora

        # --- Fecha Workbook (Salva o arquivo) ---
        workbook.close()
        logger.info(f"Dados exportados com sucesso para {output_path}")
        return output_path

    except (IOError, OSError, xlsxwriter.exceptions.XlsxWriterException) as e:
        logger.exception(
            f"Erro de I/O ou XlsxWriter ao exportar para Excel: {e}")
        # Tenta remover arquivo parcial se existir e falhou
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                logger.warning(
                    f"Não foi possível remover arquivo parcial: {output_path}")
        return None
    except Exception as e:  # Captura qualquer outro erro inesperado
        logger.exception(f"Erro inesperado durante exportação para Excel: {e}")
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                logger.warning(
                    f"Não foi possível remover arquivo parcial: {output_path}")
        return None
