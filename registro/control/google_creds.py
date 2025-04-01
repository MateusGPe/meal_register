# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Provides a class to handle granting and managing access to Google Sheets and Drive
using the Google Sheets API and Google Drive API.
"""

import os.path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]


class GrantAccess:
    """
    Handles the process of granting and managing access to Google Sheets and Drive.

    This class checks for existing valid credentials, refreshes them if expired,
    or initiates a new authorization flow if no valid credentials are found.
    The credentials are saved to a token file for subsequent use.
    """
    credentials: Optional[Credentials] = None

    def __init__(self, credential_path: str = "./config/credentials.json",
                 token_path: str = "./config/token.json"):
        """
        Initializes the GrantAccess object.

        Checks for an existing token file. If found and valid, loads the credentials.
        If no valid token is found, it attempts to refresh existing credentials
        or initiates a new authorization flow using the provided credentials file.

        Args:
            credential_path (str, optional): The path to the Google Cloud client
                secrets JSON file. Defaults to "./config/credentials.json".
            token_path (str, optional): The path to the file where the Google
                access token will be stored. Defaults to "./config/token.json".
        """
        if os.path.exists(token_path):
            self.credentials = Credentials.from_authorized_user_file(
                token_path, SCOPES)

        if not self.credentials or not self.credentials.valid:
            if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                self.credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    credential_path, SCOPES
                )
                self.credentials = flow.run_local_server(port=0)

            with open(token_path, "w", encoding="utf-8") as token:
                token.write(self.credentials.to_json())
