# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# File: registro/control/utils.py (Utilitários Principais)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Fornece funções utilitárias gerais para a aplicação de registro de refeições.
Inclui helpers para processamento de texto (capitalização customizada,
normalização de chaves, limpeza/codificação de prontuário), interação com
sistema de arquivos (encontrar pasta Documentos), e leitura/escrita de
arquivos JSON e CSV.
"""
import csv
import ctypes
import ctypes.wintypes  # Import explícito para clareza
import json
import logging
import os
import platform
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from registro.control.constants import (CAPITALIZATION_EXCEPTIONS,
                                        CSIDL_PERSONAL,
                                        EXTERNAL_KEY_TRANSLATION,
                                        PRONTUARIO_CLEANUP_REGEX,
                                        PRONTUARIO_OBFUSCATION_MAP,
                                        SHGFP_TYPE_CURRENT)

logger = logging.getLogger(__name__)


def to_code(text: str) -> str:
    """
    Ofusca um prontuário removendo prefixos comuns e substituindo dígitos
    por letras predefinidas. Útil para criar chaves de lookup não identificáveis.

    Args:
        text: A string contendo o prontuário a ser ofuscado.

    Returns:
        A string ofuscada ou uma string vazia se a entrada for inválida.
    """
    if not isinstance(text, str):
        logger.warning(
            "Entrada inválida para to_code: Esperado string, recebido %s."
            " Retornando string vazia.", type(text),
        )
        return ""
    # Remove prefixos como 'IQ000...' ou 'iq0...'
    text_cleaned = PRONTUARIO_CLEANUP_REGEX.sub("", text)
    # Aplica o mapeamento de caracteres definido em constants.py
    translated = text_cleaned.translate(PRONTUARIO_OBFUSCATION_MAP)
    return translated


def capitalize(text: str) -> str:
    """
    Capitaliza um texto seguindo regras específicas: palavras em
    `CAPITALIZATION_EXCEPTIONS` ficam em minúsculo, palavras de uma letra
    ficam em maiúsculo, e as demais seguem capitalização normal (primeira
    letra maiúscula, resto minúsculo).

    Args:
        text: A string a ser capitalizada.

    Returns:
        A string capitalizada ou uma string vazia se a entrada for inválida.
    """
    if not isinstance(text, str):
        logger.warning(
            "Entrada inválida para capitalize: Esperado string, recebido %s."
            " Retornando string vazia.", type(text),
        )
        return ""
    text = text.strip()
    if not text:
        return ""
    words = text.split(" ")
    capitalized_words = []
    for word in words:
        if not word:  # Ignora múltiplos espaços
            continue
        lword = word.lower()
        if lword in CAPITALIZATION_EXCEPTIONS:
            capitalized_words.append(lword)
        # Trata siglas ou iniciais (ex: 'J. K. Rowling')
        elif len(word) == 1 or (len(word) == 2 and word.endswith(".")):
            capitalized_words.append(word.upper())
        else:
            # Capitalização padrão (primeira maiúscula, resto minúsculo)
            capitalized_words.append(word[0].upper() + lword[1:])
    return " ".join(capitalized_words)


def adjust_keys(input_dict: Dict[Any, Any]) -> Dict[str, Any]:
    """
    Normaliza as chaves de um dicionário (para minúsculas, sem espaços extras),
    traduz chaves conhecidas (definidas em EXTERNAL_KEY_TRANSLATION) e aplica
    processamento específico (capitalize, limpeza de prontuário) a valores
    de chaves específicas ('nome', 'dish', 'pront').

    Args:
        input_dict: O dicionário original com chaves e valores diversos.

    Returns:
        Um novo dicionário com chaves normalizadas e valores processados.
        Retorna um dicionário vazio se a entrada não for um dicionário.
    """
    adjusted_dict: Dict[str, Any] = {}
    if not isinstance(input_dict, dict):
        logger.warning(
            "Entrada inválida para adjust_keys: Esperado dict, recebido %s."
            " Retornando dict vazio.",type(input_dict),
        )
        return adjusted_dict

    for original_key, value in input_dict.items():
        normalized_key: str
        # Normaliza a chave para string minúscula
        if isinstance(original_key, str):
            normalized_key = original_key.strip().lower()
            # Traduz a chave se houver mapeamento definido
            normalized_key = EXTERNAL_KEY_TRANSLATION.get(
                normalized_key, normalized_key
            )
        else:
            try:
                # Tenta converter chaves não-string
                normalized_key = str(original_key).strip().lower()
                logger.debug(
                    "Chave não-string '%s' convertida para '%s'.",
                    original_key,
                    normalized_key,
                )
            except Exception:
                # Se a conversão falhar, usa a representação da chave
                normalized_key = repr(original_key)
                logger.warning(
                    "Não foi possível converter a chave %s (%s) para string."
                    " Usando representação: '%s'.",
                    original_key,
                    type(original_key),
                    normalized_key,
                )

        # Processa o valor
        processed_value: Any = value.strip() if isinstance(value, str) else value

        # Aplica capitalização ou limpeza baseada na chave normalizada
        if normalized_key in ["nome", "dish"] and isinstance(processed_value, str):
            processed_value = capitalize(processed_value)
        elif normalized_key == "pront" and isinstance(processed_value, str):
            # Remove prefixo 'IQ0...' e garante maiúsculas
            processed_value = PRONTUARIO_CLEANUP_REGEX.sub("", processed_value).upper()

        adjusted_dict[normalized_key] = processed_value

    return adjusted_dict


def get_documents_path() -> str:
    """
    Determina e retorna o caminho para a pasta 'Documentos' do usuário atual,
    independentemente do sistema operacional (Windows, Linux). Cria a pasta
    se ela não existir.

    Returns:
        O caminho absoluto para a pasta 'Documentos' como string.
        Em caso de falha, retorna um caminho padrão baseado no home do usuário.
    """
    system = platform.system()
    default_path: Path = Path.home() / "Documents"
    path_to_return: Path

    if system == "Windows":
        try:
            # Cria um buffer para receber o caminho
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            # Chama a função da API do Windows para obter o caminho
            ctypes.windll.shell32.SHGetFolderPathW(  # type: ignore
                None, CSIDL_PERSONAL, None, SHGFP_TYPE_CURRENT, buf
            )
            path_to_return = Path(buf.value)
            logger.debug("Caminho Documentos (Windows API): %s", path_to_return)
        except (AttributeError, OSError, Exception) as e:
            logger.warning(
                "Falha ao obter caminho Documentos via API Windows: %s. Usando padrão: %s",
                e, default_path,
            )
            path_to_return = default_path
    elif system == "Linux":
        # Tenta obter via variável de ambiente XDG
        xdg_documents = os.environ.get("XDG_DOCUMENTS_DIR")
        if xdg_documents and Path(xdg_documents).is_dir():
            path_to_return = Path(xdg_documents)
            logger.debug("Caminho Documentos (XDG_DOCUMENTS_DIR): %s", path_to_return)
        else:
            # Se a variável não existe ou aponta para local inválido, usa o padrão
            if xdg_documents:
                logger.warning(
                    "XDG_DOCUMENTS_DIR ('%s') não é válido. Usando padrão.",
                    xdg_documents,
                )
            else:
                logger.debug("XDG_DOCUMENTS_DIR não definido. Usando padrão.")
            path_to_return = default_path
    else:  # Outros sistemas (macOS, etc.)
        logger.debug(
            "Sistema %s. Usando caminho padrão para Documentos: %s",
            system,
            default_path,
        )
        path_to_return = default_path

    # Garante que o diretório exista, criando-o se necessário
    try:
        path_to_return.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(
            "Não foi possível criar o diretório Documentos em '%s': %s."
            " Retornando caminho mesmo assim.",path_to_return, e,
        )
    except Exception as e:
        logger.exception(
            "Erro inesperado ao garantir a existência do diretório Documentos: %s", e
        )

    # Retorna o caminho absoluto resolvido como string
    return str(path_to_return.resolve())


def _handle_file_error(e: Exception, filename: Union[str, Path], operation: str):
    """
    Centraliza o tratamento e logging de erros comuns de I/O de arquivos.

    Args:
        e: A exceção capturada.
        filename: O nome/caminho do arquivo que causou o erro.
        operation: Descrição da operação que falhou (ex: "JSON load", "CSV save").
    """
    filepath = str(filename)
    if isinstance(e, FileNotFoundError):
        logger.error("Arquivo não encontrado durante '%s': %s", operation, filepath)
    elif isinstance(e, PermissionError):
        logger.error(
            "Permissão negada durante '%s' no arquivo: %s", operation, filepath
        )
    elif isinstance(e, JSONDecodeError):
        logger.error(
            "Erro de decodificação JSON durante '%s' no arquivo: %s - %s",
            operation,
            filepath,
            e,
        )
    elif isinstance(e, csv.Error):
        logger.error(
            "Erro de formato CSV durante '%s' no arquivo: %s - %s",
            operation,
            filepath,
            e,
        )
    elif isinstance(e, (IOError, OSError)):
        logger.error("Erro de I/O durante '%s' em %s: %s", operation, filepath, e)
    else:
        # Loga a exceção completa para erros inesperados
        logger.exception(
            "Erro inesperado durante '%s' de %s: %s", operation, filepath, e
        )


def load_json(filename: str) -> Optional[Any]:
    """
    Carrega dados de um arquivo JSON.

    Args:
        filename: O caminho para o arquivo JSON.

    Returns:
        Os dados carregados do JSON (pode ser dict, list, etc.) ou None se ocorrer um erro.
    """
    logger.debug("Tentando carregar dados JSON de: %s", filename)
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.debug("Dados JSON carregados com sucesso de: %s", filename)
            return data
    except Exception as e:
        _handle_file_error(e, filename, "leitura JSON")
        return None


def save_json(filename: str, data: Union[Dict[str, Any], List[Any]]) -> bool:
    """
    Salva dados (dicionário ou lista) em um arquivo JSON com formatação indentada.
    Cria diretórios pais se não existirem.

    Args:
        filename: O caminho para o arquivo JSON onde salvar os dados.
        data: Os dados (dict ou list) a serem salvos.

    Returns:
        True se a operação for bem-sucedida, False caso contrário.
    """
    logger.debug("Tentando salvar dados JSON em: %s", filename)
    try:
        file_path = Path(filename)
        # Cria diretórios pais, se necessário
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            # ensure_ascii=False para salvar caracteres acentuados corretamente
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.debug("Dados JSON salvos com sucesso em: %s", filename)
        return True
    except TypeError as te:
        # Erro comum se tentar serializar tipos não suportados por JSON
        logger.error(
            "Erro de tipo ao salvar JSON em %s: %s. Dados: %r", filename, te, data
        )
        _handle_file_error(te, filename, "escrita JSON (erro de tipo)")
        return False
    except Exception as e:
        _handle_file_error(e, filename, "escrita JSON")
        return False


def load_csv_as_dict(filename: str) -> Optional[List[Dict[str, str]]]:
    """
    Lê um arquivo CSV e retorna uma lista de dicionários, onde cada dicionário
    representa uma linha e as chaves são os cabeçalhos do CSV.

    Args:
        filename: O caminho para o arquivo CSV.

    Returns:
        Uma lista de dicionários representando as linhas do CSV, ou None se ocorrer um erro.
        Retorna lista vazia se o CSV estiver vazio (apenas cabeçalho).
    """
    logger.debug("Tentando carregar CSV como lista de dicts de: %s", filename)
    rows: List[Dict[str, str]] = []
    try:
        with open(filename, "r", newline="", encoding="utf-8") as file:
            # Assume que a primeira linha é o cabeçalho
            reader = csv.DictReader(file)
            # Converte o reader para uma lista de dicionários
            rows = list(reader)
            logger.debug(
                "Carregadas %s linhas de dados do CSV: %s", len(rows), filename
            )
            return rows
    except Exception as e:
        _handle_file_error(e, filename, "leitura CSV (como dict)")
        return None


def save_csv_from_list(
    data: List[List[Any]],
    filename: str,
    delimiter: str = ",",
    quotechar: str = '"',
    quoting: int = csv.QUOTE_MINIMAL,
) -> bool:
    """
    Salva uma lista de listas em um arquivo CSV.
    Cria diretórios pais se não existirem.

    Args:
        data: Uma lista de listas, onde cada lista interna representa uma linha do CSV.
              A primeira lista interna é geralmente o cabeçalho.
        filename: O caminho para o arquivo CSV onde salvar os dados.
        delimiter: O caractere delimitador a ser usado (padrão: ',').
        quotechar: O caractere para envolver campos que contêm o delimitador (padrão: '"').
        quoting: Controla quando as aspas devem ser geradas (padrão: csv.QUOTE_MINIMAL).

    Returns:
        True se a operação for bem-sucedida, False caso contrário.
    """
    logger.debug("Tentando salvar dados de lista para CSV: %s", filename)
    if not data:
        logger.warning(
            "Nenhum dado fornecido para save_csv_from_list para o arquivo: %s. Escrita pulada.",
            filename,
        )
        return True
    try:
        file_path = Path(filename)
        # Cria diretórios pais, se necessário
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
            # Cria um escritor CSV com as opções especificadas
            writer = csv.writer(
                csvfile, delimiter=delimiter, quotechar=quotechar, quoting=quoting
            )
            # Escreve todas as linhas da lista de listas
            writer.writerows(data)
        logger.info("%s linhas salvas com sucesso no CSV: %s", len(data), filename)
        return True
    except Exception as e:
        _handle_file_error(e, filename, "escrita CSV (de lista)")
        return False
