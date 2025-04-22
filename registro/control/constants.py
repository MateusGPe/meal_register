# ----------------------------------------------------------------------------
# File: registro/control/constants.py (Refined Constants)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Constantes e configurações para a aplicação Registro de Refeições.

Este módulo fornece:
- Caminhos de arquivo para configuração e arquivos de dados.
- Escopos da API do Google para acesso a planilhas e Google Drive.
- Utilitários para processamento de dados, incluindo exceções de capitalização e
  dicionários de tradução.
- Nomes de classes e planilhas para integração e organização de dados.
- Uma estrutura TypedDict para representação de dados de sessão.
"""

import re
from typing import Dict, List, Literal, Optional, Set, TypedDict

# --- Caminhos de Arquivo ---
CONFIG_DIR: str = "./config"  # Diretório base de configuração
CREDENTIALS_PATH: str = f"{CONFIG_DIR}/credentials.json"
# Usa caminho relativo seguro
DATABASE_URL: str = f"sqlite:///{CONFIG_DIR}/registro.db"
RESERVES_CSV_PATH: str = f"{CONFIG_DIR}/reserves.csv"
SPREADSHEET_ID_JSON: str = f"{CONFIG_DIR}/spreadsheet.json"
STUDENTS_CSV_PATH: str = f"{CONFIG_DIR}/students.csv"
TOKEN_PATH: str = f"{CONFIG_DIR}/token.json"
SESSION_PATH: str = f"{CONFIG_DIR}/session.json"
# Caminho para arquivo de lanches
SNACKS_JSON_PATH: str = f"{CONFIG_DIR}/lanches.json"

# --- Configurações API Google ---
SCOPES: List[str] = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# --- Processamento de Texto ---
# Palavras (minúsculas) que não devem ser capitalizadas automaticamente
CAPITALIZE_EXCEPTIONS: Set[str] = {
    "a", "o", "as", "os", "de", "do", "da", "dos", "das",
    "e", "é", "em", "com", "sem", "ou", "para", "por", "pelo", "pela",
    "no", "na", "nos", "nas"
}

# Mapeamento para ofuscar/codificar prontuários (se necessário)
TRANSLATE_DICT: Dict[int, int] = str.maketrans("0123456789Xx", "abcdefghijkk")

# Mapeamento para normalizar chaves de dicionários (ex: de CSVs ou planilhas)
TRANSLATE_KEYS: Dict[str, str] = {
    'matrícula iq': 'pront',
    'matrícula': 'pront',
    'prontuário': 'pront',
    'refeição': 'dish',  # Usado em alguns contextos de reserva
    'curso': 'turma',  # Exemplo, ajuste conforme nomes reais das colunas
    'situação': 'status',  # Exemplo
}

# Regex para remover prefixo "IQ" e zeros subsequentes do prontuário para comparação/exibição
# Remove IQ0, IQ00, etc.
REMOVE_IQ: re.Pattern[str] = re.compile(r"[Ii][Qq]0+")

# --- Nomes de Planilhas Google ---
RESERVES_SHEET_NAME: str = "DB"         # Planilha de onde as reservas são lidas
# Planilha de onde os dados dos alunos são lidos
STUDENTS_SHEET_NAME: str = "Discentes"

# --- Nomes de Turmas Específicas (Exemplos) ---
# Usado no SessionDialog para seleção rápida
INTEGRATE_CLASSES: List[str] = [
    "1º A - MAC", "1º A - MEC", "1º B - MEC", "2º A - MAC",
    "2º A - MEC", "2º B - MEC", "3º A - MEC", "3º B - MEC",
]
# 'SEM RESERVA' é um conceito de filtro, não uma turma real aqui
# OTHERS: List[str] = ["SEM RESERVA"] # Removido daqui, tratado por prefixo '#'
# ANYTHING: List[str] = INTEGRATE_CLASSES + OTHERS # Removido

# --- Tipagem de Dados ---
# Define a estrutura esperada para dados de uma nova sessão
SESSION = TypedDict(
    'SESSION',
    {
        # Tipos de refeição permitidos
        'refeição': Literal["Lanche", "Almoço"],
        # Nome do lanche (se refeição for Lanche)
        'lanche': Optional[str],
        # Período (Matutino, etc.) - Opcional, pode ser vazio
        'período': str,
        'data': str,                            # Data no formato YYYY-MM-DD
        'hora': str,                            # Hora no formato HH:MM
        # Lista de nomes de turmas selecionadas
        'groups': List[str]
    }
)

# --- Constantes Windows API (para get_documments_path) ---
CSIDL_PERSONAL: int = 5         # Constante para a pasta 'Meus Documentos'
SHGFP_TYPE_CURRENT: int = 0     # Constante para obter o caminho atual

# --- Cabeçalho para Exportação Excel ---
EXPORT_HEADER: List[str] = ["Matrícula",
                            "Data", "Nome", "Turma", "Refeição", "Hora"]
