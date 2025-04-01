"""Utility functions for the registration application.

This module provides a collection of helper functions for common tasks
such as loading and saving data in JSON and CSV formats, finding the
best matching string pairs, capitalizing text according to specific rules,
and adjusting dictionary keys. It also defines a TypedDict for representing
session data.
"""

# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

import csv
import ctypes
import json
from json import JSONDecodeError
import os
import platform
import re
import sys
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, TypedDict

from fuzzywuzzy import fuzz

CSIDL_PERSONAL: int = 5
SHGFP_TYPE_CURRENT: int = 0

TRANSLATE_DICT: Dict[int, int] = str.maketrans("0123456789Xx", "abcdefghijkk")
REMOVE_IQ: re.Pattern[str] = re.compile(r"[Ii][Qq]\d0+")

SESSION = TypedDict(
    'SESSION',
    {
        'refeição': Literal["Lanche", "Almoço"],
        'lanche': str,
        'período': Literal["Integral", "Matutino", "Vespertino", "Noturno"],
        'data': str,
        'hora': str,
        'turmas': List[str]
    })

def to_code(text: str) -> str:
    """
    Translates a given text by removing 'IQ' followed by digits and then
    applying a translation dictionary.

    Args:
        text (str): The input string to be translated.

    Returns:
        str: The translated string.
    """
    text = REMOVE_IQ.sub("", text)
    translated = text.translate(TRANSLATE_DICT)
    return " ".join(translated)


def get_documments_path() -> str:
    """
    Returns the path to the user's documents directory based on the operating system.

    On Windows, it uses the SHGetFolderPathW API to get the path to the CSIDL_PERSONAL 
    (Documents) folder. On Linux, it checks the XDG_DOCUMENTS_DIR environment variable 
    or defaults to the user's home Documents folder. On other platforms, it defaults to 
    the user's home Documents folder.

    Returns:
        str: The path to the documents directory.
    """
    if platform.system() == "Windows":
        try:
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(
                None, CSIDL_PERSONAL, None, SHGFP_TYPE_CURRENT, buf
            )
            return buf.value
        except (AttributeError, OSError):
            return os.path.expanduser("~/Documents")
    elif platform.system() == "Linux":
        xdg_documents = os.environ.get("XDG_DOCUMENTS_DIR")
        if xdg_documents:
            return xdg_documents.strip('"')
        return os.path.expanduser("~/Documents")
    return os.path.expanduser("~/Documents")


def load_json(filename) -> dict | None:
    """
    Loads a JSON file and returns its contents as a dictionary.

    Args:
        filename (str): The path to the JSON file to be loaded.

    Returns:
        dict | None: The contents of the JSON file as a dictionary if successful,
        otherwise None if an error occurs.
    """

    try:
        with open(filename, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        return data
    except (FileNotFoundError, PermissionError, JSONDecodeError) as e:
        print(e, file=sys.stderr)
    return None


def load_csv(filename: str) -> Optional[dict | list]:
    """
    Loads a CSV file and returns its contents as a list of dictionaries.

    Args:
        filename (str): The path to the CSV file to be loaded.

    Returns:
        dict | list | None: The contents of the CSV file as a list of dictionaries
        if successful, otherwise None if an error occurs.
    """
    try:
        with open(filename, "r", encoding="utf-8", errors="ignore") as file:
            return list(csv.DictReader(file))
    except FileNotFoundError:
        print(f"File not found: {filename}", file=sys.stderr)
    except csv.Error as e:
        print(f"Error parsing CSV file: {e}", file=sys.stderr)

    return None


def save_csv(data, filename, delimiter=',', quotechar='"', quoting=csv.QUOTE_NONNUMERIC):
    """
    Saves data to a CSV file with specified formatting options.

    Args:
        data (list): A list of rows, where each row is an iterable of values, to be
                        written to theCSV.
        filename (str): The path to the file where the CSV data will be saved.
        delimiter (str, optional): A one-character string used to separate fields in the CSV.
                                    Defaults to ','.
        quotechar (str, optional): A one-character string used to quote fields containing special
                                    characters. Defaults to '"'.
        quoting (int, optional): Controls the quoting behavior. Defaults to csv.QUOTE_NONNUMERIC.

    Returns:
        bool: True if the data was successfully saved, False if an error occurred during
                the process.
    """

    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile, delimiter=delimiter,
                                quotechar=quotechar, quoting=quoting)
            for row in data:
                writer.writerow(row)
        print(f"Data successfully saved to '{filename}'")
        return True
    except IOError as e:
        print(f"An I/O error occurred while saving to CSV: {e}")
    except csv.Error as e:
        print(f"A CSV error occurred while saving to CSV: {e}")
    return False


