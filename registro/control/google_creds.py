# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Provides a class to handle granting and managing access to Google Sheets and Drive
using the Google Sheets API and Google Drive API.

The `GrantAccess` class simplifies the process of managing Google API credentials by:
- Checking for existing valid credentials.
- Refreshing expired credentials automatically.
- Initiating a new authorization flow if no valid credentials are found.
- Saving credentials to a token file for reuse in subsequent sessions.

This class is designed to work with the Google Sheets API and Google Drive API.
"""

import os.path
from typing import Optional, Self

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from registro.control.constants import CREDENTIALS_PATH, SCOPES, TOKEN_PATH


class GrantAccess:
    """
    Handles the process of granting and managing access to Google Sheets and Drive.

    This class provides methods to manage Google API credentials, ensuring that
    the application has the necessary access to interact with Google Sheets and Drive.
    It supports refreshing expired tokens and initiating new authorization flows
    when required.

    Attributes:
        _credentials (Optional[Credentials]): The current Google API credentials.
        _credentials_path (str): The path to the Google Cloud client secrets JSON file.
        _token_path (str): The path to the token file containing the access token.
    """

    def __init__(self: Self, credentials_path: str = CREDENTIALS_PATH,
                 token_path: str = TOKEN_PATH):
        """
        Initializes the GrantAccess object.

        Args:
            credentials_path (str): The path to the Google Cloud client secrets JSON file.
                This file contains the client ID and client secret for the application.
                Defaults to "./config/credentials.json".
            token_path (str): The path to the token file containing the access token.
                This file is used to store and reuse credentials between sessions.
                Defaults to "./config/token.json".
        """
        self._credentials: Optional[Credentials] = None
        self._credentials_path: str = credentials_path
        self._token_path: str = token_path

    def reflesh_token(self: Self) -> Self:
        """
        Refreshes or obtains new Google API credentials.

        This method performs the following steps:
        1. Checks if a token file exists at the specified `token_path`.
        2. If the token file exists, it loads the credentials from the file.
        3. If the credentials are expired but have a refresh token, it refreshes them.
        4. If no valid credentials are found, it initiates a new authorization flow
           using the client secrets file at `credentials_path`.
        5. Saves the refreshed or newly obtained credentials to the token file.

        Returns:
            Self: The current instance of the `GrantAccess` class with updated credentials.

        Raises:
            FileNotFoundError: If the credentials file does not exist.
            Exception: If an error occurs during the authorization flow or token refresh.
        """
        if os.path.exists(self._token_path):
            self._credentials = Credentials.from_authorized_user_file(
                self._token_path, SCOPES)

        if not self._credentials or not self._credentials.valid:
            if self._credentials and self._credentials.expired and self._credentials.refresh_token:
                self._credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self._credentials_path, SCOPES
                )
                self._credentials = flow.run_local_server(port=0)

            with open(self._token_path, "w", encoding="utf-8") as token:
                token.write(self._credentials.to_json())
        return self

    def get_credentials(self: Self) -> Credentials:
        """
        Retrieves the current Google API credentials.

        This method should be called after ensuring that the credentials are valid
        (e.g., by calling `reflesh_token`).

        Returns:
            Credentials: The current Google API credentials.

        Raises:
            ValueError: If the credentials are not initialized or invalid.
        """
        if not self._credentials:
            raise ValueError("Credentials are not initialized. Call `reflesh_token` first.")
        return self._credentials
