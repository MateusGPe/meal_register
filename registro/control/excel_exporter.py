# ----------------------------------------------------------------------------
# File: registro/control/excel_exporter.py (Exportador Excel Refinado)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Fornece funcionalidade para exportar os dados de refeições servidas em uma
sessão para um arquivo Excel (.xlsx), formatado com cabeçalhos e estilos básicos.
"""
import logging
import os
import re
from pathlib import Path
from typing import NamedTuple, Optional, Sequence

import xlsxwriter
from xlsxwriter.exceptions import XlsxWriterException

# Importações locais
from registro.control.constants import EXPORT_HEADER
from registro.control.utils import get_documents_path

logger = logging.getLogger(__name__)

# Define uma estrutura para os dados de refeição servida (melhora a clareza)


class ServedMealRecord(NamedTuple):
    """ Representa uma linha de dados de refeição servida para exportação. """
    pront: str
    nome: str
    turma: str
    hora_consumo: str
    prato: str


def _sanitize_filename_part(part: str) -> str:
    """
    Remove caracteres inválidos para nomes de arquivo/aba e trunca.

    Args:
        part: A string a ser sanitizada (ex: tipo de refeição, hora).

    Returns:
        A string sanitizada e truncada.
    """
    # Remove caracteres inválidos em nomes de arquivo Windows/Linux comuns
    part = re.sub(r'[\\/*?:"<>|\[\]]', '', part)
    # Substitui ':' por '.' (comum em horas)
    part = part.replace(':', '.')
    # Trunca para evitar nomes excessivamente longos (limite comum em alguns sistemas)
    return part[:30]


def export_to_excel(
    served_meals_data: Sequence[ServedMealRecord],
    meal_type: str,
    session_date: str,  # Formato YYYY-MM-DD
    session_time: str,  # Formato HH.MM (após sanitização) ou HH:MM
) -> Optional[Path]:
    """
    Exporta uma sequência de registros de refeições servidas para um arquivo Excel.

    O arquivo é salvo na pasta 'Documentos' do usuário, com nome baseado no
    tipo de refeição, data e hora da sessão.

    Args:
        served_meals_data: Uma sequência (lista, tupla) de objetos ServedMealRecord.
        meal_type: O tipo de refeição (ex: "Almoço", "Lanche").
        session_date: A data da sessão (formato YYYY-MM-DD).
        session_time: A hora de início da sessão (formato HH:MM ou similar).

    Returns:
        O Path para o arquivo Excel criado se a exportação for bem-sucedida,
        ou None se ocorrer um erro ou não houver dados para exportar.
    """
    # Validação inicial dos dados
    if not served_meals_data:
        logger.warning("Nenhum dado de refeição servida fornecido para exportação Excel. Pulando.")
        return None
    if not all([meal_type, session_date, session_time]):
        logger.error("Metadados da sessão insuficientes (tipo, data, hora)"
                     " fornecidos para exportação Excel.")
        return None

    output_path: Optional[Path] = None  # Caminho do arquivo a ser criado
    workbook: Optional[xlsxwriter.Workbook] = None  # Objeto Workbook

    try:
        # --- Preparação do Nome do Arquivo e Caminho ---
        safe_meal_type = _sanitize_filename_part(meal_type)
        safe_date = session_date  # YYYY-MM-DD já é seguro para nome de arquivo
        safe_time = _sanitize_filename_part(session_time)  # Transforma HH:MM em HH.MM

        # Monta o nome base do arquivo
        filename_base = f"{safe_meal_type} {safe_date} {safe_time}.xlsx"

        # Obtém o caminho para a pasta 'Documentos'
        docs_path_str = get_documents_path()
        docs_path = Path(docs_path_str)

        # Define o caminho completo do arquivo de saída
        output_path = docs_path / filename_base

        # --- Criação e Escrita do Arquivo Excel ---
        logger.info("Iniciando exportação Excel para: %s", output_path)
        # Usa gerenciador de contexto para garantir fechamento do workbook
        # 'constant_memory' é útil para arquivos grandes, mas pode ser mais lento
        workbook = xlsxwriter.Workbook(output_path, {'constant_memory': True})

        # Cria a aba (worksheet) - nome também sanitizado
        worksheet_name = _sanitize_filename_part(f"{safe_meal_type}_{safe_date}_{safe_time}")
        worksheet = workbook.add_worksheet(worksheet_name)

        # --- Formatação ---
        # Formato para o cabeçalho (negrito, centralizado, borda)
        header_format = workbook.add_format(
            {'bold': True, 'align': 'center', 'valign': 'vcenter', 'border': 1})
        # Formato padrão para as células de dados (alinhamento vertical, borda)
        cell_format = workbook.add_format(
            {'border': 1, 'valign': 'vcenter'})

        # --- Escrita dos Dados ---
        # Escreve o cabeçalho na primeira linha
        worksheet.write_row(0, 0, EXPORT_HEADER, header_format)
        # Congela a primeira linha (cabeçalho)
        worksheet.freeze_panes(1, 0)

        # Itera sobre os dados das refeições servidas e escreve cada linha
        row_idx = 1  # Começa na segunda linha (índice 1)
        for record in served_meals_data:
            # Monta a tupla de dados na ordem definida por EXPORT_HEADER
            data_row = (
                record.pront,
                session_date,  # Usa a data da sessão para todas as linhas
                record.nome,
                record.turma,
                record.prato,
                record.hora_consumo
            )
            worksheet.write_row(row_idx, 0, data_row, cell_format)
            row_idx += 1

        # --- Ajuste de Largura das Colunas ---
        # Ajusta a largura das colunas para melhor visualização
        worksheet.set_column(0, 0, 12)  # Matrícula
        worksheet.set_column(1, 1, 12)  # Data
        worksheet.set_column(2, 2, 40)  # Nome
        worksheet.set_column(3, 3, 25)  # Turma
        worksheet.set_column(4, 4, 30)  # Refeição/Prato
        worksheet.set_column(5, 5, 10)  # Hora

        # O workbook é salvo automaticamente ao sair do bloco 'with'

        logger.info("Dados de refeições servidas exportados com sucesso para %s", output_path)
        return output_path

    # Tratamento de erros específicos de I/O e XlsxWriter
    except (IOError, OSError, XlsxWriterException) as e:
        logger.exception("Erro de I/O ou XlsxWriter durante exportação Excel: %s", e)
        # Tenta remover arquivo parcial se ele foi criado
        if output_path and output_path.exists():
            try:
                os.remove(output_path)
                logger.info("Arquivo parcial removido: %s", output_path)
            except OSError as remove_err:
                logger.warning("Não foi possível remover arquivo parcial %s: %s",
                               output_path, remove_err)
        return None  # Indica falha na exportação
    # Tratamento de outros erros inesperados
    except Exception as e:
        logger.exception("Erro inesperado durante exportação Excel: %s", e)
        # Tenta remover arquivo parcial
        if output_path and output_path.exists():
            try:
                os.remove(output_path)
                logger.info("Arquivo parcial removido: %s", output_path)
            except OSError as remove_err:
                logger.warning("Não foi possível remover arquivo parcial %s: %s",
                               output_path, remove_err)
        return None  # Indica falha
    finally:
        # Garante que o workbook seja fechado mesmo se ocorrerem exceções
        # dentro do bloco 'with' (embora o 'with' já faça isso).
        # Isso é mais relevante se não estivéssemos usando 'with'.
        if workbook:
            try:
                # workbook.close() # Com 'with', isso é chamado automaticamente
                pass
            except Exception as close_err:
                logger.error(
                    "Erro adicional ao fechar workbook (pode já estar fechado): %s", close_err)
