# ----------------------------------------------------------------------------
# File: registro/control/utils.py (Core Utilities)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
General utility functions for the meal registration application.
Provides helpers for text processing (custom capitalization, key normalization,
prontuario cleaning/encoding), file system interaction (finding Documents path),
and reading/writing JSON and CSV files.
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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable, Literal, Set, Union
from registro.control.constants import (
    CAPITALIZATION_EXCEPTIONS, CSIDL_PERSONAL, PRONTUARIO_CLEANUP_REGEX,
    SHGFP_TYPE_CURRENT, PRONTUARIO_OBFUSCATION_MAP, EXTERNAL_KEY_TRANSLATION
)
logger = logging.getLogger(__name__)

def to_code(text: str) -> str:
    if not isinstance(text, str):
        logger.warning(f"Invalid input to to_code: Expected string, got {type(text)}. Returning empty string.")
        return ""
    text_cleaned = PRONTUARIO_CLEANUP_REGEX.sub("", text)
    translated = text_cleaned.translate(PRONTUARIO_OBFUSCATION_MAP)
    return translated

def capitalize(text: str) -> str:
    if not isinstance(text, str):
        logger.warning(f"Invalid input to capitalize: Expected string, got {type(text)}. Returning empty string.")
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
        if lword in CAPITALIZATION_EXCEPTIONS:
            capitalized_words.append(lword)
        elif len(word) == 1:
            capitalized_words.append(word.upper())
        else:
            capitalized_words.append(word[0].upper() + lword[1:])
    return " ".join(capitalized_words)

def adjust_keys(input_dict: Dict[Any, Any]) -> Dict[str, Any]:
    adjusted_dict: Dict[str, Any] = {}
    if not isinstance(input_dict, dict):
        logger.warning(f"Invalid input to adjust_keys: Expected dict, got {type(input_dict)}. Returning empty dict.")
        return adjusted_dict
    for original_key, value in input_dict.items():
        normalized_key: str
        if isinstance(original_key, str):
            normalized_key = original_key.strip().lower()
            normalized_key = EXTERNAL_KEY_TRANSLATION.get(normalized_key, normalized_key)
        else:
            try:
                normalized_key = str(original_key).strip().lower()
                logger.debug(f"Converted non-string key '{original_key}' to '{normalized_key}'.")
            except Exception:
                logger.warning(
                    f"Could not convert key {original_key} ({type(original_key)}) to string. Using raw string representation.")
                normalized_key = repr(original_key)
        processed_value: Any = value.strip() if isinstance(value, str) else value
        if normalized_key in ["nome", "dish"] and isinstance(processed_value, str):
            processed_value = capitalize(processed_value)
        elif normalized_key == "pront" and isinstance(processed_value, str):
            processed_value = PRONTUARIO_CLEANUP_REGEX.sub("", processed_value).upper()
        adjusted_dict[normalized_key] = processed_value
    return adjusted_dict

def get_documents_path() -> str:
    system = platform.system()
    default_path = Path.home() / "Documents"
    path_to_return: Path
    if system == "Windows":
        try:
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(
                None, CSIDL_PERSONAL, None, SHGFP_TYPE_CURRENT, buf
            )
            path_to_return = Path(buf.value)
            logger.debug(f"Documents path obtained via Windows API: {path_to_return}")
        except (AttributeError, OSError, Exception) as e:
            logger.warning(f"Failed to get Documents path via Windows API: {e}. Using default: {default_path}")
            path_to_return = default_path
    elif system == "Linux":
        xdg_documents = os.environ.get("XDG_DOCUMENTS_DIR")
        if xdg_documents and Path(xdg_documents).is_dir():
            path_to_return = Path(xdg_documents)
            logger.debug(f"Documents path obtained via XDG_DOCUMENTS_DIR: {path_to_return}")
        else:
            if xdg_documents:
                logger.warning(f"XDG_DOCUMENTS_DIR ('{xdg_documents}') not valid. Using default.")
            else:
                logger.debug("XDG_DOCUMENTS_DIR not set. Using default.")
            path_to_return = default_path
    else:
        logger.debug(f"System is {system}. Using default Documents path: {default_path}")
        path_to_return = default_path
    try:
        path_to_return.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(f"Could not create Documents directory at '{path_to_return}': {e}. Returning path anyway.")
    except Exception as e:
        logger.exception(f"Unexpected error ensuring Documents directory exists: {e}")
    return str(path_to_return.resolve())

def _handle_file_error(e: Exception, filename: Union[str, Path], operation: str):
    filepath = str(filename)
    if isinstance(e, FileNotFoundError):
        logger.error(f"File not found during {operation}: {filepath}")
    elif isinstance(e, PermissionError):
        logger.error(f"Permission denied during {operation} on file: {filepath}")
    elif isinstance(e, JSONDecodeError):
        logger.error(f"JSON decoding error during {operation} in file: {filepath} - {e}")
    elif isinstance(e, csv.Error):
        logger.error(f"CSV format error during {operation} in file: {filepath} - {e}")
    elif isinstance(e, (IOError, OSError)):
        logger.error(f"File I/O error during {operation} on {filepath}: {e}")
    else:
        logger.exception(f"Unexpected error during {operation} of {filepath}: {e}")

def load_json(filename: str) -> Optional[Any]:
    logger.debug(f"Attempting to load JSON data from: {filename}")
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.debug(f"Successfully loaded JSON data from: {filename}")
            return data
    except Exception as e:
        _handle_file_error(e, filename, "JSON load")
        return None

def save_json(filename: str, data: Union[Dict[str, Any], List[Any]]) -> bool:
    logger.debug(f"Attempting to save JSON data to: {filename}")
    try:
        file_path = Path(filename)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.debug(f"Successfully saved JSON data to: {filename}")
        return True
    except TypeError as te:
        logger.error(f"Data type error saving JSON to {filename}: {te}. Data: {data!r}")
        _handle_file_error(te, filename, "JSON save (type error)")
        return False
    except Exception as e:
        _handle_file_error(e, filename, "JSON save")
        return False

def load_csv_as_dict(filename: str) -> Optional[List[Dict[str, str]]]:
    logger.debug(f"Attempting to load CSV data as dict list from: {filename}")
    rows: List[Dict[str, str]] = []
    try:
        with open(filename, "r", newline='', encoding="utf-8") as file:
            reader = csv.DictReader(file)
            rows = list(reader)
            logger.debug(f"Successfully loaded {len(rows)} data rows from CSV: {filename}")
            return rows
    except Exception as e:
        _handle_file_error(e, filename, "CSV load (as dict)")
        return None

def save_csv_from_list(data: List[List[Any]], filename: str, delimiter: str = ',',
                       quotechar: str = '"', quoting: int = csv.QUOTE_MINIMAL) -> bool:
    logger.debug(f"Attempting to save list data to CSV: {filename}")
    if not data:
        logger.warning(f"No data provided to save_csv_from_list for file: {filename}. Skipping write.")
        return True
    try:
        file_path = Path(filename)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile, delimiter=delimiter,
                                quotechar=quotechar, quoting=quoting)
            writer.writerows(data)
        logger.info(f"Successfully saved {len(data)} rows to CSV: {filename}")
        return True
    except Exception as e:
        _handle_file_error(e, filename, "CSV save (from list)")
        return False
