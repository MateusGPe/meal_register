# ----------------------------------------------------------------------------
# File: registro/control/utils.py (Refined Utilities)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Funções utilitárias para a aplicação de registro.

Este módulo fornece uma coleção de funções auxiliares para tarefas comuns
como carregar e salvar dados nos formatos JSON e CSV, capitalizar texto
de acordo com regras específicas e ajustar chaves de dicionários.
"""

import csv
import ctypes
import json
import logging
import os
import platform
import re
import sys
from json import JSONDecodeError
from typing import Any, Dict, List, Optional, Tuple, Callable, Literal, Set, Union  # Adicionado Set

# Importações locais de constantes
from registro.control.constants import (
    CAPITALIZE_EXCEPTIONS, CSIDL_PERSONAL, REMOVE_IQ, SHGFP_TYPE_CURRENT,
    TRANSLATE_DICT, TRANSLATE_KEYS
)

# fuzzywuzzy é opcional aqui, movido para onde é usado (SearchStudents)
# from fuzzywuzzy import fuzz

logger = logging.getLogger(__name__)

# --- Funções de Processamento de Texto ---


def to_code(text: str) -> str:
    """
    Codifica um texto removendo 'IQ' e aplicando um dicionário de tradução.
    Usado principalmente para gerar um ID ofuscado a partir do prontuário.

    Args:
        text (str): A string de entrada (geralmente prontuário).

    Returns:
        str: A string codificada.
    """
    if not isinstance(text, str):
        return ""  # Lida com entrada inválida
    text_cleaned = REMOVE_IQ.sub("", text)  # Remove IQ0...
    # Aplica mapeamento de caracteres
    translated = text_cleaned.translate(TRANSLATE_DICT)
    # A junção com espaço parece específica, verificar se é necessária
    # return " ".join(translated)
    return translated  # Retorna diretamente a string traduzida


def capitalize(text: str) -> str:
    """
    Retorna a string capitalizada (primeira letra maiúscula, resto minúsculo),
    a menos que seja uma exceção definida em CAPITALIZE_EXCEPTIONS.
    Processa cada palavra se houver espaços.

    Args:
        text (str): A string de entrada a ser capitalizada.

    Returns:
        str: A string capitalizada.
    """
    if not isinstance(text, str):
        return ""
    text = text.strip()
    if not text:
        return ""

    words = text.split(" ")
    capitalized_words = []
    for word in words:
        if not word:
            continue
        lword = word.lower()
        if lword in CAPITALIZE_EXCEPTIONS:
            capitalized_words.append(lword)
        elif len(word) == 1:  # Capitaliza palavras de uma letra que não são exceção
            capitalized_words.append(word.upper())
        else:
            capitalized_words.append(word[0].upper() + lword[1:])

    return " ".join(capitalized_words)


def adjust_keys(input_dict: Dict[Any, Any]) -> Dict[str, Any]:
    """
    Ajusta chaves e valores de um dicionário: normaliza chaves (minúsculas, traduz)
    e formata valores específicos (capitaliza nome/dish, limpa pront).

    Args:
        input_dict (dict): O dicionário de entrada (geralmente de CSV/planilha).

    Returns:
        dict: Um novo dicionário com chaves e valores ajustados.
              As chaves são sempre strings minúsculas normalizadas.
    """
    adjusted_dict: Dict[str, Any] = {}
    for key, value in input_dict.items():
        original_key = key  # Guarda chave original para referência se não for string
        normalized_key = key  # Assume que não será string inicialmente

        # Normaliza a chave se for string
        if isinstance(key, str):
            normalized_key = key.strip().lower()
            normalized_key = TRANSLATE_KEYS.get(
                normalized_key, normalized_key)  # Aplica tradução de chave

        # Processa o valor (remove espaços extras se for string)
        processed_value = value.strip() if isinstance(value, str) else value

        # Aplica formatação específica baseada na CHAVE NORMALIZADA
        if isinstance(normalized_key, str):
            if normalized_key in ["nome", "dish"] and isinstance(processed_value, str):
                # Usa a função capitalize melhorada
                processed_value = capitalize(processed_value)
            elif normalized_key == "pront" and isinstance(processed_value, str):
                # Exemplo: Remove IQ0+, pode adicionar outras limpezas se necessário
                processed_value = REMOVE_IQ.sub(
                    "", processed_value.upper())  # Garante maiúsculas também
            # Adicionar outros processamentos de valor aqui se necessário (ex: booleanos, datas)
            # elif normalized_key == "canceled" and isinstance(processed_value, str):
            #     processed_value = processed_value.lower() in ['true', '1', 'sim', 'cancelado']

        # Adiciona ao dicionário de saída usando a chave normalizada
        adjusted_dict[normalized_key] = processed_value

    return adjusted_dict

# --- Funções de Sistema de Arquivos ---


def get_documents_path() -> str:
    """
    Retorna o caminho para a pasta 'Documentos' do usuário, de forma cross-platform.

    Returns:
        str: O caminho absoluto para a pasta de documentos.
    """
    system = platform.system()
    default_path = os.path.expanduser("~/Documents")  # Caminho padrão

    if system == "Windows":
        try:
            # Usa API do Windows para obter o caminho correto (lida com redirecionamento)
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(
                None, CSIDL_PERSONAL, None, SHGFP_TYPE_CURRENT, buf)
            path = buf.value
            # Cria o diretório se não existir (importante se for a primeira vez)
            os.makedirs(path, exist_ok=True)
            return path
        except (AttributeError, OSError, Exception) as e:
            logger.warning(
                f"Falha ao obter caminho de Documentos via API Windows: {e}. Usando padrão: {default_path}")
            # Garante que o padrão exista
            os.makedirs(default_path, exist_ok=True)
            return default_path
    elif system == "Linux":
        # Tenta variável de ambiente XDG, senão usa padrão
        xdg_documents = os.environ.get("XDG_DOCUMENTS_DIR")
        path = xdg_documents.strip('"') if xdg_documents else default_path
        os.makedirs(path, exist_ok=True)  # Garante que exista
        return path
    else:  # macOS ou outros
        os.makedirs(default_path, exist_ok=True)  # Garante que exista
        return default_path

# --- Funções de Leitura/Escrita de Arquivos ---


def _handle_file_error(e: Exception, filename: str, operation: str):
    """ Loga erros comuns de operação de arquivo. """
    if isinstance(e, FileNotFoundError):
        logger.error(f"Arquivo não encontrado para {operation}: {filename}")
    elif isinstance(e, PermissionError):
        logger.error(f"Permissão negada para {operation} arquivo: {filename}")
    elif isinstance(e, JSONDecodeError):
        logger.error(
            f"Erro ao decodificar JSON em {filename} durante {operation}: {e}")
    elif isinstance(e, csv.Error):
        logger.error(f"Erro de CSV em {filename} durante {operation}: {e}")
    elif isinstance(e, (IOError, OSError)):
        logger.error(f"Erro de I/O em {filename} durante {operation}: {e}")
    else:
        # Loga stacktrace
        logger.exception(
            f"Erro inesperado durante {operation} de {filename}: {e}")


def load_json(filename: str) -> Optional[Any]:
    """
    Carrega dados de um arquivo JSON.

    Args:
        filename (str): O caminho para o arquivo JSON.

    Returns:
        Optional[Any]: O conteúdo do arquivo (geralmente dict ou list), ou None se ocorrer erro.
    """
    try:
        with open(filename, "r", encoding="utf-8", errors="ignore") as f:
            return json.load(f)
    except Exception as e:  # pylint: disable=broad-except
        _handle_file_error(e, filename, "leitura JSON")
        return None


def save_json(filename: str, data: Union[Dict[str, Any], List[Any]]) -> bool:
    """
    Salva dados (dict ou list) em um arquivo JSON com indentação.

    Args:
        filename (str): O caminho para o arquivo JSON onde salvar.
        data (Union[Dict, List]): Os dados a serem salvos.

    Returns:
        bool: True se salvo com sucesso, False caso contrário.
    """
    try:
        # Garante que o diretório pai exista
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "w", encoding="utf-8") as f:
            # Usa indent=2 e permite não-ASCII
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:  # pylint: disable=broad-except
        _handle_file_error(e, filename, "escrita JSON")
        return False


def load_csv_as_dict(filename: str) -> Optional[List[Dict[str, str]]]:
    """
    Carrega um arquivo CSV e retorna como uma lista de dicionários.
    As chaves são os nomes das colunas do cabeçalho.

    Args:
        filename (str): O caminho para o arquivo CSV.

    Returns:
        Optional[List[Dict[str, str]]]: Lista de dicionários representando as linhas,
                                       ou None se ocorrer erro.
    """
    try:
        with open(filename, "r", encoding="utf-8", errors="ignore") as file:
            # Assume que a primeira linha é o cabeçalho
            reader = csv.DictReader(file)
            return list(reader)  # Converte para lista de dicts
    except Exception as e:  # pylint: disable=broad-except
        _handle_file_error(e, filename, "leitura CSV (dict)")
        return None


def save_csv_from_list(data: List[List[str]], filename: str, delimiter: str = ',',
                       quotechar: str = '"', quoting: int = csv.QUOTE_MINIMAL) -> bool:
    """
    Salva uma lista de listas em um arquivo CSV.

    Args:
        data (List[List[str]]): Lista de linhas, onde cada linha é uma lista de valores.
                                A primeira linha geralmente é o cabeçalho.
        filename (str): O caminho para o arquivo CSV onde salvar.
        delimiter (str): Delimitador de campos. Padrão ','.
        quotechar (str): Caractere para aspas. Padrão '"'.
        quoting (int): Regra de aspas (ex: csv.QUOTE_MINIMAL, csv.QUOTE_ALL). Padrão MINIMAL.

    Returns:
        bool: True se salvo com sucesso, False caso contrário.
    """
    try:
        # Garante que o diretório pai exista
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile, delimiter=delimiter,
                                quotechar=quotechar, quoting=quoting)
            writer.writerows(data)  # Escreve todas as linhas de uma vez
        logger.info(f"Dados salvos com sucesso em '{filename}'")
        return True
    except Exception as e:  # pylint: disable=broad-except
        _handle_file_error(e, filename, "escrita CSV (list)")
        return False

# --- Funções de Comparação (Exemplo, pode ser removida se não usada globalmente) ---
# A função find_best_matching_pair foi removida daqui pois seu uso
# parece ser específico do SearchStudents. Manter utilitários aqui
# mais genéricos. Se for necessário em múltiplos lugares, pode voltar.
