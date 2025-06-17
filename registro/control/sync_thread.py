# ----------------------------------------------------------------------------
# File: registro/control/sync_thread.py (Threads para Operações de Sincronização)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Define classes de Thread para executar operações de sincronização demoradas
(com Google Sheets) em segundo plano, evitando que a interface principal
trave. Inclui threads para sincronizar refeições servidas e para sincronizar
dados mestre (alunos e reservas).
"""
import logging
from threading import Thread
from typing import Any, List, Optional

# Importações locais
from registro.control.constants import (  # Textos para logs/mensagens
    RESERVES_CSV_PATH,
    RESERVES_SHEET_NAME,
    STUDENTS_CSV_PATH,
    STUDENTS_SHEET_NAME,
)
from registro.control.reserves import (  # Funções de importação
    import_reserves_csv,
    import_students_csv,
)
from registro.control.session_manage import SessionManager  # Fachada do controle
from registro.control.utils import save_csv_from_list  # Utilitário CSV

logger = logging.getLogger(__name__)


class BaseSyncThread(Thread):
    """
    Classe base abstrata para threads de sincronização.

    Fornece estrutura básica com gerenciamento de estado (sucesso/erro)
    e delega a lógica específica para o método `_run_logic`.
    """

    def __init__(self, session_manager: SessionManager):
        """
        Inicializa a thread base.

        Args:
            session_manager: A instância do SessionManager para acesso aos
                             dados e funcionalidades de controle.
        """
        super().__init__(
            daemon=True
        )  # Define como daemon para não impedir app de fechar
        self._session_manager = session_manager
        self.error: Optional[Exception] = None  # Armazena exceção se ocorrer erro
        self.success: bool = False  # Indica se a thread concluiu sem erros

    def run(self):
        """
        Método principal executado pela thread.
        Envolve a chamada de `_run_logic` em um bloco try-except.
        """
        thread_name = (
            self.__class__.__name__
        )  # Nome da classe filha (ex: SpreadsheetThread)
        try:
            logger.info("Iniciando thread: %s", thread_name)
            self._run_logic()  # Executa a lógica específica da subclasse
            # Define sucesso baseado na ausência de erro após _run_logic
            self.success = self.error is None
            if self.success:
                logger.info("Thread %s concluída com sucesso.", thread_name)
            else:
                logger.error(
                    "Thread %s finalizada com erro: %s", thread_name, self.error
                )
        except Exception as e:
            # Captura erros não tratados dentro de _run_logic
            logger.exception("Erro não tratado na thread %s: %s", thread_name, e)
            self.error = e
            self.success = False

    def _run_logic(self):
        """
        Método abstrato a ser implementado pelas subclasses.
        Contém a lógica de sincronização específica da thread.

        Raises:
            NotImplementedError: Se a subclasse não implementar este método.
        """
        raise NotImplementedError("Subclasses devem implementar o método _run_logic.")


class SpreadsheetThread(BaseSyncThread):
    """
    Thread para sincronizar (fazer upload) os dados de refeições servidas
    na sessão atual para a planilha Google Sheets configurada.
    """

    def _run_logic(self):
        """
        Busca os alunos servidos, formata os dados e os envia para a planilha
        Google Sheets usando `append_unique_rows`.
        """
        logger.info("SpreadsheetThread: Iniciando upload de refeições servidas.")
        spreadsheet = self._session_manager.get_spreadsheet()

        # Obtém a instância do SpreadSheet (wrapper gspread)
        if not spreadsheet:
            logger.error(
                "SpreadsheetThread: Não é possível prosseguir, instância SpreadSheet indisponível."
            )
            self.error = ValueError("Instância SpreadSheet não disponível.")
            return  # Encerra a execução da thread

        # Busca os detalhes dos alunos servidos na sessão atual
        served_meals = self._session_manager.get_served_students_details()
        if not served_meals:
            logger.info(
                "SpreadsheetThread: Nenhum aluno servido encontrado na sessão atual."
                " Nada para fazer upload."
            )
            return  # Encerra com sucesso (nada a fazer)

        # Obtém informações da sessão para determinar a aba alvo
        meal_type = self._session_manager.get_meal_type()
        session_date = self._session_manager.get_date()  # YYYY-MM-DD

        # Valida se temos as informações necessárias
        if not meal_type or not session_date:
            logger.error(
                "SpreadsheetThread: Não é possível determinar nome da aba alvo ou data da sessão."
            )
            self.error = ValueError("Tipo de refeição ou data da sessão ausente.")
            return

        # Define o nome da aba (Worksheet) - Ex: 'Lanche', 'Almoco'
        sheet_name = meal_type.capitalize()
        logger.debug(
            "SpreadsheetThread: Aba alvo: '%s', Data da sessão: %s",
            sheet_name,
            session_date,
        )

        # --- Formatação dos Dados para a Planilha ---
        # Transforma a tupla de dados em uma lista de listas no formato esperado pela planilha
        rows_to_add: List[List[Any]] = []
        for pront, nome, turma, hora, prato_status in served_meals:
            # Simplifica a string de turma (pega apenas a primeira se houver várias)
            # Pode ser ajustado conforme a necessidade da planilha
            simplified_turma = turma.split(",")[0].strip() if "," in turma else turma
            # Adiciona a linha formatada
            # Ordem deve coincidir com as colunas da planilha de destino!
            rows_to_add.append(
                [
                    str(pront),
                    str(session_date),  # Usa a data da sessão
                    str(nome),
                    str(simplified_turma),
                    str(prato_status),
                    str(hora),  # Hora do consumo
                ]
            )

        # --- Envio para a Planilha ---
        if rows_to_add:
            logger.info(
                "SpreadsheetThread: Tentando adicionar %s linhas únicas à aba '%s'.",
                len(rows_to_add),
                sheet_name,
            )
            # Usa append_unique_rows para evitar duplicatas na planilha
            success_append = spreadsheet.append_unique_rows(rows_to_add, sheet_name)
            if not success_append:
                logger.error(
                    "SpreadsheetThread: Falha ao adicionar linhas únicas à aba '%s'.",
                    sheet_name,
                )
                self.error = RuntimeError(
                    f"Falha ao adicionar linhas à Planilha Google '{sheet_name}'."
                    " Verifique os logs."
                )
                # Não retorna aqui, permite que o estado `success` seja definido no final do `run`
        else:
            # Caso raro onde served_meals existe mas rows_to_add fica vazia (erro de formatação?)
            logger.info(
                "SpreadsheetThread: Nenhuma linha formatada para adicionar à planilha."
            )


class SyncReserves(BaseSyncThread):
    """
    Thread para sincronizar dados mestre (Alunos e Reservas) das Planilhas
    Google para o banco de dados local.

    Baixa os dados das planilhas configuradas (STUDENTS_SHEET_NAME, RESERVES_SHEET_NAME),
    salva-os temporariamente como CSV e utiliza as funções `import_students_csv`
    e `import_reserves_csv` para atualizar o banco de dados.
    """

    def _run_logic(self):
        """
        Executa o fluxo de sincronização:
        1. Baixa dados de Alunos da planilha -> Salva CSV -> Importa para DB.
        2. Baixa dados de Reservas da planilha -> Salva CSV -> Importa para DB.
        """
        logger.info(
            "SyncReserves: Iniciando sincronização de cadastros (Alunos/Reservas) do"
            " Google Sheets para o DB local."
        )

        # Obtém a instância do SpreadSheet
        spreadsheet = self._session_manager.get_spreadsheet()
        if not spreadsheet:
            logger.error(
                "SyncReserves: Não é possível prosseguir, instância SpreadSheet indisponível."
            )
            self.error = ValueError("Instância SpreadSheet não disponível.")
            return

        # --- Sincronização de Alunos ---
        logger.info(
            "SyncReserves: Buscando dados de alunos da aba '%s'...", STUDENTS_SHEET_NAME
        )
        students_data = spreadsheet.fetch_sheet_values(STUDENTS_SHEET_NAME)

        if students_data is None:  # Erro ao buscar dados
            logger.error(
                "SyncReserves: Falha ao buscar dados da aba de alunos '%s'."
                " Abortando sincronização.", STUDENTS_SHEET_NAME,
            )
            self.error = RuntimeError(
                f"Falha ao buscar dados da aba '{STUDENTS_SHEET_NAME}'."
            )
            return
        elif not students_data or len(students_data) <= 1:  # Vazio ou apenas cabeçalho
            logger.warning(
                "SyncReserves: Aba de alunos '%s' está vazia ou contém apenas cabeçalhos."
                " Pulando importação de alunos.",STUDENTS_SHEET_NAME,
            )
        else:
            # Salva os dados baixados em um arquivo CSV temporário
            logger.info(
                "SyncReserves: Salvando %s linhas da aba de alunos para '%s'...",
                len(students_data),
                STUDENTS_CSV_PATH,
            )
            # Se salvou CSV, tenta importar para o banco de dados
            if save_csv_from_list(students_data, str(STUDENTS_CSV_PATH)):
                logger.info(
                    "SyncReserves: Dados de alunos salvos em CSV."
                    " Importando para o banco de dados..."
                )
                # Falha na importação para o DB
                if not import_students_csv(
                    self._session_manager.student_crud,
                    self._session_manager.turma_crud,
                    str(STUDENTS_CSV_PATH),
                ):
                    logger.error(
                        "SyncReserves: Falha ao importar dados de alunos do CSV para o"
                        " banco de dados. Abortando sincronização."
                    )
                    self.error = RuntimeError("Falha ao importar alunos do CSV.")
                    return  # Aborta o resto da sincronização
                logger.info("SyncReserves: Dados de alunos importados com sucesso.")
            else:
                # Falha ao salvar o CSV
                logger.error(
                    "SyncReserves: Falha ao salvar dados de alunos no CSV '%s'."
                    " Abortando sincronização.",
                    STUDENTS_CSV_PATH,
                )
                self.error = RuntimeError(
                    f"Falha ao salvar alunos para CSV '{STUDENTS_CSV_PATH}'."
                )
                return  # Aborta

        # --- Sincronização de Reservas ---
        logger.info(
            "SyncReserves: Buscando dados de reservas da aba '%s'...",
            RESERVES_SHEET_NAME,
        )
        reserves_data = spreadsheet.fetch_sheet_values(RESERVES_SHEET_NAME)

        if reserves_data is None:  # Erro ao buscar dados
            logger.error(
                "SyncReserves: Falha ao buscar dados da aba de reservas '%s'."
                " Abortando sincronização.",
                RESERVES_SHEET_NAME,
            )
            self.error = RuntimeError(
                f"Falha ao buscar dados da aba '{RESERVES_SHEET_NAME}'."
            )
            return
        elif not reserves_data or len(reserves_data) <= 1:  # Vazio ou apenas cabeçalho
            logger.warning(
                "SyncReserves: Aba de reservas '%s' está vazia ou contém apenas cabeçalhos."
                " Pulando importação de reservas.",
                RESERVES_SHEET_NAME,
            )
        else:
            # Salva os dados baixados em um arquivo CSV temporário
            logger.info(
                "SyncReserves: Salvando %s linhas da aba de reservas para '%s'...",
                len(reserves_data),
                RESERVES_CSV_PATH,
            )
            if save_csv_from_list(reserves_data, str(RESERVES_CSV_PATH)):
                # Se salvou CSV, tenta importar para o banco de dados
                logger.info(
                    "SyncReserves: Dados de reservas salvos em CSV."
                    " Importando para o banco de dados..."
                )
                # Falha na importação para o DB
                if not import_reserves_csv(
                    self._session_manager.student_crud,
                    self._session_manager.reserve_crud,
                    str(RESERVES_CSV_PATH),
                ):
                    logger.error(
                        "SyncReserves: Falha ao importar dados de reservas do CSV para o"
                        " banco de dados. Abortando sincronização."
                    )
                    self.error = RuntimeError("Falha ao importar reservas do CSV.")
                    return  # Aborta
                logger.info("SyncReserves: Dados de reservas importados com sucesso.")
            else:
                # Falha ao salvar o CSV
                logger.error(
                    "SyncReserves: Falha ao salvar dados de reservas no CSV '%s'."
                    " Abortando sincronização.",RESERVES_CSV_PATH,
                )
                self.error = RuntimeError(
                    f"Falha ao salvar reservas para CSV '{RESERVES_CSV_PATH}'."
                )
                return  # Aborta

        # Se chegou até aqui sem erros, a sincronização foi concluída
        logger.info("SyncReserves: Processo de sincronização de cadastros concluído.")
        # O estado `self.success` será definido como True no final do método `run` da classe base.
