"""
This module defines constants and configurations used throughout the meal register application.

It includes:
- File paths for configuration and data files.
- Google API scopes for accessing spreadsheets and Drive.
- Data processing utilities such as capitalization exceptions and translation dictionaries.
- Class and sheet names for integration and data organization.
- A TypedDict structure for session data representation.
"""

import re
from typing import Dict, List, Literal, Set, TypedDict

# File paths
CREDENTIALS_PATH: str = "./config/credentials.json"
DATABASE_URL: str = "sqlite:///./config/registro.db"
RESERVES_CSV_PATH: str = "./config/reserves.csv"
SPREADSHEET_ID_JSON: str = "./config/spreadsheet.json"
STUDENTS_CSV_PATH: str = "./config/students.csv"
TOKEN_PATH: str = "./config/token.json"

# Google API scopes
SCOPES: List[str] = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Data processing
CAPITALIZE_EXCEPTIONS: Set[str] = {
    "a", "o",
    "as", "os",
    "de", "dos",
    "das", "do",
    "da", "e",
    "é", "com",
    "sem", "ou",
    "para", "por",
    "no", "na",
    "nos", "nas"
}

TRANSLATE_DICT: Dict[int, int] = str.maketrans("0123456789Xx", "abcdefghijkk")
TRANSLATE_KEYS = {
    'matrícula iq': 'pront',
    'matrícula': 'pront',
    'prontuário': 'pront',
    'refeição': 'dish'
}

REMOVE_IQ: re.Pattern[str] = re.compile(r"[Ii][Qq]\d0+")

# Class and sheet names
INTEGRATE_CLASSES: List[str] = [
    "1º A - MAC",
    "1º A - MEC",
    "1º B - MEC",
    "2º A - MAC",
    "2º A - MEC",
    "2º B - MEC",
    "3º A - MEC",
    "3º B - MEC",
]
OTHERS: List[str] = ["SEM RESERVA"]
ANYTHING: List[str] = INTEGRATE_CLASSES + OTHERS

RESERVES_SHEET_NAME: str = "DB"
STUDENTS_SHEET_NAME: str = "Discentes"

SESSION = TypedDict(
    'SESSION',
    {
        'refeição': Literal["Lanche", "Almoço"],
        'lanche': str,
        'período': Literal["Integral", "Matutino", "Vespertino", "Noturno"],
        'data': str,
        'hora': str,
        'groups': List[str]
    })

CSIDL_PERSONAL: int = 5
SHGFP_TYPE_CURRENT: int = 0