def save_json(filename: str, data: dict | list) -> bool:
    """
    Saves a dictionary or list to a JSON file with pretty formatting.

    Args:
        filename (str): The path to the file where the JSON data will be saved.
        data (dict | list): The data to be saved, either as a dictionary or a list.

    Returns:
        bool: True if the data was successfully saved, False if an error occurred.
    """

    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2))
        return True
    except (IOError, OSError) as e:
        print(e, file=sys.stderr)
    return False


def find_best_matching_pair(target_pair: Tuple, vector_of_pairs: List[Tuple],
                            score_function: Callable[[
                                Any, Any], int] = fuzz.ratio
                            ) -> Tuple[Tuple[str, str], int]:
    """
    Finds the best matching pair of strings in a given vector of pairs, given a target pair,
    using a specified score function.

    Args:
        target_pair (tuple): A pair of strings to be compared with each pair in the vector.
        vector_of_pairs (list): A list of pairs of strings to be compared with the target pair.
        score_function (function, optional): A function that takes two strings and returns a score.
                                            Defaults to fuzz.ratio.

    Returns:
        tuple: A tuple containing the best matching pair and its corresponding score.
    """
    if not vector_of_pairs:
        return None, 0

    best_match = None
    highest_score = -1

    for pair in vector_of_pairs:
        if len(pair) != 2 or len(target_pair) != 2:
            raise ValueError(
                "Both target_pair and elements in vector_of_pairs must be pairs of strings.")

        string1_target, string2_target = target_pair
        string1_vector, string2_vector = pair

        score1 = score_function(string1_target, string1_vector)
        score2 = score_function(string2_target, string2_vector)

        overall_score = (score1 + 2*score2) / 3

        if overall_score > highest_score:
            highest_score = overall_score
            best_match = pair

    return best_match, highest_score


CAPITALIZE_EXCEPTIONS = {
    "a", "o",
    "as", "os",
    "de", "dos",
    "das", "do",
    "da", "e",
    "é", "com",
    "sem", "ou",
    "para", "por",
    "no", "na",
    "nos", "nas"}

TRANSLATE_KEYS = {
    'matrícula iq': 'pront',
    'matrícula': 'pront',
    'prontuário': 'pront',
    'refeição': 'prato'
}


def capitalize(text: str) -> str:
    """
    Returns the given string capitalized, unless it is in the set of given exceptions.
    The exceptions are lowercased words that should not be capitalized.

    Examples:
        >>> capitalize('a')
        'a'
        >>> capitalize('A')
        'a'
        >>> capitalize('hello world')
        'Hello world'
        >>> capitalize('hello World')
        'hello World'
    """
    text = text.strip()
    if len(text) == 0:
        return ""
    ltext = text.lower()
    if ltext in CAPITALIZE_EXCEPTIONS:
        return ltext
    return text[0].upper() + ltext[1:]


def adjust_keys(input_dict: dict) -> dict:
    """
    Adjusts the keys and values of a given dictionary according to predefined rules.

    This function processes the input dictionary by converting all string keys to lowercase,
    translating certain keys using a translation dictionary, and performing specific
    formatting on the values based on their keys. Keys like "nome" and "prato" have their
    values capitalized appropriately, while keys like "pront" have specific patterns
    replaced in their values.

    Args:
        input_dict (dict): The dictionary whose keys and values need to be adjusted.

    Returns:
        dict: A new dictionary with adjusted keys and values.
    """

    lowercase_dict = {}
    for key, value in input_dict.items():
        if isinstance(key, str):
            key = key.strip().lower()
            key = TRANSLATE_KEYS.get(key, key)
            if isinstance(value, str):
                value = value.strip()

            if key in ["nome", "prato"]:
                value = " ".join(capitalize(v) for v in value.split(" "))
            elif key == "pront":
                value = re.sub(r'IQ\d{2}', 'IQ30', value.upper())

            lowercase_dict[key] = value
        else:
            lowercase_dict[key] = value
    return lowercase_dict
