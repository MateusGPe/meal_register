# ----------------------------------------------------------------------------
# File: registro/control/sync_thread.py (Refined Threading Wrappers)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Fornece classes de Thread para sincronização de dados com Planilhas Google
e importação local de dados de alunos e reservas a partir de CSVs.
"""

import logging
from threading import Thread
from typing import Optional

# Importações locais
from registro.control.constants import (RESERVES_CSV_PATH, RESERVES_SHEET_NAME,
                                        STUDENTS_CSV_PATH, STUDENTS_SHEET_NAME,
                                        EXPORT_HEADER) # EXPORT_HEADER usado em SpreadsheetThread
from registro.control.reserves import import_reserves_csv, import_students_csv
from registro.control.session_manage import SessionManager
from registro.control.utils import save_csv_from_list # Renomeado para clareza

logger = logging.getLogger(__name__)

class BaseSyncThread(Thread):
    """ Classe base para threads de sincronização com manejo de erro. """
    def __init__(self, session_manager: SessionManager):
        super().__init__(daemon=True) # Roda como daemon para não impedir fechamento da app
        self._session_manager = session_manager
        self.error: Optional[Exception] = None # Armazena exceção se ocorrer
        self.success: bool = False # Indica sucesso geral

    def run(self):
        """ Método principal da thread, com tratamento de erro genérico. """
        try:
            logger.info(f"Iniciando thread: {self.__class__.__name__}")
            self._run_logic()
            self.success = self.error is None # Sucesso se nenhuma exceção foi capturada
            if self.success:
                 logger.info(f"Thread {self.__class__.__name__} concluída com sucesso.")
            else:
                 logger.error(f"Thread {self.__class__.__name__} concluída com erro: {self.error}")
        except Exception as e:
            logger.exception(f"Erro não capturado na thread {self.__class__.__name__}: {e}")
            self.error = e
            self.success = False

    def _run_logic(self):
        """ Método a ser implementado pelas subclasses com a lógica específica. """
        raise NotImplementedError("Subclasses devem implementar _run_logic")

class SpreadsheetThread(BaseSyncThread):
    """
    Thread para adicionar dados de refeições servidas a uma Planilha Google.
    """
    def _run_logic(self):
        """ Adiciona refeições servidas à planilha online. """
        spreadsheet = self._session_manager.get_spreadsheet()
        if not spreadsheet:
            self.error = ValueError("Instância SpreadSheet não disponível.")
            return

        served_meals = self._session_manager.get_served_students()
        if not served_meals:
            logger.info("SpreadsheetThread: Nenhum aluno servido para enviar.")
            # Considera sucesso pois não há o que fazer
            self.success = True
            self.error = None
            return

        sheet_name = (self._session_manager.get_meal_type() or "Desconhecido").capitalize()
        session_date = self._session_manager.get_date()
        if not sheet_name or not session_date:
            self.error = ValueError("Tipo de refeição ou data da sessão indisponível.")
            return

        rows_to_add = []
        # Formata dados na ordem do EXPORT_HEADER:
        # ["Matrícula", "Data", "Nome", "Turma", "Refeição", "Hora"]
        for pront, nome, turma, hora, prato in served_meals:
            # Simplifica seleção de turma (pode precisar de ajuste fino)
            simplified_turma = turma.split(',')[0] if ',' in turma else turma
            rows_to_add.append([
                str(pront), str(session_date), str(nome),
                str(simplified_turma), str(prato), str(hora)
            ])

        if rows_to_add:
            logger.info(f"Enviando {len(rows_to_add)} registros servidos para planilha '{sheet_name}'...")
            # Tenta adicionar apenas linhas únicas
            if not spreadsheet.append_unique_rows(rows_to_add, sheet_name):
                # Define erro se append_unique_rows falhar (retornar False)
                self.error = RuntimeError(f"Falha ao adicionar linhas únicas à planilha '{sheet_name}'. Verifique logs do SpreadSheet.")
                # Não define self.success aqui, deixa o handler genérico fazer isso
        else:
             logger.info("Nenhuma linha formatada para adicionar à planilha.")
             self.success = True # Sucesso se não havia nada a adicionar

class SyncReserves(BaseSyncThread):
    """
    Thread para sincronizar dados de alunos e reservas da Planilha Google
    para o banco de dados local (via arquivos CSV intermediários).
    """
    def _run_logic(self):
        """ Busca dados da planilha, salva em CSV e importa para o DB. """
        spreadsheet = self._session_manager.get_spreadsheet()
        if not spreadsheet:
            self.error = ValueError("Instância SpreadSheet não disponível.")
            return

        # 1. Sincronizar Alunos (Discentes)
        logger.info("Sincronizando dados dos alunos (Discentes)...")
        students_data = spreadsheet.fetch_sheet_values(STUDENTS_SHEET_NAME)
        if students_data is None: # Erro ao buscar
            self.error = RuntimeError(f"Falha ao buscar dados da planilha '{STUDENTS_SHEET_NAME}'.")
            return
        if not students_data or len(students_data) <= 1: # Vazio ou só cabeçalho
             logger.warning(f"Planilha '{STUDENTS_SHEET_NAME}' vazia ou sem dados válidos.")
             # Continua para reservas, mas marca que pode não ser sucesso total? Ou considera sucesso?
             # Por ora, continua.
        else:
            # Salva em CSV
            if save_csv_from_list(students_data, STUDENTS_CSV_PATH):
                logger.info(f"Dados de alunos salvos em '{STUDENTS_CSV_PATH}'. Iniciando importação...")
                # Importa do CSV para o DB
                if not import_students_csv(self._session_manager.student_crud,
                                           self._session_manager.turma_crud,
                                           STUDENTS_CSV_PATH):
                    self.error = RuntimeError("Falha ao importar alunos do CSV para o banco de dados.")
                    return # Aborta se a importação de alunos falhar
                logger.info("Importação de alunos concluída.")
            else:
                self.error = RuntimeError(f"Falha ao salvar dados dos alunos em '{STUDENTS_CSV_PATH}'.")
                return # Aborta se não conseguir salvar CSV

        # 2. Sincronizar Reservas (DB sheet)
        logger.info("Sincronizando dados das reservas (DB)...")
        reserves_data = spreadsheet.fetch_sheet_values(RESERVES_SHEET_NAME)
        if reserves_data is None: # Erro ao buscar
            self.error = RuntimeError(f"Falha ao buscar dados da planilha '{RESERVES_SHEET_NAME}'.")
            return
        if not reserves_data or len(reserves_data) <= 1:
            logger.warning(f"Planilha '{RESERVES_SHEET_NAME}' vazia ou sem dados válidos.")
            # Considera sucesso se não há reservas para importar
        else:
             # Salva em CSV
             if save_csv_from_list(reserves_data, RESERVES_CSV_PATH):
                  logger.info(f"Dados de reservas salvos em '{RESERVES_CSV_PATH}'. Iniciando importação...")
                  # Importa do CSV para o DB
                  if not import_reserves_csv(self._session_manager.student_crud,
                                             self._session_manager.reserve_crud,
                                             RESERVES_CSV_PATH):
                       self.error = RuntimeError("Falha ao importar reservas do CSV para o banco de dados.")
                       return # Aborta se a importação de reservas falhar
                  logger.info("Importação de reservas concluída.")
             else:
                  self.error = RuntimeError(f"Falha ao salvar dados das reservas em '{RESERVES_CSV_PATH}'.")
                  return # Aborta se não conseguir salvar CSV

        # Se chegou aqui sem erros, marca como sucesso
        if self.error is None:
            self.success = True