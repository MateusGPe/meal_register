# ----------------------------------------------------------------------------
# File: registro/control/google_creds.py (Refined Google Creds Manager)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Fornece uma classe para gerenciar o acesso às APIs Google (Sheets, Drive)
usando OAuth 2.0.

A classe `GrantAccess` simplifica o fluxo de obtenção e atualização de credenciais:
- Verifica credenciais existentes e válidas (token.json).
- Atualiza credenciais expiradas usando o refresh_token.
- Inicia um novo fluxo de autorização (via navegador/servidor local) se necessário.
- Salva as credenciais obtidas/atualizadas em token.json para uso futuro.
"""

import logging
import os.path
from typing import Optional, Self

# Importações da biblioteca Google OAuth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Importações locais de constantes
from registro.control.constants import CREDENTIALS_PATH, SCOPES, TOKEN_PATH
from registro.control.utils import save_json  # Para salvar o token

logger = logging.getLogger(__name__)


class GrantAccess:
    """
    Gerencia o processo de autenticação e autorização para APIs Google.

    Atributos:
        _credentials (Optional[Credentials]): As credenciais Google API atuais.
        _credentials_path (str): Caminho para o arquivo JSON de segredos do cliente.
        _token_path (str): Caminho para o arquivo JSON do token de acesso/refresh.
    """

    def __init__(self: Self, credentials_path: str = CREDENTIALS_PATH,
                 token_path: str = TOKEN_PATH):
        """
        Inicializa o GrantAccess.

        Args:
            credentials_path (str): Caminho para o arquivo `credentials.json`.
            token_path (str): Caminho para o arquivo `token.json`.
        """
        self._credentials: Optional[Credentials] = None
        self._credentials_path: str = credentials_path
        self._token_path: str = token_path
        logger.debug(
            f"GrantAccess inicializado. Credenciais: '{credentials_path}', Token: '{token_path}'")

    def _load_token(self) -> Optional[Credentials]:
        """ Tenta carregar credenciais do arquivo token.json. """
        if os.path.exists(self._token_path):
            try:
                creds = Credentials.from_authorized_user_file(
                    self._token_path, SCOPES)
                logger.info(f"Token carregado de '{self._token_path}'")
                return creds
            except Exception as e:  # Captura erros ao carregar/parsear o token
                logger.warning(
                    f"Falha ao carregar token de '{self._token_path}': {e}. Um novo fluxo será iniciado se necessário.")
                # Tenta remover token inválido para forçar novo fluxo
                try:
                    os.remove(self._token_path)
                except OSError:
                    pass
        return None

    def _save_token(self, creds: Credentials):
        """ Salva as credenciais no arquivo token.json. """
        try:
            # Garante que o diretório exista
            os.makedirs(os.path.dirname(self._token_path), exist_ok=True)
            # Usa save_json para escrita segura
            # Converte para dict antes de salvar
            if save_json(self._token_path, json.loads(creds.to_json())):
                logger.info(f"Credenciais salvas em '{self._token_path}'")
            else:
                logger.error(
                    f"Falha ao salvar credenciais em '{self._token_path}'")
        except Exception as e:
            logger.exception(
                f"Erro inesperado ao salvar token em '{self._token_path}': {e}")

    def _run_auth_flow(self) -> Optional[Credentials]:
        """ Executa o fluxo de autorização OAuth 2.0 instalado. """
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                self._credentials_path, SCOPES)
            # run_local_server tenta abrir o navegador para autorização
            logger.info(
                "Iniciando fluxo de autorização local. Verifique o navegador.")
            # Porta 0 para escolher uma disponível
            creds = flow.run_local_server(port=0)
            logger.info("Fluxo de autorização concluído.")
            return creds
        except FileNotFoundError:
            logger.error(
                f"Arquivo de credenciais não encontrado: '{self._credentials_path}'. Não é possível iniciar autorização.")
        # Captura outros erros (rede, cancelamento pelo usuário, etc.)
        except Exception as e:
            logger.exception(f"Erro durante o fluxo de autorização: {e}")
        return None

    def refresh_or_obtain_credentials(self: Self) -> Self:
        """
        Garante credenciais válidas, atualizando ou obtendo novas se necessário.

        Ordem de verificação:
        1. Carrega do `token.json`.
        2. Se carregado e válido, usa.
        3. Se carregado, expirado, mas com refresh token, atualiza.
        4. Se não carregado, ou inválido/sem refresh token, inicia novo fluxo de autorização.
        5. Salva as credenciais válidas (atualizadas ou novas) em `token.json`.

        Returns:
            Self: A própria instância com as credenciais atualizadas em `_credentials`.
        """
        creds = self._load_token()

        if creds and creds.valid:
            logger.info("Credenciais válidas carregadas do token.")
            self._credentials = creds
        elif creds and creds.expired and creds.refresh_token:
            logger.info("Credenciais expiradas, tentando atualizar...")
            try:
                creds.refresh(Request())
                logger.info("Credenciais atualizadas com sucesso.")
                self._credentials = creds
                self._save_token(creds)  # Salva o token atualizado
            except Exception as e:
                logger.error(
                    f"Falha ao atualizar credenciais: {e}. Iniciando novo fluxo.")
                # Se refresh falhar, força novo fluxo removendo token antigo
                if os.path.exists(self._token_path):
                    try:
                        os.remove(self._token_path)
                    except OSError:
                        pass
                creds = self._run_auth_flow()
                if creds:
                    self._credentials = creds
                    self._save_token(creds)
                else:
                    logger.error(
                        "Falha ao obter novas credenciais após falha na atualização.")
                    self._credentials = None  # Garante que fique None se falhar
        else:
            logger.info(
                "Nenhuma credencial válida encontrada ou token expirado sem refresh token. Iniciando novo fluxo.")
            creds = self._run_auth_flow()
            if creds:
                self._credentials = creds
                self._save_token(creds)
            else:
                logger.error(
                    "Falha ao obter novas credenciais pelo fluxo de autorização.")
                self._credentials = None  # Garante que fique None se falhar

        return self  # Retorna self para encadeamento (fluent interface)

    def get_credentials(self: Self) -> Optional[Credentials]:
        """
        Retorna as credenciais atuais (pode ser None se a obtenção/atualização falhou).

        É recomendado chamar `refresh_or_obtain_credentials` antes de usar este método.

        Returns:
            Optional[Credentials]: As credenciais Google API ou None.
        """
        # Não lança mais exceção, retorna None se falhou, permitindo tratamento no chamador
        if not self._credentials:
            logger.warning(
                "get_credentials() chamado, mas as credenciais não estão disponíveis/válidas.")
        return self._credentials
