# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# File: registro/control/google_creds.py (Gerenciador de Credenciais Google)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Gerencia a obtenção e atualização de credenciais OAuth2 para interação com
as APIs do Google (Sheets, Drive), utilizando um fluxo de servidor local
para autorização inicial e salvando/reutilizando tokens.
"""
import json
import logging
from pathlib import Path
from typing import Optional, Self

from google.auth.exceptions import GoogleAuthError, RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Importa constantes necessárias
from registro.control.constants import CREDENTIALS_PATH, SCOPES, TOKEN_PATH
from registro.control.utils import save_json

logger = logging.getLogger(__name__)


class GrantAccess:
    """
    Gerencia o ciclo de vida das credenciais do Google OAuth2.

    Tenta carregar um token existente, atualizá-lo se expirado, ou iniciar
    um novo fluxo de autorização via navegador se necessário.
    """

    def __init__(self: Self, credentials_path: Path = CREDENTIALS_PATH,
                 token_path: Path = TOKEN_PATH):
        """
        Inicializa o gerenciador de acesso.

        Args:
            credentials_path: Caminho para o arquivo JSON de credenciais da API
                              (client_secrets.json ou similar).
            token_path: Caminho para o arquivo JSON onde o token de acesso/refresh
                        será armazenado.
        """
        self._credentials: Optional[Credentials] = None
        self._credentials_path: Path = Path(credentials_path)
        self._token_path: Path = Path(token_path)
        logger.debug(
            f"GrantAccess inicializado. Credenciais: '{self._credentials_path}', Token: '{self._token_path}'")

    def _load_token(self) -> Optional[Credentials]:
        """
        Tenta carregar as credenciais a partir do arquivo de token armazenado.

        Returns:
            Um objeto Credentials se o token for carregado e válido (mesmo que
            expirado, desde que tenha refresh token), ou None se o arquivo não
            existir ou ocorrer um erro ao carregá-lo.
        """
        if self._token_path.exists():
            try:
                # Carrega as credenciais do arquivo usando os escopos definidos
                creds = Credentials.from_authorized_user_file(str(self._token_path), SCOPES)
                logger.info(f"Token carregado com sucesso de '{self._token_path}'")
                return creds
            except ValueError as ve:
                logger.warning(f"Formato inválido no arquivo de token '{self._token_path}': {ve}. Tentando remover.")
                self._remove_token_file()
            except GoogleAuthError as ae:
                logger.warning(
                    f"Erro de autenticação ao carregar token de '{self._token_path}': {ae}. Tentando remover.")
                self._remove_token_file()
            except Exception as e:
                # Captura outros erros potenciais durante o carregamento
                logger.warning(
                    f"Falha ao carregar token de '{self._token_path}': {e}. "
                    "Tentará iniciar novo fluxo de autorização se necessário.")
                # Tenta remover o arquivo de token potencialmente inválido
                self._remove_token_file()
        else:
            logger.debug(f"Arquivo de token não encontrado em '{self._token_path}'.")
        return None

    def _remove_token_file(self) -> None:
        """ Tenta remover o arquivo de token. """
        try:
            self._token_path.unlink(missing_ok=True)  # Ignora erro se já não existir
            logger.debug(f"Arquivo de token potencialmente inválido removido: '{self._token_path}'")
        except OSError as rm_err:
            logger.error(f"Não foi possível remover o arquivo de token inválido '{self._token_path}': {rm_err}")

    def _save_token(self, creds: Credentials) -> None:
        """
        Salva as credenciais (incluindo refresh token) no arquivo de token.

        Args:
            creds: O objeto Credentials a ser salvo.
        """
        try:
            # Garante que o diretório pai exista
            self._token_path.parent.mkdir(parents=True, exist_ok=True)
            # Converte as credenciais para um dicionário serializável
            # O método to_json() retorna uma string JSON, então carregamos de volta
            creds_dict = json.loads(creds.to_json())
            # Usa a função utilitária para salvar o JSON
            if save_json(str(self._token_path), creds_dict):
                logger.info(f"Credenciais salvas com sucesso em '{self._token_path}'")
            else:
                # save_json já loga o erro específico
                logger.error(f"Falha ao salvar credenciais usando save_json para '{self._token_path}'")
        except json.JSONDecodeError as json_err:
            logger.error(
                f"Erro ao serializar credenciais para JSON antes de salvar em '{self._token_path}': {json_err}")
        except Exception as e:
            logger.exception(f"Erro inesperado ao salvar token em '{self._token_path}': {e}")

    def _run_auth_flow(self) -> Optional[Credentials]:
        """
        Inicia o fluxo de autorização OAuth2 interativo (abre o navegador).

        Requer o arquivo de credenciais da API (`credentials.json`).

        Returns:
            Um objeto Credentials com o token de acesso e refresh token se o
            fluxo for concluído com sucesso, ou None caso contrário.
        """
        logger.info("Tentando iniciar novo fluxo de autorização.")
        try:
            # Verifica se o arquivo de credenciais da API existe
            if not self._credentials_path.exists():
                logger.error(
                    f"Arquivo de credenciais não encontrado: '{self._credentials_path}'. Não é possível iniciar autorização.")
                return None

            # Configura o fluxo a partir do arquivo de credenciais e escopos
            flow = InstalledAppFlow.from_client_secrets_file(str(self._credentials_path), SCOPES)

            # Inicia um servidor local temporário para receber o callback do Google
            # port=0 pede ao sistema para escolher uma porta livre
            logger.info("Iniciando servidor local para autorização. Verifique seu navegador.")
            creds = flow.run_local_server(port=0)
            logger.info("Fluxo de autorização concluído com sucesso.")
            return creds
        except FileNotFoundError:
            # Caso o arquivo desapareça entre a verificação e o uso
            logger.error(f"Arquivo de credenciais desapareceu: '{self._credentials_path}'.")
        except Exception as e:
            logger.exception(f"Erro durante o fluxo de autorização: {e}")
        return None

    def refresh_or_obtain_credentials(self: Self) -> Self:
        """
        Orquestra o processo de obtenção de credenciais válidas.

        1. Tenta carregar do token.
        2. Se carregado e válido, usa.
        3. Se carregado, expirado e com refresh token, tenta atualizar.
        4. Se a atualização falhar ou não houver token/refresh token,
           inicia o fluxo de autorização interativo.
        5. Salva o token novo ou atualizado.

        Returns:
            A própria instância (self) para encadeamento de métodos.
            O atributo `_credentials` conterá as credenciais válidas ou None.
        """
        creds = self._load_token()

        if creds and creds.valid:
            # Token carregado e ainda válido
            logger.info("Usando credenciais válidas carregadas do arquivo de token.")
            self._credentials = creds
        elif creds and creds.expired and creds.refresh_token:
            # Token carregado, mas expirado; tenta atualizar usando refresh token
            logger.info("Credenciais expiradas, tentando atualização...")
            try:
                # Tenta obter um novo token de acesso
                creds.refresh(Request())
                logger.info("Credenciais atualizadas com sucesso.")
                self._credentials = creds
                # Salva o token atualizado (que pode ter novo access_token)
                self._save_token(creds)
            except RefreshError as e:
                # Falha na atualização (refresh token inválido, revogado, etc.)
                logger.error(f"Falha ao atualizar credenciais: {e}. Iniciando novo fluxo de autorização.")
                self._remove_token_file()  # Remove o token antigo/inválido
                creds = self._run_auth_flow()  # Tenta obter novas credenciais
                if creds:
                    self._credentials = creds
                    self._save_token(creds)
                else:
                    logger.error("Falha ao obter novas credenciais após falha na atualização.")
                    self._credentials = None
            except Exception as e:
                # Outro erro durante a atualização
                logger.exception(f"Erro inesperado durante atualização de credenciais: {e}. Iniciando novo fluxo.")
                self._remove_token_file()
                creds = self._run_auth_flow()
                if creds:
                    self._credentials = creds
                    self._save_token(creds)
                else:
                    logger.error("Falha ao obter novas credenciais.")
                    self._credentials = None
        else:
            # Nenhuma credencial válida carregada (arquivo não existe, expirado sem refresh token, etc.)
            if creds and not creds.refresh_token:
                logger.info("Credenciais expiradas e sem refresh token disponível. Iniciando novo fluxo de autorização.")
            elif not creds:
                logger.info("Nenhum token existente encontrado. Iniciando novo fluxo de autorização.")

            # Inicia o fluxo interativo para obter novas credenciais
            creds = self._run_auth_flow()
            if creds:
                self._credentials = creds
                self._save_token(creds)  # Salva as novas credenciais
            else:
                logger.error("Falha ao obter novas credenciais via fluxo de autorização.")
                self._credentials = None
        return self  # Permite encadeamento, ex: GrantAccess().refresh_or_obtain_credentials().get_credentials()

    def get_credentials(self: Self) -> Optional[Credentials]:
        """
        Retorna as credenciais OAuth2 válidas.

        É recomendado chamar `refresh_or_obtain_credentials()` antes para
        garantir que as credenciais estejam prontas e atualizadas.

        Returns:
            O objeto Credentials válido ou None se as credenciais não puderam
            ser obtidas ou atualizadas.
        """
        if not self._credentials:
            logger.warning("get_credentials() chamado, mas as credenciais não estão disponíveis ou válidas.")
        return self._credentials
