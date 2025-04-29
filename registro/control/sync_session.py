# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# File: registro/control/sync_session.py (Wrapper gspread Refinado)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Fornece uma classe wrapper (`SpreadSheet`) para simplificar a interação com
planilhas Google Sheets usando a biblioteca `gspread`. Gerencia a autenticação,
a abertura da planilha configurada e operações comuns como leitura, escrita e
append de dados, tratando erros comuns da API.
"""
import json
import logging
from typing import List, Set, Tuple, Optional, Dict, Any

import gspread
from gspread.exceptions import APIError, WorksheetNotFound, SpreadsheetNotFound
from gspread.utils import ValueInputOption

# Importações locais
from registro.control.constants import SPREADSHEET_ID_JSON, UI_TEXTS
from registro.control.google_creds import GrantAccess  # Gerenciador de credenciais

logger = logging.getLogger(__name__)

# --- Funções Auxiliares Internas ---


def _convert_to_tuples(list_of_lists: List[List[Any]]) -> Set[Tuple[str, ...]]:
    """Converte uma lista de listas em um conjunto de tuplas de strings."""
    # Mapeia cada elemento da linha interna para string antes de criar a tupla
    return {tuple(map(str, row)) for row in list_of_lists}


def _convert_to_lists(set_of_tuples: Set[Tuple[str, ...]]) -> List[List[str]]:
    """Converte um conjunto de tuplas de strings de volta para uma lista de listas."""
    # Converte cada tupla de volta para lista
    return [list(row) for row in set_of_tuples]

# --- Classe Principal ---


class SpreadSheet:
    """
    Wrapper para interagir com uma planilha Google Sheets específica.

    Gerencia a autenticação e fornece métodos para buscar e atualizar dados
    em abas (worksheets) da planilha configurada no arquivo JSON.
    Utiliza um padrão Singleton implícito para a conexão (atributos de classe).
    """
    # Atributos de classe para manter a conexão única
    spreadsheet: Optional[gspread.Spreadsheet] = None
    client: Optional[gspread.Client] = None
    configuration: Optional[Dict[str, str]] = None  # Armazena config (ex: {'key': '...'})
    _is_initialized: bool = False  # Flag para indicar se a conexão foi estabelecida
    _config_file_path: Optional[str] = None  # Caminho para o arquivo de config da planilha

    def __init__(self, config_file: str = str(SPREADSHEET_ID_JSON)):
        """
        Inicializa o objeto SpreadSheet, definindo o caminho do arquivo de configuração.
        A conexão real é estabelecida sob demanda (lazy initialization).

        Args:
            config_file: Caminho para o arquivo JSON contendo a chave ('key')
                         da planilha Google Sheets.
        """
        # Armazena o caminho do arquivo de configuração na classe
        # (compartilhado entre todas as instâncias)
        SpreadSheet._config_file_path = config_file

    @classmethod
    def _ensure_initialized(cls) -> bool:
        """
        Garante que a conexão com a API Google Sheets esteja estabelecida.
        Se não estiver inicializada, tenta autenticar e abrir a planilha.

        Este método é chamado internamente antes de cada operação na planilha.

        Returns:
            True se a conexão estiver estabelecida (ou foi estabelecida com sucesso),
            False caso contrário.
        """
        # Se já inicializado, retorna True imediatamente
        if cls._is_initialized:
            return True

        logger.debug("Inicializando conexão com Google Sheets...")

        # Verifica se o caminho do arquivo de configuração foi definido
        if not cls._config_file_path:
            logger.error("Não é possível inicializar SpreadSheet: Caminho do arquivo de configuração não definido.")
            return False

        try:
            # --- Autenticação ---
            # Obtém as credenciais usando o gerenciador GrantAccess
            creds_manager = GrantAccess()
            credentials = creds_manager.refresh_or_obtain_credentials().get_credentials()
            if not credentials:
                logger.error("Falha ao obter credenciais Google. Não é possível conectar ao Sheets.")
                return False  # Falha na inicialização

            # Autoriza o cliente gspread com as credenciais obtidas
            cls.client = gspread.authorize(credentials)
            logger.info("Cliente gspread autorizado com sucesso.")

            # --- Leitura da Configuração da Planilha ---
            try:
                with open(cls._config_file_path, 'r', encoding='utf-8') as file:
                    cls.configuration = json.load(file)
            except FileNotFoundError:
                logger.error(f"Arquivo de configuração da planilha não encontrado: '{cls._config_file_path}'")
                return False
            except json.JSONDecodeError as e:
                logger.error(f"Erro ao decodificar JSON de '{cls._config_file_path}': {e}")
                return False

            # Verifica se a configuração é válida e contém a chave da planilha
            if not cls.configuration or 'key' not in cls.configuration:
                logger.error(f"Configuração inválida ou chave ('key') ausente em '{cls._config_file_path}'")
                return False

            # --- Abertura da Planilha ---
            spreadsheet_key = cls.configuration['key']
            logger.info(f"Tentando abrir planilha Google Sheet com a chave: {spreadsheet_key}")
            # Abre a planilha usando a chave (ID)
            cls.spreadsheet = cls.client.open_by_key(spreadsheet_key)
            logger.info(f"Planilha Google Sheet aberta com sucesso: '{cls.spreadsheet.title}' (ID: {spreadsheet_key})")

            # Marca como inicializado com sucesso
            cls._is_initialized = True
            return True

        except SpreadsheetNotFound:
            key_info = cls.configuration.get('key', 'N/A') if cls.configuration else 'N/A'
            logger.error(f"Planilha com a chave '{key_info}' não encontrada. Verifique a chave e as permissões.")
        except APIError as e:
            # Erros gerais da API Google (permissão, cota, etc.)
            key_info = cls.configuration.get('key', 'N/A') if cls.configuration else 'N/A'
            logger.exception(f"Erro de API ao acessar Google Sheet (Chave: {key_info}): {e}")
        except Exception as e:
            # Captura outros erros inesperados
            logger.exception(f"Erro inesperado durante a inicialização do SpreadSheet: {e}")

        # Se chegou aqui, a inicialização falhou. Reseta os atributos de classe.
        cls.spreadsheet = None
        cls.client = None
        cls.configuration = None
        cls._is_initialized = False
        return False

    def _get_worksheet(self, sheet_name: str) -> Optional[gspread.Worksheet]:
        """
        Obtém um objeto Worksheet (aba) pelo nome. Garante que a conexão
        esteja inicializada antes de tentar.

        Args:
            sheet_name: O nome da aba (worksheet) a ser acessada.

        Returns:
            O objeto gspread.Worksheet correspondente ou None se a conexão
            não estiver ativa, a aba não for encontrada ou ocorrer um erro.
        """
        # Garante que a conexão principal esteja ativa
        if not self._ensure_initialized() or self.spreadsheet is None:
            logger.error(f"Não é possível obter worksheet '{sheet_name}': Conexão SpreadSheet não inicializada.")
            return None
        try:
            # Tenta obter a aba pelo nome
            worksheet = self.spreadsheet.worksheet(sheet_name)
            logger.debug(f"Worksheet acessada com sucesso: '{sheet_name}'")
            return worksheet
        except WorksheetNotFound:
            logger.error(f"Worksheet '{sheet_name}' não encontrada na planilha '{self.spreadsheet.title}'.")
        except APIError as e:
            # Erros específicos da API ao acessar a aba
            logger.exception(f"Erro de API ao acessar worksheet '{sheet_name}': {e}")
        except Exception as e:
            # Outros erros inesperados
            logger.exception(f"Erro inesperado ao obter worksheet '{sheet_name}': {e}")
        return None  # Retorna None em caso de qualquer erro

    def update_data(self, rows: List[List[Any]], sheet_name: str, replace: bool = False) -> bool:
        """
        Atualiza dados em uma worksheet específica. Pode substituir todo o
        conteúdo ou adicionar novas linhas ao final.

        Args:
            rows: Lista de listas representando as linhas a serem escritas.
            sheet_name: Nome da worksheet (aba) a ser atualizada.
            replace: Se True, limpa a aba antes de escrever os dados (substitui).
                     Se False (padrão), adiciona as linhas ao final (append).

        Returns:
            True se a operação for bem-sucedida, False caso contrário.
        """
        # Obtém a worksheet alvo
        worksheet = self._get_worksheet(sheet_name)
        if not worksheet:
            logger.error(f"Não é possível atualizar dados: Falha ao obter worksheet '{sheet_name}'.")
            return False
        try:
            # Define como os valores serão interpretados (ex: '1/1/2024' como data)
            value_option = ValueInputOption.user_entered

            if replace:
                # Limpa a planilha inteira
                logger.info(f"Limpando worksheet '{sheet_name}' antes de atualizar...")
                worksheet.clear()
                # Escreve os novos dados a partir da célula A1
                worksheet.update('A1', rows, value_input_option=value_option)
                logger.info(f"Worksheet '{sheet_name}' limpa e atualizada com {len(rows)} linhas.")
            else:
                # Adiciona as linhas ao final da tabela existente
                worksheet.append_rows(values=rows, value_input_option=value_option)
                logger.info(f"Adicionadas {len(rows)} linhas à worksheet '{sheet_name}'.")
            return True
        except APIError as e:
            logger.exception(f"Erro de API ao atualizar dados na worksheet '{sheet_name}': {e}")
        except Exception as e:
            logger.exception(f"Erro inesperado ao atualizar dados em '{sheet_name}': {e}")
        return False

    def fetch_sheet_values(self, sheet_name: str) -> Optional[List[List[str]]]:
        """
        Busca todos os valores de uma worksheet (aba) específica.

        Args:
            sheet_name: Nome da worksheet a ser lida.

        Returns:
            Uma lista de listas contendo todos os valores como strings,
            ou None se ocorrer um erro.
        """
        # Obtém a worksheet alvo
        worksheet = self._get_worksheet(sheet_name)
        if not worksheet:
            logger.error(f"Não é possível buscar valores: Falha ao obter worksheet '{sheet_name}'.")
            return None
        try:
            logger.debug(f"Buscando todos os valores da worksheet '{sheet_name}'...")
            # Obtém todos os valores (incluindo células vazias como '')
            values = worksheet.get_all_values()
            logger.info(f"Buscadas {len(values)} linhas da worksheet '{sheet_name}'.")
            return values
        except APIError as e:
            logger.exception(f"Erro de API ao buscar valores de '{sheet_name}': {e}")
        except Exception as e:
            logger.exception(f"Erro inesperado ao buscar valores de '{sheet_name}': {e}")
        return None

    def append_unique_rows(self, rows_to_append: List[List[Any]], sheet_name: str) -> bool:
        """
        Adiciona linhas a uma worksheet, garantindo que apenas linhas
        que ainda não existem na planilha sejam adicionadas.

        Args:
            rows_to_append: Lista de listas representando as linhas a serem
                            potencialmente adicionadas.
            sheet_name: Nome da worksheet (aba) onde adicionar as linhas.

        Returns:
            True se a operação for bem-sucedida (mesmo que nenhuma linha nova
            tenha sido adicionada), False se ocorrer um erro.
        """
        # Obtém a worksheet alvo
        worksheet = self._get_worksheet(sheet_name)
        if not worksheet:
            logger.error(f"Não é possível adicionar linhas únicas: Falha ao obter worksheet '{sheet_name}'.")
            return False
        try:
            # --- Lógica de Identificação de Linhas Únicas ---
            logger.debug(f"Buscando dados existentes de '{sheet_name}' para determinar linhas únicas...")
            # Busca todos os dados atuais da planilha
            existing_data = worksheet.get_all_values()
            # Converte os dados existentes para um conjunto de tuplas para busca eficiente
            existing_rows_set = _convert_to_tuples(existing_data)
            logger.debug(f"Encontradas {len(existing_rows_set)} linhas existentes em '{sheet_name}'.")

            # Converte as linhas a serem adicionadas para um conjunto de tuplas
            new_rows_set = _convert_to_tuples(rows_to_append)

            # Encontra as linhas que estão no novo conjunto mas não no existente
            unique_new_rows_set = new_rows_set - existing_rows_set

            # Converte as linhas únicas de volta para lista de listas para o append
            unique_rows_to_add = _convert_to_lists(unique_new_rows_set)

            # --- Adição das Linhas Únicas ---
            if unique_rows_to_add:
                logger.info(f"Adicionando {len(unique_rows_to_add)} linhas únicas à worksheet '{sheet_name}'.")
                # Adiciona apenas as linhas que são realmente novas
                worksheet.append_rows(values=unique_rows_to_add, value_input_option=ValueInputOption.user_entered)
            else:
                logger.info(f"Nenhuma linha nova e única encontrada para adicionar à worksheet '{sheet_name}'.")
            return True  # Retorna sucesso mesmo se nada foi adicionado

        except APIError as e:
            logger.exception(f"Erro de API ao adicionar linhas únicas a '{sheet_name}': {e}")
        except Exception as e:
            logger.exception(f"Erro inesperado ao adicionar linhas únicas a '{sheet_name}': {e}")
        return False
