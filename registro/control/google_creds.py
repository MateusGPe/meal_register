# ----------------------------------------------------------------------------
# File: registro/control/google_creds.py (Refined Google Creds Manager)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
import json
import logging
from pathlib import Path
from typing import Optional, Self
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.exceptions import RefreshError
from registro.control.constants import CREDENTIALS_PATH, SCOPES, TOKEN_PATH
from registro.control.utils import save_json
logger = logging.getLogger(__name__)


class GrantAccess:
    def __init__(self: Self, credentials_path: Path = CREDENTIALS_PATH,
                 token_path: Path = TOKEN_PATH):
        self._credentials: Optional[Credentials] = None

        self._credentials_path: Path = Path(credentials_path)
        self._token_path: Path = Path(token_path)
        logger.debug(
            f"GrantAccess initialized. Credentials: '{self._credentials_path}', Token: '{self._token_path}'")

    def _load_token(self) -> Optional[Credentials]:
        if self._token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self._token_path), SCOPES)
                logger.info(f"Token loaded successfully from '{self._token_path}'")
                return creds
            except Exception as e:
                logger.warning(
                    f"Failed to load token from '{self._token_path}': {e}. "
                    "Will attempt to initiate a new authorization flow if needed.")

                try:
                    self._token_path.unlink(missing_ok=True)
                    logger.debug(f"Removed potentially invalid token file: '{self._token_path}'")
                except OSError as rm_err:
                    logger.error(f"Could not remove invalid token file '{self._token_path}': {rm_err}")
        else:
            logger.debug(f"Token file not found at '{self._token_path}'.")
        return None

    def _save_token(self, creds: Credentials):
        try:

            self._token_path.parent.mkdir(parents=True, exist_ok=True)

            creds_dict = json.loads(creds.to_json())

            if save_json(str(self._token_path), creds_dict):
                logger.info(f"Credentials saved successfully to '{self._token_path}'")
            else:

                logger.error(f"Failed to save credentials using save_json to '{self._token_path}'")
        except Exception as e:

            logger.exception(f"Unexpected error saving token to '{self._token_path}': {e}")

    def _run_auth_flow(self) -> Optional[Credentials]:
        logger.info("Attempting to initiate new authorization flow.")
        try:
            if not self._credentials_path.exists():
                logger.error(f"Credentials file not found: '{self._credentials_path}'. Cannot start authorization.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(str(self._credentials_path), SCOPES)

            logger.info("Starting local server for authorization. Please check your browser.")

            creds = flow.run_local_server(port=0)
            logger.info("Authorization flow completed successfully.")
            return creds
        except FileNotFoundError:
            logger.error(f"Credentials file disappeared: '{self._credentials_path}'.")
        except Exception as e:
            logger.exception(f"Error during the authorization flow: {e}")
        return None

    def refresh_or_obtain_credentials(self: Self) -> Self:
        creds = self._load_token()
        if creds and creds.valid:
            logger.info("Using valid credentials loaded from token file.")
            self._credentials = creds
        elif creds and creds.expired and creds.refresh_token:
            logger.info("Credentials expired, attempting refresh...")
            try:
                creds.refresh(Request())
                logger.info("Credentials refreshed successfully.")
                self._credentials = creds
                self._save_token(creds)
            except RefreshError as e:
                logger.error(f"Failed to refresh credentials: {e}. Initiating new authorization flow.")

                try:
                    self._token_path.unlink(missing_ok=True)
                except OSError as rm_err:
                    logger.error(f"Could not remove token file after refresh error: {rm_err}")
                creds = self._run_auth_flow()
                if creds:
                    self._credentials = creds
                    self._save_token(creds)
                else:
                    logger.error("Failed to obtain new credentials after refresh failure.")
                    self._credentials = None
            except Exception as e:
                logger.exception(f"Unexpected error during credential refresh: {e}. Initiating new flow.")
                try:
                    self._token_path.unlink(missing_ok=True)
                except OSError as rm_err:
                    logger.error(f"Could not remove token: {rm_err}")
                creds = self._run_auth_flow()
                if creds:
                    self._credentials = creds
                    self._save_token(creds)
                else:
                    logger.error("Failed to obtain new credentials.")
                    self._credentials = None
        else:
            if creds and not creds.refresh_token:
                logger.info("Credentials expired and no refresh token available. Initiating new authorization flow.")
            elif not creds:
                logger.info("No existing token found. Initiating new authorization flow.")

            creds = self._run_auth_flow()
            if creds:
                self._credentials = creds
                self._save_token(creds)
            else:
                logger.error("Failed to obtain new credentials via authorization flow.")
                self._credentials = None
        return self

    def get_credentials(self: Self) -> Optional[Credentials]:
        if not self._credentials:

            logger.warning("get_credentials() called, but credentials are not available or valid.")
        return self._credentials
