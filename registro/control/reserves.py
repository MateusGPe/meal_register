# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Provides functions for importing student and reserve data from CSV files
and for reserving snacks for all students.
"""

import csv
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.exc import SQLAlchemyError

from registro.control.generic_crud import CRUD
from registro.control.utils import adjust_keys, find_best_matching_pair
from registro.model.tables import Reserve, Students


def import_reserves_csv(student_crud: CRUD[Students], reserve_crud: CRUD[Reserve],
                        csv_file_path: str) -> bool:
    """
    Imports reserve data from a CSV file into the database.

    This function reads student and reserve information from a CSV file,
    creates new student records if they don't exist, and creates corresponding
    reserve entries. It also handles cases where students might not have
    a reservation on a given date by creating a "Sem Reserva" entry.

    Args:
        student_crud (CRUD[Students]): CRUD object for interacting with the Students table.
        reserve_crud (CRUD[Reserve]): CRUD object for interacting with the Reserve table.
        csv_file_path (str): The path to the CSV file containing the reserve data.

    Returns:
        bool: True if the import was successful, False otherwise.
    """
    values = {(s.pront, s.nome)
              for s in student_crud.read_all()}

    try:
        existing_students_pronts: Set[str] = {
            s.pront for s in student_crud.read_all()
        }
        new_students_data: Dict[str, Dict[str, str]] = {}
        csv_reserves_data: List[Dict[str, str]] = []
        unique_dates: Set[str] = set()
        reserved_data_pront_pairs: Set[Tuple[str, str]] = set()

        with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    row = adjust_keys(row)
                    pront = row['pront']
                    nome = row['nome']
                    turma = row['turma']
                    prato = row['prato']
                    data = row['data']

                    unique_dates.add(data)
                    reserved_data_pront_pairs.add((data, pront))

                    if pront not in new_students_data and pront not in existing_students_pronts:
                        (pair, ratio) = find_best_matching_pair(
                            (pront, nome), values)
                        if ratio >= 95:
                            diff = []
                            if pair[0] != pront:
                                diff.append(f"'{pair[0]}' -> '{pront}'")
                            if pair[1] != nome:
                                diff.append(f"'{pair[1]}' -> '{nome}'")
                            print(
                                f'{pront} - {nome}: {', '.join(diff)}, ratio: {int(ratio)}')
                            (pront, nome) = pair
                        else:
                            new_students_data[pront] = {
                                'pront': pront, 'nome': nome+"*", 'turma': turma}

                    csv_reserves_data.append({
                        'pront': pront, 'prato': prato, 'data': data, 'snacks': False,
                        'reserved': True})
                except KeyError as e:
                    print(f"Missing key in row: {row}. Error: {e}")
                except csv.Error as e:
                    print(f"Error parsing CSV: {e}")
                except SQLAlchemyError as e:
                    print(f"Database error: {e}")

        if new_students_data:
            student_crud.bulk_create(list(new_students_data.values()))

        all_students_by_pront: Dict[str, Students] = {
            student.pront: student for student in student_crud.read_all()
        }

        not_in_reserve_entries: List[Dict[str, Optional[str]]] = []
        for student_pront in all_students_by_pront:
            for date in unique_dates:
                if (date, student_pront) not in reserved_data_pront_pairs:
                    not_in_reserve_entries.append({
                        'pront': student_pront, 'prato': 'Sem Reserva',
                        'data': date, 'reserved': False})

        all_reserves_data = csv_reserves_data + not_in_reserve_entries

        reserves_to_insert: List[dict] = []
        for reserve_info in all_reserves_data:
            pront = reserve_info['pront']
            if pront in all_students_by_pront:
                reserves_to_insert.append({
                    'prato': reserve_info.get('prato'),
                    'data': reserve_info['data'],
                    'reserved': reserve_info['reserved'],
                    'snacks': False,
                    'student_id': all_students_by_pront[pront].id})
            else:
                print(f"Warning: Student with pront '{pront}' not found"
                      " in the database for a reserve entry.")

        if reserves_to_insert:
            reserve_crud.bulk_create(reserves_to_insert)
            reserve_crud.commit()

        print(f"Successfully imported data from {csv_file_path}")
        return True

    except FileNotFoundError:
        print(f"File not found: {csv_file_path}")
        return False
    except csv.Error as e:
        print(f"Error parsing CSV: {e}")
        return False
    except SQLAlchemyError as e:
        student_crud.rollback()
        print(f"Database error: {e}")
        return False
    except (TypeError, ValueError) as e:
        print(f"Invalid data: {e}")
        return False


def import_students_csv(student_crud: CRUD[Students], csv_file_path: str) -> bool:
    """
    Imports student data from a CSV file into the database.

    This function reads student information (pront, nome, turma) from a CSV
    file and creates new student records in the database if they don't
    already exist.

    Args:
        student_crud (CRUD[Students]): CRUD object for interacting with the Students table.
        csv_file_path (str): The path to the CSV file containing the student data.

    Returns:
        bool: True if the import was successful, False otherwise.
    """
    try:
        existing_students_pronts: Set[str] = {
            s.pront for s in student_crud.read_all()
        }
        new_students_data: Dict[str, Dict[str, str]] = {}

        with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    row = adjust_keys(row)
                    pront = row['pront']
                    nome = row['nome']
                    turma = row['turma']

                    if pront not in new_students_data and pront not in existing_students_pronts:
                        new_students_data[pront] = {
                            'pront': pront, 'nome': nome, 'turma': turma}
                except KeyError as e:
                    print(f"Missing key in row: {row}. Error: {e}")
                except (TypeError, ValueError) as e:
                    print(f"Error processing row: {row}. Error: {e}")

        if new_students_data:
            student_crud.bulk_create(list(new_students_data.values()))

        print(f"Successfully imported students from {csv_file_path}")
        return True

    except FileNotFoundError:
        print(f"File not found: {csv_file_path}")
        return False
    except csv.Error as e:
        print(f"Error parsing CSV: {e}")
        return False
    except SQLAlchemyError as e:
        student_crud.rollback()
        print(f"Database error: {e}")
        return False
    except (TypeError, ValueError) as e:
        print(f"Invalid data: {e}")
        return False


def reserve_snacks(student_crud: CRUD[Students], reserve_crud: CRUD[Reserve],
                   data: str, prato: str) -> bool:
    """
    Reserves a specific snack for all students on a given date.

    Args:
        student_crud (CRUD[Students]): CRUD object for interacting with the Students table.
        reserve_crud (CRUD[Reserve]): CRUD object for interacting with the Reserve table.
        data (str): The date for which to reserve the snack (in 'YYYY-MM-DD' format).
        prato (str): The name of the snack to reserve.

    Returns:
        bool: True if the snack reservation was successful for all students, False otherwise.
    """
    try:
        students = student_crud.read_all()

        reserves_to_insert: List[dict] = []
        for student in students:
            reserves_to_insert.append({
                'prato': prato,
                'data': data,
                'reserved': True,
                'snacks': True,
                'student_id': student.id
            })
        reserve_crud.bulk_create(reserves_to_insert)
        reserve_crud.commit()
        return True
    except SQLAlchemyError as e:
        reserve_crud.rollback()
        print(f"Database error: {e}")
        return False
    except (TypeError, ValueError) as e:
        print(f"Invalid data: {e}")
        return False
