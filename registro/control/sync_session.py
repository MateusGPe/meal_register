# ----------------------------------------------------------------------------
# File: registro/control/sync_session.py (Refined gspread Wrapper)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Fornece uma classe para interagir com o Google Sheets usando a biblioteca gspread,
permitindo atualização, busca e adição de dados.
"""

import json
import logging
from typing import List, Set, Tuple, Optional, Dict, Any

import gspread
from google.oauth2.credentials import Credentials
# Exceções específicas do gspread para melhor tratamento de erros
from gspread.exceptions import APIError, WorksheetNotFound, SpreadsheetNotFound
from gspread.utils import ValueInputOption # Enum para opções de input

# Importações locais
from registro.control.constants import SPREADSHEET_ID_JSON
from registro.control.google_creds import GrantAccess # Gerenciador de credenciais

logger = logging.getLogger(__name__)

# --- Funções Auxiliares Privadas ---
def _convert_to_tuples(list_of_lists: List[List[str]]) -> Set[Tuple[str, ...]]:
    """Converte lista de listas em um conjunto de tuplas (para comparação)."""
    return set(tuple(map(str, row)) for row in list_of_lists) # Garante que sejam strings

def _convert_to_lists(set_of_tuples: Set[Tuple[str, ...]]) -> List[List[str]]:
    """Converte conjunto de tuplas de volta para lista de listas."""
    return [list(row) for row in set_of_tuples]

# --- Classe Principal ---
class SpreadSheet:
    """
    Classe para interagir com o Google Sheets usando gspread.

    Fornece métodos para atualizar, buscar e adicionar dados a uma Planilha Google.
    """
    spreadsheet: Optional[gspread.Spreadsheet] = None
    client: Optional[gspread.Client] = None
    configuration: Optional[Dict[str, str]] = None
    _is_initialized: bool = False

    def __init__(self, config_file: str = SPREADSHEET_ID_JSON):
        """
        Inicializa o objeto SpreadSheet (lazy initialization).

        A conexão real e abertura da planilha ocorrem na primeira chamada de método
        que necessite delas, através do método `_ensure_initialized`.

        Args:
            config_file (str): Caminho para o arquivo JSON de configuração
                               contendo a chave (key) da Planilha Google.
        """
        self._config_file = config_file
        # Inicialização adiada para _ensure_initialized

    def _ensure_initialized(self) -> bool:
        """ Garante que a conexão e a planilha estejam inicializadas. """
        if self._is_initialized:
            return True # Já inicializado

        logger.debug("Inicializando conexão com Google Sheets...")
        try:
            # 1. Obter credenciais
            creds_manager = GrantAccess()
            # Tenta obter/atualizar credenciais
            credentials = creds_manager.refresh_or_obtain_credentials().get_credentials()
            if not credentials:
                logger.error("Falha ao obter credenciais do Google. Não é possível conectar ao Sheets.")
                return False

            # 2. Autorizar cliente gspread
            self.client = gspread.authorize(credentials)
            logger.info("Cliente gspread autorizado.")

            # 3. Carregar configuração da planilha
            with open(self._config_file, 'r', encoding='utf-8') as file:
                self.configuration = json.load(file)
            if not self.configuration or 'key' not in self.configuration:
                 logger.error(f"Configuração inválida ou chave 'key' ausente em '{self._config_file}'")
                 return False

            # 4. Abrir a planilha pela chave
            spreadsheet_key = self.configuration['key']
            logger.info(f"Abrindo Planilha Google com chave: {spreadsheet_key}")
            self.spreadsheet = self.client.open_by_key(spreadsheet_key)
            logger.info(f"Planilha '{self.spreadsheet.title}' aberta com sucesso.")
            self._is_initialized = True
            return True

        except json.JSONDecodeError as e:
            logger.exception(f"Erro ao decodificar JSON de configuração '{self._config_file}': {e}")
        except FileNotFoundError:
             logger.error(f"Arquivo de configuração da planilha não encontrado: '{self._config_file}'")
        except (SpreadsheetNotFound, APIError) as e:
            logger.exception(f"Erro ao abrir/acessar planilha (chave: {self.configuration.get('key', 'N/A')}): {e}")
        except Exception as e: # Captura outros erros inesperados
            logger.exception(f"Erro inesperado durante a inicialização do SpreadSheet: {e}")

        # Se chegou aqui, a inicialização falhou
        self._is_initialized = False
        self.spreadsheet = None
        self.client = None
        self.configuration = None
        return False

    def _get_worksheet(self, sheet_name: str) -> Optional[gspread.Worksheet]:
        """ Obtém um objeto Worksheet pelo nome, tratando erros comuns. """
        if not self._ensure_initialized() or self.spreadsheet is None:
            logger.error(f"Não foi possível obter worksheet '{sheet_name}': Conexão não inicializada.")
            return None
        try:
            return self.spreadsheet.worksheet(sheet_name)
        except WorksheetNotFound:
            logger.error(f"Worksheet '{sheet_name}' não encontrada na planilha '{self.spreadsheet.title}'.")
        except APIError as e:
            logger.exception(f"Erro de API ao acessar worksheet '{sheet_name}': {e}")
        except Exception as e:
             logger.exception(f"Erro inesperado ao obter worksheet '{sheet_name}': {e}")
        return None

    def update_data(self, rows: List[List[Any]], sheet_name: str, replace: bool = False) -> bool:
        """
        Atualiza dados em uma worksheet específica.

        Args:
            rows (List[List[Any]]): Lista de linhas para atualizar/adicionar.
            sheet_name (str): Nome da worksheet.
            replace (bool): Se True, limpa a planilha antes de adicionar. False para adicionar no final.

        Returns:
            bool: True se sucesso, False caso contrário.
        """
        worksheet = self._get_worksheet(sheet_name)
        if not worksheet: return False

        try:
            value_option = ValueInputOption.user_entered # Interpreta valores como o usuário digitaria
            if replace:
                worksheet.clear() # Limpa toda a planilha
                worksheet.update('A1', rows, value_input_option=value_option)
                logger.info(f"Worksheet '{sheet_name}' limpa e dados atualizados.")
            else:
                # Adiciona as linhas no final da tabela existente
                worksheet.append_rows(values=rows, value_input_option=value_option)
                logger.info(f"{len(rows)} linhas adicionadas à worksheet '{sheet_name}'.")
            return True
        except APIError as e:
            logger.exception(f"Erro de API ao atualizar dados em '{sheet_name}': {e}")
        except Exception as e:
            logger.exception(f"Erro inesperado ao atualizar dados em '{sheet_name}': {e}")
        return False

    def fetch_sheet_values(self, sheet_name: str) -> Optional[List[List[str]]]:
        """
        Busca todos os valores de uma worksheet específica.

        Args:
            sheet_name (str): Nome da worksheet.

        Returns:
            Optional[List[List[str]]]: Lista de listas com os valores, ou None em caso de erro.
        """
        worksheet = self._get_worksheet(sheet_name)
        if not worksheet: return None

        try:
            logger.debug(f"Buscando todos os valores da worksheet '{sheet_name}'...")
            values = worksheet.get_all_values()
            logger.info(f"{len(values)} linhas encontradas em '{sheet_name}'.")
            return values
        except APIError as e:
            logger.exception(f"Erro de API ao buscar valores de '{sheet_name}': {e}")
        except Exception as e:
            logger.exception(f"Erro inesperado ao buscar valores de '{sheet_name}': {e}")
        return None

    def append_unique_rows(self, rows_to_append: List[List[Any]], sheet_name: str) -> bool:
        """
        Adiciona apenas linhas únicas (que não existem) a uma worksheet.

        Args:
            rows_to_append (List[List[Any]]): Lista de linhas candidatas a adicionar.
            sheet_name (str): Nome da worksheet.

        Returns:
            bool: True se sucesso (mesmo que nenhuma linha seja adicionada), False em caso de erro.
        """
        worksheet = self._get_worksheet(sheet_name)
        if not worksheet: return False

        try:
            logger.debug(f"Buscando dados existentes em '{sheet_name}' para adicionar linhas únicas...")
            existing_data = worksheet.get_all_values() # Pega todos os dados atuais
            existing_rows_set = _convert_to_tuples(existing_data) # Converte para set de tuplas para busca rápida
            new_rows_set = _convert_to_tuples(rows_to_append) # Converte novas linhas também

            # Encontra as linhas que estão em new_rows_set mas não em existing_rows_set
            unique_new_rows_set = new_rows_set - existing_rows_set
            unique_rows_to_add = _convert_to_lists(unique_new_rows_set) # Converte de volta para lista de listas

            if unique_rows_to_add:
                logger.info(f"Adicionando {len(unique_rows_to_add)} linhas únicas à worksheet '{sheet_name}'.")
                worksheet.append_rows(values=unique_rows_to_add, value_input_option=ValueInputOption.user_entered)
            else:
                logger.info(f"Nenhuma linha única nova para adicionar à worksheet '{sheet_name}'.")
            return True # Operação bem-sucedida (mesmo sem adicionar nada)

        except APIError as e:
            logger.exception(f"Erro de API ao adicionar linhas únicas a '{sheet_name}': {e}")
        except Exception as e:
            logger.exception(f"Erro inesperado ao adicionar linhas únicas a '{sheet_name}': {e}")
        return False