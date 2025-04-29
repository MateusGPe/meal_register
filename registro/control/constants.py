# ----------------------------------------------------------------------------
# File: registro/control/constants.py (Refined Constants)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
import re
from pathlib import Path
from typing import Dict, List, Literal, Optional, Set, TypedDict
APP_DIR = Path(".")
CONFIG_DIR = APP_DIR / "config"
CREDENTIALS_PATH: Path = CONFIG_DIR / "credentials.json"
DATABASE_URL: str = f"sqlite:///{CONFIG_DIR.resolve()}/registro.db"
RESERVES_CSV_PATH: Path = CONFIG_DIR / "reserves.csv"
SPREADSHEET_ID_JSON: Path = CONFIG_DIR / "spreadsheet.json"
STUDENTS_CSV_PATH: Path = CONFIG_DIR / "students.csv"
TOKEN_PATH: Path = CONFIG_DIR / "token.json"
SESSION_PATH: Path = CONFIG_DIR / "session.json"
SNACKS_JSON_PATH: Path = CONFIG_DIR / "lanches.json"
SCOPES: List[str] = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
CAPITALIZATION_EXCEPTIONS: Set[str] = {
    "a", "o", "as", "os", "de", "do", "da", "dos", "das",
    "e", "é", "em", "com", "sem", "ou", "para", "por", "pelo", "pela",
    "no", "na", "nos", "nas"
}
PRONTUARIO_OBFUSCATION_MAP: Dict[int, int] = str.maketrans("0123456789Xx", "abcdefghijkk")
EXTERNAL_KEY_TRANSLATION: Dict[str, str] = {
    'matrícula iq': 'pront',
    'matrícula': 'pront',
    'prontuário': 'pront',
    'refeição': 'dish',
    'curso': 'turma',
    'situação': 'status',
    'nome completo': 'nome'
}
PRONTUARIO_CLEANUP_REGEX: re.Pattern[str] = re.compile(r"^[Ii][Qq]0+")
RESERVES_SHEET_NAME: str = "DB"
STUDENTS_SHEET_NAME: str = "Discentes"
INTEGRATED_CLASSES: List[str] = [
    "1º A - MAC", "1º A - MEC", "1º B - MEC", "2º A - MAC",
    "2º A - MEC", "2º B - MEC", "3º A - MEC", "3º B - MEC",
]
NewSessionData = TypedDict(
    'NewSessionData',
    {
        'refeição': Literal["Lanche", "Almoço"],
        'lanche': Optional[str],
        'período': str,
        'data': str,
        'hora': str,
        'groups': List[str]
    }
)
SESSION = NewSessionData
CSIDL_PERSONAL: int = 5
SHGFP_TYPE_CURRENT: int = 0
EXPORT_HEADER: List[str] = [
    "Matrícula", "Data", "Nome", "Turma", "Refeição", "Hora"
]
